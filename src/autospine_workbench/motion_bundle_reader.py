"""Secure read-only boundary for exact immutable MotionIR bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import stat

from .manifest_artifacts import LayerManifestError, require_sha256
from .motion_bundle_inventory import (
    MAX_BVH_BYTES,
    MAX_BVH_MAP_BYTES,
    MAX_BVH_RUN_BYTES,
    MAX_BVH_TOTAL_DOCUMENT_BYTES,
    MAX_KIMODO_MAP_BYTES,
    MAX_KIMODO_RUN_BYTES,
    MAX_KIMODO_SOURCE_BYTES,
    MAX_KIMODO_TOTAL_DOCUMENT_BYTES,
    MAX_MOTION_BYTES,
    MAX_RAW_NPZ_BYTES,
    MAX_RUN_BYTES,
    MAX_TOTAL_DOCUMENT_BYTES,
    MotionBundleInventoryError,
    profile_for_file_names,
)
from .motion_bundle_integrity import (
    MotionBundleIntegrityError,
    MotionBundleSnapshot,
    VerifiedMotionBundle,
    verify_motion_bundle_snapshot,
)


class VerifiedMotionBundleReaderError(RuntimeError):
    """Raised when an exact motion bundle cannot be snapshotted and rebuilt."""


@dataclass(frozen=True, slots=True)
class VerifiedMotionBundleReader:
    """Resolve no aliases and verify one exact motion content address."""

    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_root", Path(self.state_root))

    def load(
        self, clip_sha256: str, bundle_sha256: str
    ) -> VerifiedMotionBundle:
        """Read each admitted file once, then reproduce all identities."""

        try:
            clip_sha = require_sha256(clip_sha256, "Motion clip")
            bundle_sha = require_sha256(bundle_sha256, "Motion bundle")
        except LayerManifestError as exc:
            raise VerifiedMotionBundleReaderError(
                "Verified motion bundle identity is invalid"
            ) from exc
        try:
            directory = _resolve_bundle(self.state_root, clip_sha, bundle_sha)
            snapshot = _snapshot(directory)
            verified = verify_motion_bundle_snapshot(
                snapshot,
                expected_clip_sha256=clip_sha,
                expected_bundle_sha256=bundle_sha,
            )
            if verified.path != directory:
                raise VerifiedMotionBundleReaderError(
                    "Verified motion bundle path changed during verification"
                )
            return verified
        except VerifiedMotionBundleReaderError:
            raise
        except (
            MotionBundleIntegrityError,
            KeyError,
            OSError,
            OverflowError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise VerifiedMotionBundleReaderError(
                f"Verified motion bundle load failed: {exc}"
            ) from exc


def _resolve_bundle(root: Path, clip_sha: str, bundle_sha: str) -> Path:
    try:
        if _is_alias(root):
            raise VerifiedMotionBundleReaderError(
                "Motion bundle state root is aliased"
            )
        trusted = root.resolve(strict=True)
        _real_directory(trusted, "Motion bundle state root")
        current = trusted
        for name in ("motions", clip_sha, bundle_sha):
            current = _exact_directory(current, name)
        current.relative_to(trusted)
        return current
    except VerifiedMotionBundleReaderError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise VerifiedMotionBundleReaderError(
            "Exact motion bundle path was not found"
        ) from exc


def _exact_directory(parent: Path, name: str) -> Path:
    _real_directory(parent, "Motion bundle parent")
    matches = [
        item for item in _children(parent)
        if item.name.casefold() == name.casefold()
    ]
    if len(matches) != 1 or matches[0].name != name:
        raise VerifiedMotionBundleReaderError(
            f"Motion bundle path is missing or case-mismatched: {name}"
        )
    return _real_directory(matches[0], f"Motion bundle path {name}")


def _snapshot(root: Path) -> MotionBundleSnapshot:
    _real_directory(root, "Motion bundle directory")
    children = _children(root)
    files = {child.name: _regular_file(child, child.name) for child in children}
    try:
        profile = profile_for_file_names(set(files))
    except MotionBundleInventoryError as exc:
        raise VerifiedMotionBundleReaderError(
            "Motion bundle inventory has missing or unexpected entries"
        ) from exc
    limits = profile.limit_by_name
    limits.update({
        "source.bvh": MAX_BVH_BYTES,
        "source.npz": MAX_RAW_NPZ_BYTES,
        "sidecar.json": MAX_KIMODO_SOURCE_BYTES,
        "map.json": (
            MAX_KIMODO_MAP_BYTES
            if profile.source_kind == "kimodo_npz" else MAX_BVH_MAP_BYTES
        ),
        "motion.json": MAX_MOTION_BYTES,
        "run-manifest.json": (
            MAX_RUN_BYTES if profile.source_kind == "builtin"
            else MAX_KIMODO_RUN_BYTES if profile.source_kind == "kimodo_npz"
            else MAX_BVH_RUN_BYTES
        ),
    })
    total_limit = (
        MAX_TOTAL_DOCUMENT_BYTES
        if profile.source_kind == "builtin"
        else MAX_KIMODO_TOTAL_DOCUMENT_BYTES
        if profile.source_kind == "kimodo_npz"
        else MAX_BVH_TOTAL_DOCUMENT_BYTES
    )
    items, total = [], 0
    for name in profile.names:
        data = _read_snapshot(files[name], limits[name], name)
        total += len(data)
        if total > total_limit:
            raise VerifiedMotionBundleReaderError(
                "Motion bundle byte budget is exceeded"
            )
        items.append((name, data))
    return MotionBundleSnapshot(root, tuple(items))


def _children(directory: Path) -> list[Path]:
    try:
        items = list(directory.iterdir())
    except OSError as exc:
        raise VerifiedMotionBundleReaderError(
            "Motion bundle directory cannot be enumerated"
        ) from exc
    folded: set[str] = set()
    for item in items:
        key = item.name.casefold()
        if key in folded or _is_alias(item):
            raise VerifiedMotionBundleReaderError(
                "Motion bundle directory contains a case or path alias"
            )
        folded.add(key)
    return items


def _read_snapshot(path: Path, maximum: int, label: str) -> bytes:
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or _is_alias(path):
            raise VerifiedMotionBundleReaderError(
                f"{label} is not a regular file"
            )
        if metadata.st_size > maximum:
            raise VerifiedMotionBundleReaderError(
                f"{label} exceeds its byte limit"
            )
        with path.open("rb") as handle:
            data = handle.read(maximum + 1)
    except VerifiedMotionBundleReaderError:
        raise
    except OSError as exc:
        raise VerifiedMotionBundleReaderError(f"{label} cannot be read") from exc
    if len(data) > maximum or len(data) != metadata.st_size:
        raise VerifiedMotionBundleReaderError(
            f"{label} changed while being read"
        )
    return data


def _regular_file(path: Path, label: str) -> Path:
    try:
        if _is_alias(path) or not stat.S_ISREG(path.lstat().st_mode):
            raise VerifiedMotionBundleReaderError(
                f"{label} is not a regular file"
            )
        if path.resolve(strict=True) != path:
            raise VerifiedMotionBundleReaderError(f"{label} is path-aliased")
    except VerifiedMotionBundleReaderError:
        raise
    except (OSError, RuntimeError) as exc:
        raise VerifiedMotionBundleReaderError(
            f"{label} cannot be inspected"
        ) from exc
    return path


def _real_directory(path: Path, label: str) -> Path:
    try:
        if _is_alias(path) or not stat.S_ISDIR(path.lstat().st_mode):
            raise VerifiedMotionBundleReaderError(f"{label} is not a real directory")
        resolved = path.resolve(strict=True)
        if resolved != path:
            raise VerifiedMotionBundleReaderError(f"{label} is path-aliased")
        return resolved
    except VerifiedMotionBundleReaderError:
        raise
    except (OSError, RuntimeError) as exc:
        raise VerifiedMotionBundleReaderError(
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
