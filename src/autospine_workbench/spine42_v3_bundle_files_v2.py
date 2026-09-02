"""Version-isolated filesystem addresses for P10.7a v2 bundles."""

from __future__ import annotations

import os
from pathlib import Path

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .spine42_v3_bundle_files import (
    Spine42V3BundleFilesError,
    existing_exact_child,
    read_bundle_files,
    remove_staging,
    require_real_directory,
    sync_directory,
    write_file,
)


NAMESPACE = "spine42-v3-v2"


class Spine42V3BundleFilesV2Error(RuntimeError):
    """Raised when a P10.7a v2 path is unsafe or ambiguous."""


def publication_parent(
    state_root: Path,
    project_id: str,
    skeleton_json_sha256: str,
) -> Path:
    """Create the isolated parent for one v2 skeleton address."""

    project, skeleton_sha = _address(project_id, skeleton_json_sha256)
    root = _safe_state_root(state_root)
    current = root
    for name in ("builds", project, NAMESPACE, skeleton_sha):
        current = _exact_directory(current, name)
    _require_within(root, current)
    return current


def existing_bundle_path(
    state_root: Path,
    project_id: str,
    skeleton_json_sha256: str,
    bundle_sha256: str,
) -> Path:
    """Resolve one exact v2 address without creating any directory."""

    project, skeleton_sha = _address(project_id, skeleton_json_sha256)
    try:
        bundle_sha = require_sha256(bundle_sha256, "Spine v3 v2 bundle")
        root = Path(os.path.abspath(os.fspath(Path(state_root))))
        current = require_real_directory(root, "Spine v3 v2 state root")
        for name in ("builds", project, NAMESPACE, skeleton_sha, bundle_sha):
            child = existing_exact_child(current, name)
            if child is None:
                raise Spine42V3BundleFilesV2Error(
                    "Exact Spine v3 v2 bundle path does not exist"
                )
            current = require_real_directory(
                child, f"Spine v3 v2 bundle path {name}"
            )
        _require_within(root, current)
        return current
    except Spine42V3BundleFilesV2Error:
        raise
    except (
        LayerManifestError, OSError, Spine42V3BundleFilesError,
        TypeError, ValueError,
    ) as exc:
        raise Spine42V3BundleFilesV2Error(
            "Spine v3 v2 bundle address is invalid"
        ) from exc


def _address(project_id: str, skeleton_sha256: str) -> tuple[str, str]:
    try:
        return (
            require_safe_token(project_id, "Project id"),
            require_sha256(skeleton_sha256, "Spine v3 v2 skeleton"),
        )
    except LayerManifestError as exc:
        raise Spine42V3BundleFilesV2Error(
            "Spine v3 v2 primary address is invalid"
        ) from exc


def _safe_state_root(root: Path) -> Path:
    try:
        absolute = Path(os.path.abspath(os.fspath(Path(root))))
    except (OSError, TypeError, ValueError) as exc:
        raise Spine42V3BundleFilesV2Error(
            "Spine v3 v2 state root is invalid"
        ) from exc
    current = Path(absolute.parts[0])
    require_real_directory(current, "Spine v3 v2 state-root ancestor")
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
                raise Spine42V3BundleFilesV2Error(
                    "Spine v3 v2 state root cannot be created"
                ) from exc
        current = require_real_directory(
            child, "Spine v3 v2 state-root ancestor"
        )
    return current


def _exact_directory(parent: Path, name: str) -> Path:
    found = existing_exact_child(parent, name)
    if found is None:
        try:
            (parent / name).mkdir()
        except FileExistsError:
            pass
        found = existing_exact_child(parent, name)
    if found is None:
        raise Spine42V3BundleFilesV2Error(
            "Spine v3 v2 hierarchy disappeared"
        )
    return require_real_directory(found, f"Spine v3 v2 path {name}")


def _require_within(root: Path, path: Path) -> None:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, RuntimeError, ValueError) as exc:
        raise Spine42V3BundleFilesV2Error(
            "Spine v3 v2 hierarchy escaped its state root"
        ) from exc


__all__ = [
    "NAMESPACE", "Spine42V3BundleFilesV2Error", "existing_bundle_path",
    "existing_exact_child", "publication_parent", "read_bundle_files",
    "remove_staging", "require_real_directory", "sync_directory",
    "write_file",
]
