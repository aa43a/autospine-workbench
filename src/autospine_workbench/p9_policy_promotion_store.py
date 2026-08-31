"""Atomic immutable publication for a promoted P9 review package."""

from __future__ import annotations

import os
from pathlib import Path
import stat
from typing import Mapping

from .atomic_staging import create_same_parent_staging
from .manifest_artifacts import require_safe_token
from .p9_review_draft_store import require_real_state_root
from .safe_input_files import read_real_file
from .spine42_bundle_files import (
    existing_exact_child,
    is_alias,
    remove_staging,
    require_real_directory,
    sync_directory,
    write_file,
)


class P9PolicyPromotionStoreError(RuntimeError):
    """Raised when a promoted review package cannot be sealed exactly."""


def publish_promoted_review_package(
    state_root: Path,
    motion_id: str,
    project_id: str,
    documents: Mapping[str, bytes],
) -> bool:
    """Publish a fixed three-document package; return whether it was reused."""

    parent: Path | None = None
    staging: Path | None = None
    try:
        motion = require_safe_token(motion_id, "Promoted motion id")
        project = require_safe_token(project_id, "Promoted project id")
        expected = _inventory(documents)
        state = require_real_state_root(Path(state_root))
        parent = _ensure_directory(state, "reviews")
        destination = existing_exact_child(parent, motion)
        if destination is not None:
            _require_exact(destination, project, expected)
            return True
        staging = create_same_parent_staging(parent, prefix=f".{motion[:12]}.")
        require_real_directory(staging, "P9 promotion staging")
        child = staging / project
        child.mkdir()
        require_real_directory(child, "P9 promotion project staging")
        for name, payload in expected.items():
            write_file(child / name, payload)
        sync_directory(child)
        sync_directory(staging)
        _require_exact(staging, project, expected)
        try:
            os.rename(staging, parent / motion)
            destination = parent / motion
            staging = None
            reused = False
            sync_directory(parent)
        except OSError:
            destination = existing_exact_child(parent, motion)
            if destination is None:
                raise
            reused = True
        _require_exact(destination, project, expected)
        return reused
    except P9PolicyPromotionStoreError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise P9PolicyPromotionStoreError(
            "Promoted P9 review package could not be published exactly"
        ) from exc
    finally:
        if staging is not None:
            remove_staging(staging, parent)


def _inventory(documents: Mapping[str, bytes]) -> dict[str, bytes]:
    names = {
        "depth-pair-policy.json", "foot-lock-candidates.json",
        "depth-order-candidates.json",
    }
    if set(documents) != names or any(
        type(payload) is not bytes for payload in documents.values()
    ):
        raise P9PolicyPromotionStoreError(
            "Promoted P9 review package inventory is unsupported"
        )
    return dict(documents)


def _require_exact(
    root: Path, project: str, expected: Mapping[str, bytes],
) -> None:
    directory = require_real_directory(root, "Promoted P9 namespace")
    children = _entries(directory, 1)
    if set(children) != {project}:
        raise P9PolicyPromotionStoreError(
            "Promoted P9 namespace inventory differs"
        )
    child = require_real_directory(
        children[project], "Promoted P9 project directory",
    )
    entries = _entries(child, len(expected))
    if set(entries) != set(expected):
        raise P9PolicyPromotionStoreError(
            "Promoted P9 project inventory differs"
        )
    for name, payload in expected.items():
        path = entries[name]
        if is_alias(path) or not stat.S_ISREG(path.lstat().st_mode) \
                or read_real_file(path, len(payload), name) != payload:
            raise P9PolicyPromotionStoreError(
                "Promoted P9 package bytes differ"
            )


def _entries(directory: Path, maximum: int) -> dict[str, Path]:
    children = []
    for child in directory.iterdir():
        children.append(child)
        if len(children) > maximum:
            raise P9PolicyPromotionStoreError(
                "Promoted P9 inventory contains extra entries"
            )
    if len({child.name.casefold() for child in children}) != len(children) \
            or any(is_alias(child) for child in children):
        raise P9PolicyPromotionStoreError(
            "Promoted P9 inventory contains an alias or case collision"
        )
    return {child.name: child for child in children}


def _ensure_directory(parent: Path, name: str) -> Path:
    found = existing_exact_child(parent, name)
    if found is None:
        try:
            (parent / name).mkdir()
        except FileExistsError:
            pass
        found = existing_exact_child(parent, name)
    if found is None:
        raise P9PolicyPromotionStoreError(
            "Promoted P9 review hierarchy disappeared"
        )
    return require_real_directory(found, "Promoted P9 review hierarchy")


__all__ = [
    "P9PolicyPromotionStoreError", "publish_promoted_review_package",
]
