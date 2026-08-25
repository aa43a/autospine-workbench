"""Alias-safe filesystem primitives for immutable Spine 4.2 bundles."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat

from .spine42_bundle_contract import DOCUMENT_LIMITS, DOCUMENT_NAMES
from .safe_input_files import SafeInputFileError, read_real_file


class Spine42BundleFilesError(RuntimeError):
    """Raised when a bundle path or file snapshot is unsafe."""


def publication_parent(
    state_root: Path, project_id: str, skeleton_json_sha256: str
) -> Path:
    """Create and return the exact non-aliased publication parent."""

    root = _safe_state_root(state_root)
    current = root
    for name in ("builds", project_id, "spine42", skeleton_json_sha256):
        current = _exact_directory(current, name)
    _require_within(root, current)
    return current


def existing_bundle_path(
    state_root: Path,
    project_id: str,
    skeleton_json_sha256: str,
    bundle_sha256: str,
) -> Path:
    """Resolve an existing exact-case hierarchy without creating any path."""

    root = Path(os.path.abspath(os.fspath(Path(state_root))))
    current = require_real_directory(root, "Spine state root")
    for name in ("builds", project_id, "spine42", skeleton_json_sha256,
                 bundle_sha256):
        child = existing_exact_child(current, name)
        if child is None:
            raise Spine42BundleFilesError("Spine bundle path does not exist")
        current = require_real_directory(child, f"Spine bundle path {name}")
    _require_within(root, current)
    return current


def existing_exact_child(parent: Path, name: str) -> Path | None:
    parent = require_real_directory(parent, "Spine bundle parent")
    try:
        matches = [child for child in parent.iterdir()
                   if child.name.casefold() == name.casefold()]
    except OSError as exc:
        raise Spine42BundleFilesError("Spine bundle hierarchy cannot be read") from exc
    if not matches:
        return None
    if len(matches) != 1 or matches[0].name != name or is_alias(matches[0]):
        raise Spine42BundleFilesError(f"Spine bundle path is aliased: {name}")
    return matches[0]


def read_bundle_files(directory: Path) -> tuple[tuple[str, bytes], ...]:
    """Read the exact fixed inventory once, rejecting aliases and extra files."""

    root = require_real_directory(directory, "Spine bundle directory")
    try:
        children = list(root.iterdir())
    except OSError as exc:
        raise Spine42BundleFilesError("Spine bundle inventory cannot be read") from exc
    by_name: dict[str, Path] = {}
    folded: set[str] = set()
    for child in children:
        key = child.name.casefold()
        if key in folded or is_alias(child):
            raise Spine42BundleFilesError("Spine bundle inventory contains an alias")
        folded.add(key)
        try:
            if not stat.S_ISREG(child.lstat().st_mode):
                raise Spine42BundleFilesError(
                    "Spine bundle contains a non-regular entry"
                )
        except OSError as exc:
            raise Spine42BundleFilesError(
                "Spine bundle entry cannot be inspected"
            ) from exc
        by_name[child.name] = child
    if set(by_name) != set(DOCUMENT_NAMES):
        raise Spine42BundleFilesError(
            "Spine bundle inventory is incomplete or has extra entries"
        )
    try:
        return tuple(
            (name, read_real_file(by_name[name], DOCUMENT_LIMITS[index], name))
            for index, name in enumerate(DOCUMENT_NAMES)
        )
    except SafeInputFileError as exc:
        raise Spine42BundleFilesError("Spine bundle file snapshot is unsafe") from exc


def write_file(path: Path, data: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise Spine42BundleFilesError("Spine bundle file cannot be written") from exc


def require_real_directory(path: Path, label: str) -> Path:
    if is_alias(path):
        raise Spine42BundleFilesError(f"{label} is aliased")
    try:
        if not stat.S_ISDIR(path.lstat().st_mode):
            raise Spine42BundleFilesError(f"{label} is not a real directory")
    except OSError as exc:
        raise Spine42BundleFilesError(f"{label} cannot be inspected") from exc
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
    """Remove only a validated staging child created by this bundle store."""

    if parent is None or path.parent != parent or not _staging_name(path.name):
        return
    try:
        require_real_directory(parent, "Spine bundle staging parent")
        require_real_directory(path, "Spine bundle staging directory")
        if path.resolve(strict=True).parent != parent.resolve(strict=True):
            return
        _require_within(parent, path)
    except (OSError, RuntimeError, Spine42BundleFilesError):
        return
    try:
        shutil.rmtree(path.resolve(strict=True))
    except OSError:
        return


def _safe_state_root(root: Path) -> Path:
    try:
        absolute = Path(os.path.abspath(os.fspath(Path(root))))
    except (OSError, TypeError, ValueError) as exc:
        raise Spine42BundleFilesError("Spine state root is invalid") from exc
    current = Path(absolute.parts[0])
    require_real_directory(current, "Spine state-root ancestor")
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
                raise Spine42BundleFilesError(
                    "Spine state root cannot be created"
                ) from exc
        except OSError as exc:
            raise Spine42BundleFilesError(
                "Spine state-root ancestor cannot be read"
            ) from exc
        current = require_real_directory(child, "Spine state-root ancestor")
    return current


def _exact_directory(parent: Path, name: str) -> Path:
    found = existing_exact_child(parent, name)
    if found is None:
        try:
            (parent / name).mkdir()
        except FileExistsError:
            pass
        except OSError as exc:
            raise Spine42BundleFilesError(
                "Spine bundle hierarchy cannot be created"
            ) from exc
        found = existing_exact_child(parent, name)
    if found is None:
        raise Spine42BundleFilesError("Spine bundle hierarchy disappeared")
    return require_real_directory(found, f"Spine bundle path {name}")


def _require_within(root: Path, path: Path) -> None:
    try:
        trusted = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        resolved.relative_to(trusted)
    except (OSError, RuntimeError, ValueError) as exc:
        raise Spine42BundleFilesError(
            "Spine bundle hierarchy escaped its state root"
        ) from exc


def _staging_name(name: str) -> bool:
    return len(name) >= 15 and name[0] == "." and name[13] == "." \
        and all(character in "0123456789abcdef" for character in name[1:13]) \
        and bool(name[14:]) and all(
            character.isalnum() or character in "_-" for character in name[14:]
        )
