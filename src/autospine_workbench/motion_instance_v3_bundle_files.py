"""Alias-safe filesystem primitives for MotionInstance v3 bundles."""

from __future__ import annotations

import os
from pathlib import Path
import stat

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .motion_instance_v3_bundle_contract import (
    DOCUMENT_LIMITS,
    DOCUMENT_NAMES,
    MAX_TOTAL_DOCUMENT_BYTES,
)
from .motion_instance_v3_staging_cleanup import (
    is_alias,
    remove_lexical_staging,
)
from .safe_input_files import SafeInputFileError, read_real_file


NAMESPACE = "body-sway-motion-instance-v3"


class MotionInstanceV3BundleFilesError(RuntimeError):
    """Raised when a v3 bundle path or file snapshot is unsafe."""


def publication_parent(
    state_root: Path, project_id: str, motion_instance_v3_sha256: str
) -> Path:
    """Create the exact non-aliased parent for one v3 primary address."""

    project, instance_sha = _address(project_id, motion_instance_v3_sha256)
    root = _safe_state_root(state_root)
    current = root
    for name in ("builds", project, NAMESPACE, instance_sha):
        current = _exact_directory(current, name)
    _require_within(root, current)
    return current


def existing_bundle_path(
    state_root: Path,
    project_id: str,
    motion_instance_v3_sha256: str,
    bundle_sha256: str,
) -> Path:
    """Resolve one explicit project/v3/bundle address without writes."""

    project, instance_sha = _address(project_id, motion_instance_v3_sha256)
    try:
        bundle_sha = require_sha256(bundle_sha256, "MotionInstance v3 bundle")
        root = Path(os.path.abspath(os.fspath(Path(state_root))))
        current = require_real_directory(
            root, "MotionInstance v3 bundle state root"
        )
        for name in (
            "builds", project, NAMESPACE, instance_sha, bundle_sha,
        ):
            child = existing_exact_child(current, name)
            if child is None:
                raise MotionInstanceV3BundleFilesError(
                    "Exact MotionInstance v3 bundle path does not exist"
                )
            current = require_real_directory(
                child, f"MotionInstance v3 bundle path {name}"
            )
        _require_within(root, current)
        return current
    except MotionInstanceV3BundleFilesError:
        raise
    except (LayerManifestError, OSError, TypeError, ValueError) as exc:
        raise MotionInstanceV3BundleFilesError(
            "MotionInstance v3 bundle address is invalid"
        ) from exc


def existing_exact_child(parent: Path, name: str) -> Path | None:
    """Find one exact-case child and reject aliases or case collisions."""

    parent = require_real_directory(parent, "MotionInstance v3 bundle parent")
    try:
        matches = [
            child for child in parent.iterdir()
            if child.name.casefold() == name.casefold()
        ]
    except OSError as exc:
        raise MotionInstanceV3BundleFilesError(
            "MotionInstance v3 hierarchy cannot be enumerated"
        ) from exc
    if not matches:
        return None
    if len(matches) != 1 or matches[0].name != name or is_alias(matches[0]):
        raise MotionInstanceV3BundleFilesError(
            f"MotionInstance v3 path is aliased: {name}"
        )
    return matches[0]


def read_bundle_files(directory: Path) -> tuple[tuple[str, bytes], ...]:
    """Read the fixed three-file inventory exactly once under limits."""

    root = require_real_directory(
        directory, "MotionInstance v3 bundle directory"
    )
    try:
        children = list(root.iterdir())
    except OSError as exc:
        raise MotionInstanceV3BundleFilesError(
            "MotionInstance v3 inventory cannot be enumerated"
        ) from exc
    by_name: dict[str, Path] = {}
    folded: set[str] = set()
    for child in children:
        key = child.name.casefold()
        if key in folded or is_alias(child):
            raise MotionInstanceV3BundleFilesError(
                "MotionInstance v3 inventory contains a case or path alias"
            )
        folded.add(key)
        try:
            if not stat.S_ISREG(child.lstat().st_mode):
                raise MotionInstanceV3BundleFilesError(
                    "MotionInstance v3 bundle contains a non-regular entry"
                )
        except OSError as exc:
            raise MotionInstanceV3BundleFilesError(
                "MotionInstance v3 entry cannot be inspected"
            ) from exc
        by_name[child.name] = child
    if set(by_name) != set(DOCUMENT_NAMES):
        raise MotionInstanceV3BundleFilesError(
            "MotionInstance v3 inventory is missing, extra, or wrong-case"
        )
    total, items = 0, []
    try:
        for index, name in enumerate(DOCUMENT_NAMES):
            data = read_real_file(by_name[name], DOCUMENT_LIMITS[index], name)
            total += len(data)
            if total > MAX_TOTAL_DOCUMENT_BYTES:
                raise MotionInstanceV3BundleFilesError(
                    "MotionInstance v3 bundle exceeds its total byte limit"
                )
            items.append((name, data))
    except SafeInputFileError as exc:
        raise MotionInstanceV3BundleFilesError(
            "MotionInstance v3 file snapshot is unsafe"
        ) from exc
    return tuple(items)


def write_file(path: Path, data: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise MotionInstanceV3BundleFilesError(
            "MotionInstance v3 bundle file cannot be written"
        ) from exc


def require_real_directory(path: Path, label: str) -> Path:
    if is_alias(path):
        raise MotionInstanceV3BundleFilesError(f"{label} is aliased")
    try:
        if not stat.S_ISDIR(path.lstat().st_mode):
            raise MotionInstanceV3BundleFilesError(
                f"{label} is not a real directory"
            )
    except OSError as exc:
        raise MotionInstanceV3BundleFilesError(
            f"{label} cannot be inspected"
        ) from exc
    return path


def sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def remove_staging(path: Path, parent: Path | None) -> None:
    """Best-effort removal without ever recursing through a resolved alias."""

    if parent is None or path.parent != parent or not _staging_name(path.name):
        return
    try:
        require_real_directory(parent, "MotionInstance v3 staging parent")
        remove_lexical_staging(path, parent)
    except (
        NotImplementedError, OSError, RuntimeError,
        MotionInstanceV3BundleFilesError,
    ):
        return


def _address(project_id: str, instance_sha256: str) -> tuple[str, str]:
    try:
        return (
            require_safe_token(project_id, "Project id"),
            require_sha256(instance_sha256, "MotionInstance v3"),
        )
    except LayerManifestError as exc:
        raise MotionInstanceV3BundleFilesError(
            "MotionInstance v3 primary address is invalid"
        ) from exc


def _safe_state_root(root: Path) -> Path:
    try:
        absolute = Path(os.path.abspath(os.fspath(Path(root))))
    except (OSError, TypeError, ValueError) as exc:
        raise MotionInstanceV3BundleFilesError(
            "MotionInstance v3 state root is invalid"
        ) from exc
    current = Path(absolute.parts[0])
    require_real_directory(current, "MotionInstance v3 state-root ancestor")
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
                raise MotionInstanceV3BundleFilesError(
                    "MotionInstance v3 state root cannot be created"
                ) from exc
        except OSError as exc:
            raise MotionInstanceV3BundleFilesError(
                "MotionInstance v3 state-root ancestor cannot be read"
            ) from exc
        current = require_real_directory(
            child, "MotionInstance v3 state-root ancestor"
        )
    return current


def _exact_directory(parent: Path, name: str) -> Path:
    found = existing_exact_child(parent, name)
    if found is None:
        try:
            (parent / name).mkdir()
        except FileExistsError:
            pass
        except OSError as exc:
            raise MotionInstanceV3BundleFilesError(
                "MotionInstance v3 hierarchy cannot be created"
            ) from exc
        found = existing_exact_child(parent, name)
    if found is None:
        raise MotionInstanceV3BundleFilesError(
            "MotionInstance v3 hierarchy disappeared"
        )
    return require_real_directory(found, f"MotionInstance v3 path {name}")


def _require_within(root: Path, path: Path) -> None:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, RuntimeError, ValueError) as exc:
        raise MotionInstanceV3BundleFilesError(
            "MotionInstance v3 hierarchy escaped its state root"
        ) from exc


def _staging_name(name: str) -> bool:
    return len(name) >= 15 and name[0] == "." and name[13] == "." \
        and all(char in "0123456789abcdef" for char in name[1:13]) \
        and bool(name[14:]) and all(
            char.isalnum() or char in "_-" for char in name[14:]
        )


__all__ = [
    "NAMESPACE", "MotionInstanceV3BundleFilesError", "existing_bundle_path",
    "existing_exact_child", "publication_parent", "read_bundle_files",
    "remove_staging", "require_real_directory", "sync_directory",
    "write_file",
]
