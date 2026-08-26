"""Alias-safe filesystem primitives for reviewed-motion bundles."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat

from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .reviewed_motion_bundle_contract import (
    DOCUMENT_LIMITS,
    DOCUMENT_NAMES,
    MAX_TOTAL_DOCUMENT_BYTES,
)
from .safe_input_files import SafeInputFileError, read_real_file


NAMESPACE = "reviewed-motion-instances"


class ReviewedMotionBundleFilesError(RuntimeError):
    """Raised when a reviewed-motion path or snapshot is unsafe."""


def publication_parent(
    state_root: Path, project_id: str, motion_instance_v2_sha256: str
) -> Path:
    """Create the exact non-aliased parent for one v2 primary address."""

    project, instance_sha = _address(project_id, motion_instance_v2_sha256)
    root = _safe_state_root(state_root)
    current = root
    for name in ("builds", project, NAMESPACE, instance_sha):
        current = _exact_directory(current, name)
    _require_within(root, current)
    return current


def existing_bundle_path(
    state_root: Path,
    project_id: str,
    motion_instance_v2_sha256: str,
    bundle_sha256: str,
) -> Path:
    """Resolve only one explicit project/v2/bundle address without writes."""

    project, instance_sha = _address(project_id, motion_instance_v2_sha256)
    try:
        bundle_sha = require_sha256(bundle_sha256, "Reviewed-motion bundle")
        root = Path(os.path.abspath(os.fspath(Path(state_root))))
        current = require_real_directory(root, "Reviewed-motion state root")
        for name in (
            "builds", project, NAMESPACE, instance_sha, bundle_sha,
        ):
            child = existing_exact_child(current, name)
            if child is None:
                raise ReviewedMotionBundleFilesError(
                    "Exact reviewed-motion bundle path does not exist"
                )
            current = require_real_directory(
                child, f"Reviewed-motion bundle path {name}"
            )
        _require_within(root, current)
        return current
    except ReviewedMotionBundleFilesError:
        raise
    except (LayerManifestError, OSError, TypeError, ValueError) as exc:
        raise ReviewedMotionBundleFilesError(
            "Reviewed-motion bundle address is invalid"
        ) from exc


def existing_exact_child(parent: Path, name: str) -> Path | None:
    """Find one exact-case child and reject case aliases and reparse entries."""

    parent = require_real_directory(parent, "Reviewed-motion bundle parent")
    try:
        matches = [
            child for child in parent.iterdir()
            if child.name.casefold() == name.casefold()
        ]
    except OSError as exc:
        raise ReviewedMotionBundleFilesError(
            "Reviewed-motion hierarchy cannot be enumerated"
        ) from exc
    if not matches:
        return None
    if len(matches) != 1 or matches[0].name != name or is_alias(matches[0]):
        raise ReviewedMotionBundleFilesError(
            f"Reviewed-motion path is aliased: {name}"
        )
    return matches[0]


def read_bundle_files(directory: Path) -> tuple[tuple[str, bytes], ...]:
    """Read every fixed-inventory file exactly once under individual limits."""

    root = require_real_directory(directory, "Reviewed-motion bundle directory")
    try:
        children = list(root.iterdir())
    except OSError as exc:
        raise ReviewedMotionBundleFilesError(
            "Reviewed-motion inventory cannot be enumerated"
        ) from exc
    by_name: dict[str, Path] = {}
    folded: set[str] = set()
    for child in children:
        key = child.name.casefold()
        if key in folded or is_alias(child):
            raise ReviewedMotionBundleFilesError(
                "Reviewed-motion inventory contains a case or path alias"
            )
        folded.add(key)
        try:
            if not stat.S_ISREG(child.lstat().st_mode):
                raise ReviewedMotionBundleFilesError(
                    "Reviewed-motion bundle contains a non-regular entry"
                )
        except OSError as exc:
            raise ReviewedMotionBundleFilesError(
                "Reviewed-motion entry cannot be inspected"
            ) from exc
        by_name[child.name] = child
    if set(by_name) != set(DOCUMENT_NAMES):
        raise ReviewedMotionBundleFilesError(
            "Reviewed-motion inventory is missing, extra, or wrong-case"
        )
    total, items = 0, []
    try:
        for index, name in enumerate(DOCUMENT_NAMES):
            data = read_real_file(by_name[name], DOCUMENT_LIMITS[index], name)
            total += len(data)
            if total > MAX_TOTAL_DOCUMENT_BYTES:
                raise ReviewedMotionBundleFilesError(
                    "Reviewed-motion bundle exceeds its total byte limit"
                )
            items.append((name, data))
    except SafeInputFileError as exc:
        raise ReviewedMotionBundleFilesError(
            "Reviewed-motion file snapshot is unsafe"
        ) from exc
    return tuple(items)


def write_file(path: Path, data: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ReviewedMotionBundleFilesError(
            "Reviewed-motion bundle file cannot be written"
        ) from exc


def require_real_directory(path: Path, label: str) -> Path:
    if is_alias(path):
        raise ReviewedMotionBundleFilesError(f"{label} is aliased")
    try:
        if not stat.S_ISDIR(path.lstat().st_mode):
            raise ReviewedMotionBundleFilesError(f"{label} is not a real directory")
    except OSError as exc:
        raise ReviewedMotionBundleFilesError(f"{label} cannot be inspected") from exc
    return path


def is_alias(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    if stat.S_ISLNK(info.st_mode):
        return True
    junction = getattr(path, "is_junction", None)
    try:
        if callable(junction) and junction():
            return True
    except OSError:
        return True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & reparse)


def sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def remove_staging(path: Path, parent: Path | None) -> None:
    """Remove only a validated staging child below its exact parent."""

    if parent is None or path.parent != parent or not _staging_name(path.name):
        return
    try:
        require_real_directory(parent, "Reviewed-motion staging parent")
        require_real_directory(path, "Reviewed-motion staging directory")
        if path.resolve(strict=True).parent != parent.resolve(strict=True):
            return
        _require_within(parent, path)
        shutil.rmtree(path.resolve(strict=True))
    except (OSError, RuntimeError, ReviewedMotionBundleFilesError):
        return


def _address(project_id: str, instance_sha256: str) -> tuple[str, str]:
    try:
        return (
            require_safe_token(project_id, "Project id"),
            require_sha256(instance_sha256, "MotionInstance v2"),
        )
    except LayerManifestError as exc:
        raise ReviewedMotionBundleFilesError(
            "Reviewed-motion primary address is invalid"
        ) from exc


def _safe_state_root(root: Path) -> Path:
    try:
        absolute = Path(os.path.abspath(os.fspath(Path(root))))
    except (OSError, TypeError, ValueError) as exc:
        raise ReviewedMotionBundleFilesError(
            "Reviewed-motion state root is invalid"
        ) from exc
    current = Path(absolute.parts[0])
    require_real_directory(current, "Reviewed-motion state-root ancestor")
    for name in absolute.parts[1:]:
        child = current / name
        try:
            child.lstat()
        except FileNotFoundError:
            try:
                child.mkdir()
            except FileExistsError:
                pass
            except OSError as exc:
                raise ReviewedMotionBundleFilesError(
                    "Reviewed-motion state root cannot be created"
                ) from exc
        except OSError as exc:
            raise ReviewedMotionBundleFilesError(
                "Reviewed-motion state-root ancestor cannot be read"
            ) from exc
        current = require_real_directory(child, "Reviewed-motion state-root ancestor")
    return current


def _exact_directory(parent: Path, name: str) -> Path:
    found = existing_exact_child(parent, name)
    if found is None:
        try:
            (parent / name).mkdir()
        except FileExistsError:
            pass
        except OSError as exc:
            raise ReviewedMotionBundleFilesError(
                "Reviewed-motion hierarchy cannot be created"
            ) from exc
        found = existing_exact_child(parent, name)
    if found is None:
        raise ReviewedMotionBundleFilesError(
            "Reviewed-motion hierarchy disappeared"
        )
    return require_real_directory(found, f"Reviewed-motion path {name}")


def _require_within(root: Path, path: Path) -> None:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, RuntimeError, ValueError) as exc:
        raise ReviewedMotionBundleFilesError(
            "Reviewed-motion hierarchy escaped its state root"
        ) from exc


def _staging_name(name: str) -> bool:
    return len(name) >= 15 and name[0] == "." and name[13] == "." \
        and all(character in "0123456789abcdef" for character in name[1:13]) \
        and bool(name[14:]) and all(
            character.isalnum() or character in "_-" for character in name[14:]
        )
