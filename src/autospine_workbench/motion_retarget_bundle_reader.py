"""Secure read-only boundary for exact immutable P5 retarget bundles."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat

from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .motion_retarget_bundle_contract import (
    DOCUMENT_NAMES,
    MAX_INSTANCE_BYTES,
    MAX_MESH_REPORT_BYTES,
    MAX_RETARGET_REPORT_BYTES,
    MAX_RUN_BYTES,
    MAX_TARGET_PROFILE_BYTES,
    MAX_TOTAL_DOCUMENT_BYTES,
)
from .motion_retarget_bundle_integrity import (
    MotionRetargetBundleIntegrityError,
    MotionRetargetBundleSnapshot,
    VerifiedMotionRetargetBundle,
    verify_motion_retarget_bundle_snapshot,
)
from .mesh_bundle_integrity import VerifiedMeshBundle


_LIMITS = (
    MAX_TARGET_PROFILE_BYTES,
    MAX_INSTANCE_BYTES,
    MAX_RUN_BYTES,
    MAX_RETARGET_REPORT_BYTES,
    MAX_MESH_REPORT_BYTES,
)


class VerifiedMotionRetargetBundleReaderError(RuntimeError):
    """Raised when an exact P5 bundle cannot be snapshotted and rebuilt."""


@dataclass(frozen=True, slots=True)
class VerifiedMotionRetargetBundleReader:
    """Resolve no aliases and verify one exact P5 content address."""

    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def load(
        self,
        project_id: str,
        instance_sha256: str,
        bundle_sha256: str,
        *,
        mesh_bundle: VerifiedMeshBundle | None = None,
    ) -> VerifiedMotionRetargetBundle:
        """Read every admitted file once, then reproduce all evidence."""

        try:
            project = require_safe_token(project_id, "Project id")
            instance_sha = require_sha256(instance_sha256, "Motion instance")
            bundle_sha = require_sha256(bundle_sha256, "Retarget bundle")
        except LayerManifestError as exc:
            raise VerifiedMotionRetargetBundleReaderError(
                "Verified retarget bundle identity is invalid"
            ) from exc
        try:
            directory = _resolve_bundle(
                self.state_root, project, instance_sha, bundle_sha
            )
            snapshot = _snapshot(directory)
            verified = verify_motion_retarget_bundle_snapshot(
                snapshot,
                state_root=self.state_root,
                expected_project_id=project,
                expected_instance_sha256=instance_sha,
                expected_bundle_sha256=bundle_sha,
                mesh_bundle=mesh_bundle,
            )
            if verified.path != directory:
                raise VerifiedMotionRetargetBundleReaderError(
                    "Verified retarget bundle path changed during verification"
                )
            return verified
        except VerifiedMotionRetargetBundleReaderError:
            raise
        except (
            MotionRetargetBundleIntegrityError,
            KeyError,
            OSError,
            OverflowError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise VerifiedMotionRetargetBundleReaderError(
                f"Verified retarget bundle load failed: {exc}"
            ) from exc


def _resolve_bundle(
    root: Path, project: str, instance_sha: str, bundle_sha: str
) -> Path:
    try:
        if _is_alias(root):
            raise VerifiedMotionRetargetBundleReaderError(
                "Retarget bundle state root is aliased"
            )
        trusted = root.resolve(strict=True)
        _real_directory(trusted, "Retarget bundle state root")
        current = trusted
        for name in (
            "builds", project, "motion-instances", instance_sha, bundle_sha,
        ):
            current = _exact_directory(current, name)
        current.relative_to(trusted)
        return current
    except VerifiedMotionRetargetBundleReaderError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise VerifiedMotionRetargetBundleReaderError(
            "Exact retarget bundle path was not found"
        ) from exc


def _exact_directory(parent: Path, name: str) -> Path:
    _real_directory(parent, "Retarget bundle parent")
    matches = [
        item for item in _children(parent)
        if item.name.casefold() == name.casefold()
    ]
    if len(matches) != 1 or matches[0].name != name:
        raise VerifiedMotionRetargetBundleReaderError(
            f"Retarget bundle path is missing or case-mismatched: {name}"
        )
    return _real_directory(matches[0], f"Retarget bundle path {name}")


def _snapshot(root: Path) -> MotionRetargetBundleSnapshot:
    _real_directory(root, "Retarget bundle directory")
    children = _children(root)
    files = {child.name: _regular_file(child, child.name) for child in children}
    if set(files) != set(DOCUMENT_NAMES):
        raise VerifiedMotionRetargetBundleReaderError(
            "Retarget bundle inventory has missing or unexpected entries"
        )
    items = []
    total = 0
    for index, name in enumerate(DOCUMENT_NAMES):
        data = _read_snapshot(files[name], _LIMITS[index], name)
        total += len(data)
        if total > MAX_TOTAL_DOCUMENT_BYTES:
            raise VerifiedMotionRetargetBundleReaderError(
                "Retarget bundle byte budget is exceeded"
            )
        items.append((name, data))
    return MotionRetargetBundleSnapshot(root, tuple(items))


def _children(directory: Path) -> list[Path]:
    try:
        items = list(directory.iterdir())
    except OSError as exc:
        raise VerifiedMotionRetargetBundleReaderError(
            "Retarget bundle directory cannot be enumerated"
        ) from exc
    folded: set[str] = set()
    for item in items:
        key = item.name.casefold()
        if key in folded or _is_alias(item):
            raise VerifiedMotionRetargetBundleReaderError(
                "Retarget bundle directory contains a case or path alias"
            )
        folded.add(key)
    return items


def _read_snapshot(path: Path, maximum: int, label: str) -> bytes:
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or _is_alias(path):
            raise VerifiedMotionRetargetBundleReaderError(
                f"{label} is not a regular file"
            )
        if before.st_size > maximum:
            raise VerifiedMotionRetargetBundleReaderError(
                f"{label} exceeds its byte limit"
            )
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            data = handle.read(maximum + 1)
            finished = os.fstat(handle.fileno())
        after = path.lstat()
    except VerifiedMotionRetargetBundleReaderError:
        raise
    except OSError as exc:
        raise VerifiedMotionRetargetBundleReaderError(
            f"{label} cannot be read"
        ) from exc
    if (
        len(data) > maximum
        or len(data) != before.st_size
        or _file_identity(before) != _file_identity(opened)
        or _file_identity(opened) != _file_identity(finished)
        or _file_identity(finished) != _file_identity(after)
    ):
        raise VerifiedMotionRetargetBundleReaderError(
            f"{label} changed while being read"
        )
    return data


def _file_identity(value) -> tuple[int, ...]:
    return (
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        getattr(value, "st_dev", 0),
        getattr(value, "st_ino", 0),
    )


def _regular_file(path: Path, label: str) -> Path:
    try:
        if _is_alias(path) or not stat.S_ISREG(path.lstat().st_mode):
            raise VerifiedMotionRetargetBundleReaderError(
                f"{label} is not a regular file"
            )
        if path.resolve(strict=True) != path:
            raise VerifiedMotionRetargetBundleReaderError(f"{label} is path-aliased")
    except VerifiedMotionRetargetBundleReaderError:
        raise
    except (OSError, RuntimeError) as exc:
        raise VerifiedMotionRetargetBundleReaderError(
            f"{label} cannot be inspected"
        ) from exc
    return path


def _real_directory(path: Path, label: str) -> Path:
    try:
        if _is_alias(path) or not stat.S_ISDIR(path.lstat().st_mode):
            raise VerifiedMotionRetargetBundleReaderError(
                f"{label} is not a real directory"
            )
        resolved = path.resolve(strict=True)
        if resolved != path:
            raise VerifiedMotionRetargetBundleReaderError(f"{label} is path-aliased")
        return resolved
    except VerifiedMotionRetargetBundleReaderError:
        raise
    except (OSError, RuntimeError) as exc:
        raise VerifiedMotionRetargetBundleReaderError(
            f"{label} cannot be inspected"
        ) from exc


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
