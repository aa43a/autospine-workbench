"""Atomic immutable store for official body-sway runtime executions."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat

from .atomic_staging import create_same_parent_staging
from .body_sway_runtime_capture_collector import (
    MAX_CAPTURE_BYTES,
    MAX_CAPTURE_TOTAL_BYTES,
)
from .body_sway_runtime_capture_v2_profile import MAX_CAPTURE_DOCUMENT_BYTES
from .body_sway_runtime_execution import BodySwayRuntimeExecution
from .body_sway_runtime_execution_bundle import (
    BodySwayRuntimeExecutionBundle,
    BodySwayRuntimeExecutionBundleError,
    body_sway_runtime_execution_bundle_sha256,
    build_body_sway_runtime_execution_bundle,
    replay_body_sway_runtime_execution,
)
from .body_sway_runtime_execution_profile import (
    MANIFEST_NAME,
    MAX_MANIFEST_BYTES,
    NAMESPACE,
    PAYLOAD_NAME,
)
from .safe_input_files import read_real_file
from .spine42_bundle_files import (
    existing_exact_child,
    is_alias,
    remove_staging,
    require_real_directory,
    sync_directory,
    write_file,
)


class BodySwayRuntimeExecutionStoreError(RuntimeError):
    """Raised when official execution bytes cannot publish immutably."""


@dataclass(frozen=True, slots=True)
class PublishedBodySwayRuntimeExecution:
    path: Path
    project_id: str
    temporary_preview_v2_sha256: str
    execution_sha256: str
    runtime_capture_v2_sha256: str
    artifact_set_sha256: str
    bundle_sha256: str
    reused: bool


class BodySwayRuntimeExecutionStore:
    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(
        self, execution: BodySwayRuntimeExecution,
    ) -> PublishedBodySwayRuntimeExecution:
        """Validate, stage, and rename one exact content-addressed bundle."""

        try:
            bundle = build_body_sway_runtime_execution_bundle(execution)
        except BodySwayRuntimeExecutionBundleError as exc:
            raise BodySwayRuntimeExecutionStoreError(
                "Runtime execution publication input is invalid"
            ) from exc
        parent = staging = None
        try:
            parent = _publication_parent(self.state_root, bundle)
            destination = existing_exact_child(parent, bundle.bundle_sha256)
            if destination is not None:
                _verify_directory(destination, bundle)
                return _published(destination, bundle, True)
            staging = create_same_parent_staging(
                parent, prefix=f".{bundle.bundle_sha256[:12]}.",
            )
            require_real_directory(staging, "Runtime execution staging")
            captures = staging / "captures"
            captures.mkdir()
            require_real_directory(captures, "Runtime execution captures")
            for path, payload in bundle.file_items:
                write_file(staging / path, payload)
            _verify_directory(staging, bundle, staging=True)
            sync_directory(captures)
            sync_directory(staging)
            try:
                destination = parent / bundle.bundle_sha256
                os.rename(staging, destination)
                staging, reused = None, False
                sync_directory(parent)
            except OSError:
                destination = existing_exact_child(
                    parent, bundle.bundle_sha256,
                )
                if destination is None:
                    raise
                _verify_directory(destination, bundle)
                reused = True
            _verify_directory(destination, bundle)
            return _published(destination, bundle, reused)
        except BodySwayRuntimeExecutionStoreError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise BodySwayRuntimeExecutionStoreError(
                "Could not atomically publish runtime execution"
            ) from exc
        finally:
            if staging is not None:
                remove_staging(staging, parent)


def verify_body_sway_runtime_execution_directory(
    directory: Path, bundle: BodySwayRuntimeExecutionBundle,
    *, staging: bool = False,
) -> None:
    """Read and replay every stored byte against the expected bundle."""

    _verify_directory(directory, bundle, staging=staging)


def _verify_directory(directory, bundle, *, staging=False) -> None:
    root = require_real_directory(directory, "Runtime execution bundle")
    if not staging and root.name != bundle.bundle_sha256:
        raise BodySwayRuntimeExecutionStoreError(
            "Runtime execution bundle has the wrong address"
        )
    entries = _inventory(
        root, {MANIFEST_NAME, PAYLOAD_NAME, "captures"},
    )
    captures = require_real_directory(
        entries["captures"], "Runtime execution captures",
    )
    expected_captures = tuple(bundle.file_items[2:])
    names = {Path(path).name for path, _payload in expected_captures}
    image_entries = _inventory(captures, names)
    execution_bytes = read_real_file(
        entries[MANIFEST_NAME], MAX_MANIFEST_BYTES, MANIFEST_NAME,
    )
    payload_bytes = read_real_file(
        entries[PAYLOAD_NAME], MAX_CAPTURE_DOCUMENT_BYTES, PAYLOAD_NAME,
    )
    items, total = [], 0
    for path, _payload in expected_captures:
        payload = read_real_file(
            image_entries[Path(path).name], MAX_CAPTURE_BYTES, path,
        )
        total += len(payload)
        if total > MAX_CAPTURE_TOTAL_BYTES:
            raise BodySwayRuntimeExecutionStoreError(
                "Runtime execution PNG total exceeds its limit"
            )
        items.append((path, payload))
    actual = (
        (MANIFEST_NAME, execution_bytes),
        (PAYLOAD_NAME, payload_bytes),
    ) + tuple(items)
    if actual != bundle.file_items:
        raise BodySwayRuntimeExecutionStoreError(
            "Runtime execution bytes differ from their contract"
        )
    replayed = replay_body_sway_runtime_execution(
        execution_bytes, payload_bytes, tuple(items),
    )
    built = build_body_sway_runtime_execution_bundle(replayed)
    if built.file_items != actual \
            or built.bundle_sha256 != bundle.bundle_sha256 \
            or body_sway_runtime_execution_bundle_sha256(actual) \
            != bundle.bundle_sha256:
        raise BodySwayRuntimeExecutionStoreError(
            "Runtime execution bundle address is inconsistent"
        )


def _publication_parent(state_root, bundle):
    current = _safe_state_root(state_root)
    for name in (
        "builds", bundle.project_id, NAMESPACE,
        bundle.temporary_preview_v2_sha256,
    ):
        current = _ensure_directory(current, name)
    return current


def _safe_state_root(value):
    try:
        absolute = Path(os.path.abspath(os.fspath(Path(value))))
    except (OSError, TypeError, ValueError) as exc:
        raise BodySwayRuntimeExecutionStoreError(
            "Runtime execution state root is invalid"
        ) from exc
    current = Path(absolute.parts[0])
    require_real_directory(current, "Runtime execution root ancestor")
    for name in absolute.parts[1:]:
        child = current / name
        try:
            child.lstat()
        except FileNotFoundError:
            try:
                child.mkdir()
            except FileExistsError:
                pass
        current = require_real_directory(
            child, "Runtime execution state-root ancestor",
        )
    return current


def _ensure_directory(parent, name):
    found = existing_exact_child(parent, name)
    if found is None:
        try:
            (parent / name).mkdir()
        except FileExistsError:
            pass
        found = existing_exact_child(parent, name)
    if found is None:
        raise BodySwayRuntimeExecutionStoreError(
            "Runtime execution hierarchy disappeared"
        )
    return require_real_directory(found, f"Runtime execution path {name}")


def _inventory(directory, expected):
    try:
        children = list(directory.iterdir())
        if len(children) != len(expected) \
                or {item.name for item in children} != expected \
                or len({item.name.casefold() for item in children}) \
                != len(children):
            raise BodySwayRuntimeExecutionStoreError(
                "Runtime execution inventory differs"
            )
        for item in children:
            mode = item.lstat().st_mode
            valid = stat.S_ISDIR(mode) if item.name == "captures" \
                else stat.S_ISREG(mode)
            if is_alias(item) or not valid:
                raise BodySwayRuntimeExecutionStoreError(
                    "Runtime execution inventory is unsafe"
                )
        return {item.name: item for item in children}
    except BodySwayRuntimeExecutionStoreError:
        raise
    except OSError as exc:
        raise BodySwayRuntimeExecutionStoreError(
            "Runtime execution inventory is unreadable"
        ) from exc


def _published(path, bundle, reused):
    return PublishedBodySwayRuntimeExecution(
        path, bundle.project_id, bundle.temporary_preview_v2_sha256,
        bundle.execution_sha256, bundle.runtime_capture_v2_sha256,
        bundle.artifact_set_sha256, bundle.bundle_sha256, reused,
    )
