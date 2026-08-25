"""Secure read-only boundary for exact immutable P4 IK bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import stat

from .ik_bundle_contract import (
    DOCUMENT_NAMES,
    MAX_DOCUMENT_BYTES,
    MAX_TOTAL_DOCUMENT_BYTES,
)
from .ik_bundle_integrity import (
    IkBundleIntegrityError,
    IkBundleSnapshot,
    VerifiedIkBundle,
    verify_ik_bundle_snapshot,
)
from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)


class VerifiedIkBundleReaderError(RuntimeError):
    """Raised when an exact P4 bundle cannot be snapshotted and reproduced."""


@dataclass(frozen=True, slots=True)
class VerifiedIkBundleReader:
    """Resolve no aliases and verify one exact P4 address without writes."""

    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def load(
        self,
        project_id: str,
        profile_sha256: str,
        bundle_sha256: str,
    ) -> VerifiedIkBundle:
        """Read each admitted file once, then rebuild all P4 evidence."""

        try:
            project = require_safe_token(project_id, "Project id")
            profile_sha = require_sha256(profile_sha256, "IK profile")
            bundle_sha = require_sha256(bundle_sha256, "IK bundle")
        except LayerManifestError as exc:
            raise VerifiedIkBundleReaderError(
                "Verified IK bundle identity is invalid"
            ) from exc
        try:
            directory = _resolve_bundle(
                self.state_root, project, profile_sha, bundle_sha
            )
            snapshot = _snapshot(directory)
            verified = verify_ik_bundle_snapshot(
                snapshot,
                state_root=self.state_root,
                expected_project_id=project,
                expected_profile_sha256=profile_sha,
                expected_bundle_sha256=bundle_sha,
            )
            if verified.path != directory:
                raise VerifiedIkBundleReaderError(
                    "Verified IK bundle path changed during verification"
                )
            return verified
        except VerifiedIkBundleReaderError:
            raise
        except (
            IkBundleIntegrityError,
            KeyError,
            OSError,
            OverflowError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise VerifiedIkBundleReaderError(
                f"Verified IK bundle load failed: {exc}"
            ) from exc


def _resolve_bundle(
    root: Path,
    project: str,
    profile_sha: str,
    bundle_sha: str,
) -> Path:
    try:
        if _is_alias(root):
            raise VerifiedIkBundleReaderError("IK bundle state root is aliased")
        trusted = root.resolve(strict=True)
        _real_directory(trusted, "IK bundle state root")
        current = trusted
        for name in (
            "builds", project, "ik-targets", profile_sha, bundle_sha,
        ):
            current = _exact_directory(current, name)
        resolved = current.resolve(strict=True)
        resolved.relative_to(trusted)
        if resolved != current or _is_alias(resolved):
            raise VerifiedIkBundleReaderError("IK bundle path is aliased")
        return resolved
    except VerifiedIkBundleReaderError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise VerifiedIkBundleReaderError(
            "Exact IK bundle path was not found"
        ) from exc


def _exact_directory(parent: Path, name: str) -> Path:
    _real_directory(parent, "IK bundle parent")
    matches = [
        item for item in _children(parent)
        if item.name.casefold() == name.casefold()
    ]
    if len(matches) != 1 or matches[0].name != name:
        raise VerifiedIkBundleReaderError(
            f"IK bundle path is missing or case-mismatched: {name}"
        )
    return _real_directory(matches[0], f"IK bundle path {name}")


def _snapshot(root: Path) -> IkBundleSnapshot:
    _real_directory(root, "IK bundle directory")
    children = _children(root)
    files = {
        child.name: _regular_file(child, child.name) for child in children
    }
    if set(files) != set(DOCUMENT_NAMES):
        raise VerifiedIkBundleReaderError(
            "IK bundle document inventory is incomplete or has extra entries"
        )
    items = []
    total = 0
    for name in DOCUMENT_NAMES:
        data = _read_snapshot(files[name], MAX_DOCUMENT_BYTES, name)
        total += len(data)
        if total > MAX_TOTAL_DOCUMENT_BYTES:
            raise VerifiedIkBundleReaderError(
                "IK bundle JSON budget is exceeded"
            )
        items.append((name, data))
    return IkBundleSnapshot(root, tuple(items))


def _children(directory: Path) -> list[Path]:
    try:
        items = list(directory.iterdir())
    except OSError as exc:
        raise VerifiedIkBundleReaderError(
            "IK bundle directory cannot be enumerated"
        ) from exc
    folded = set()
    for item in items:
        key = item.name.casefold()
        if key in folded or _is_alias(item):
            raise VerifiedIkBundleReaderError(
                "IK bundle directory contains a case or path alias"
            )
        folded.add(key)
    return items


def _read_snapshot(path: Path, maximum: int, label: str) -> bytes:
    try:
        metadata = path.lstat()
        size = metadata.st_size
        if not stat.S_ISREG(metadata.st_mode) or _is_alias(path):
            raise VerifiedIkBundleReaderError(
                f"{label} is not a regular file"
            )
        if size > maximum:
            raise VerifiedIkBundleReaderError(
                f"{label} exceeds its byte limit"
            )
        with path.open("rb") as handle:
            data = handle.read(maximum + 1)
    except VerifiedIkBundleReaderError:
        raise
    except OSError as exc:
        raise VerifiedIkBundleReaderError(f"{label} cannot be read") from exc
    if len(data) != size:
        raise VerifiedIkBundleReaderError(
            f"{label} changed while being read"
        )
    return data


def _regular_file(path: Path, label: str) -> Path:
    try:
        if _is_alias(path) or not stat.S_ISREG(path.lstat().st_mode):
            raise VerifiedIkBundleReaderError(
                f"{label} is not a regular file"
            )
    except OSError as exc:
        raise VerifiedIkBundleReaderError(
            f"{label} cannot be inspected"
        ) from exc
    return path


def _real_directory(path: Path, label: str) -> Path:
    try:
        if _is_alias(path) or not stat.S_ISDIR(path.lstat().st_mode):
            raise VerifiedIkBundleReaderError(
                f"{label} is not a real directory"
            )
    except OSError as exc:
        raise VerifiedIkBundleReaderError(
            f"{label} cannot be inspected"
        ) from exc
    return path


def _is_alias(path: Path) -> bool:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            return True
        junction = getattr(path, "is_junction", None)
        if callable(junction) and junction():
            return True
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(getattr(metadata, "st_file_attributes", 0) & reparse)
    except OSError:
        return True
