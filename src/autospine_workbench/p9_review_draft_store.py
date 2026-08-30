"""Alias-safe atomic publication for non-authoritative P9 review drafts."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
from typing import Mapping

from .atomic_staging import create_same_parent_staging
from .manifest_artifacts import require_safe_token
from .safe_input_files import SafeInputFileError, read_real_file
from .spine42_bundle_files import (
    Spine42BundleFilesError,
    existing_exact_child,
    is_alias,
    remove_staging,
    require_real_directory,
    sync_directory,
    write_file,
)


class P9ReviewDraftStoreError(RuntimeError):
    """Raised when a draft namespace cannot be published exactly."""


def require_real_state_root(value: Path) -> Path:
    """Return an existing state root after checking every path component."""

    try:
        absolute = Path(os.path.abspath(os.fspath(Path(value))))
        current = Path(absolute.parts[0])
        require_real_directory(current, "P9 draft state-root ancestor")
        for name in absolute.parts[1:]:
            current = require_real_directory(
                current / name, "P9 draft state-root ancestor"
            )
        return current
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise P9ReviewDraftStoreError(
            "P9 draft state root is absent or unsafe"
        ) from exc


def publish_p9_review_draft(
    state: Path,
    namespace: str,
    project: str,
    files: Mapping[str, bytes],
) -> bool:
    """Publish one fixed draft inventory; return whether it was reused."""

    parent: Path | None = None
    staging: Path | None = None
    try:
        namespace = require_safe_token(namespace, "P9 draft namespace")
        project = require_safe_token(project, "P9 draft project")
        if project.casefold() == "shared":
            raise P9ReviewDraftStoreError(
                "P9 draft project collides with the shared directory"
            )
        root = require_real_state_root(state)
        parent = _ensure_directory(root, "reviews")
        expected = _expected_inventory(project, files)
        destination = existing_exact_child(parent, namespace)
        if destination is not None:
            _require_exact(destination, expected)
            return True
        address = _inventory_sha256(expected)
        staging = create_same_parent_staging(
            parent, prefix=f".{address[:12]}.",
        )
        require_real_directory(staging, "P9 draft staging directory")
        for directory, entries in expected.items():
            child = staging / directory
            child.mkdir()
            require_real_directory(child, "P9 draft staging child")
            for name, payload in entries.items():
                write_file(child / name, payload)
            sync_directory(child)
        sync_directory(staging)
        _require_exact(staging, expected)
        try:
            os.rename(staging, parent / namespace)
            destination = parent / namespace
            staging = None
            reused = False
            sync_directory(parent)
        except OSError:
            destination = existing_exact_child(parent, namespace)
            if destination is None:
                raise
            reused = True
        _require_exact(destination, expected)
        return reused
    except P9ReviewDraftStoreError:
        raise
    except (
        OSError,
        RuntimeError,
        SafeInputFileError,
        Spine42BundleFilesError,
        TypeError,
        ValueError,
    ) as exc:
        raise P9ReviewDraftStoreError(
            "P9 review draft could not be published exactly"
        ) from exc
    finally:
        if staging is not None:
            remove_staging(staging, parent)


def _ensure_directory(parent: Path, name: str) -> Path:
    found = existing_exact_child(parent, name)
    if found is None:
        try:
            (parent / name).mkdir()
        except FileExistsError:
            pass
        found = existing_exact_child(parent, name)
    if found is None:
        raise P9ReviewDraftStoreError("P9 draft hierarchy disappeared")
    return require_real_directory(found, "P9 draft hierarchy")


def _expected_inventory(
    project: str, files: Mapping[str, bytes],
) -> dict[str, dict[str, bytes]]:
    expected = {
        "shared": {"kimodo-policy-evidence.json"},
        project: {
            "depth-pair-policy.proposal.json",
            "foot-lock-candidates.json",
            "draft-manifest.json",
        },
    }
    actual: dict[str, dict[str, bytes]] = {name: {} for name in expected}
    for relative, payload in files.items():
        path = Path(relative)
        if len(path.parts) != 2 or path.parts[0] not in expected \
                or path.parts[1] not in expected[path.parts[0]] \
                or type(payload) is not bytes:
            raise P9ReviewDraftStoreError(
                "P9 draft publication inventory is unsupported"
            )
        actual[path.parts[0]][path.parts[1]] = payload
    if any(set(actual[name]) != names for name, names in expected.items()):
        raise P9ReviewDraftStoreError(
            "P9 draft publication inventory is incomplete"
        )
    return actual


def _require_exact(
    root: Path, expected: Mapping[str, Mapping[str, bytes]],
) -> None:
    directory = require_real_directory(root, "P9 draft namespace")
    children = _entries(directory, len(expected))
    if set(children) != set(expected):
        raise P9ReviewDraftStoreError(
            "P9 draft namespace directory inventory differs"
        )
    for name, files in expected.items():
        child = children[name]
        require_real_directory(child, "P9 draft evidence directory")
        entries = _entries(child, len(files))
        if set(entries) != set(files):
            raise P9ReviewDraftStoreError(
                "P9 draft namespace file inventory differs"
            )
        for filename, payload in files.items():
            path = entries[filename]
            try:
                mode = path.lstat().st_mode
            except OSError as exc:
                raise P9ReviewDraftStoreError(
                    "P9 draft evidence cannot be inspected"
                ) from exc
            if is_alias(path) or not stat.S_ISREG(mode) \
                    or read_real_file(path, len(payload), filename) != payload:
                raise P9ReviewDraftStoreError(
                    "P9 draft evidence bytes differ"
                )


def _entries(directory: Path, maximum: int) -> dict[str, Path]:
    try:
        children = []
        for child in directory.iterdir():
            children.append(child)
            if len(children) > maximum:
                raise P9ReviewDraftStoreError(
                    "P9 draft inventory contains extra entries"
                )
    except P9ReviewDraftStoreError:
        raise
    except OSError as exc:
        raise P9ReviewDraftStoreError(
            "P9 draft inventory cannot be read"
        ) from exc
    folded = {child.name.casefold() for child in children}
    if len(folded) != len(children) or any(is_alias(child) for child in children):
        raise P9ReviewDraftStoreError(
            "P9 draft inventory contains an alias or case collision"
        )
    return {child.name: child for child in children}


def _inventory_sha256(
    expected: Mapping[str, Mapping[str, bytes]],
) -> str:
    digest = hashlib.sha256()
    for directory, files in sorted(expected.items()):
        for name, payload in sorted(files.items()):
            digest.update(f"{directory}/{name}\0{len(payload)}\0".encode("utf-8"))
            digest.update(payload)
    return digest.hexdigest()


__all__ = [
    "P9ReviewDraftStoreError",
    "publish_p9_review_draft",
    "require_real_state_root",
]
