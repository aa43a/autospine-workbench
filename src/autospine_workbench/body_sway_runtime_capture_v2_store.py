"""Atomic immutable store for content-addressed RuntimeCapture v2 bundles."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat

from .atomic_staging import create_same_parent_staging
from .body_sway_runtime_capture_collector import (
    MAX_CAPTURE_BYTES,
    MAX_CAPTURE_TOTAL_BYTES,
)
from .body_sway_runtime_capture_v2 import BodySwayRuntimeCaptureV2
from .body_sway_runtime_capture_v2_bundle import (
    BodySwayRuntimeCaptureV2Bundle,
    BodySwayRuntimeCaptureV2BundleError,
    body_sway_runtime_capture_v2_bundle_sha256,
    build_body_sway_runtime_capture_v2_bundle,
)
from .body_sway_runtime_capture_v2_profile import (
    MANIFEST_NAME,
    MAX_CAPTURE_DOCUMENT_BYTES,
    NAMESPACE,
)
from .body_sway_runtime_capture_v2_validation import (
    require_body_sway_runtime_capture_v2,
)
from .safe_input_files import read_real_file, strict_json_object
from .spine42_bundle_files import (
    existing_exact_child,
    is_alias,
    remove_staging,
    require_real_directory,
    sync_directory,
    write_file,
)


class BodySwayRuntimeCaptureV2StoreError(RuntimeError):
    """Raised when v2 evidence cannot be published without mutation."""


@dataclass(frozen=True, slots=True)
class PublishedBodySwayRuntimeCaptureV2:
    path: Path
    project_id: str
    temporary_preview_v2_sha256: str
    manifest_sha256: str
    artifact_set_sha256: str
    bundle_sha256: str
    reused: bool


class BodySwayRuntimeCaptureV2Store:
    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(
        self, capture: BodySwayRuntimeCaptureV2,
    ) -> PublishedBodySwayRuntimeCaptureV2:
        """Validate first, then atomically publish or exact-reuse bytes."""

        try:
            bundle = build_body_sway_runtime_capture_v2_bundle(capture)
        except BodySwayRuntimeCaptureV2BundleError as exc:
            raise BodySwayRuntimeCaptureV2StoreError(
                "Runtime capture v2 publication input is invalid"
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
            require_real_directory(staging, "Runtime capture v2 staging")
            captures = staging / "captures"
            captures.mkdir()
            require_real_directory(captures, "Runtime capture v2 PNG directory")
            write_file(staging / MANIFEST_NAME, bundle.manifest_bytes)
            for path, payload in bundle.file_items[1:]:
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
                destination = existing_exact_child(parent, bundle.bundle_sha256)
                if destination is None:
                    raise
                _verify_directory(destination, bundle)
                reused = True
            _verify_directory(destination, bundle)
            return _published(destination, bundle, reused)
        except BodySwayRuntimeCaptureV2StoreError:
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise BodySwayRuntimeCaptureV2StoreError(
                "Could not atomically publish RuntimeCapture v2"
            ) from exc
        finally:
            if staging is not None:
                remove_staging(staging, parent)


def verify_body_sway_runtime_capture_v2_directory(
    directory: Path, bundle: BodySwayRuntimeCaptureV2Bundle,
    *, staging: bool = False,
) -> None:
    """Read all bytes once and require semantic and address equality."""

    _verify_directory(directory, bundle, staging=staging)


def _verify_directory(directory, bundle, *, staging=False) -> None:
    root = require_real_directory(directory, "Runtime capture v2 bundle")
    if not staging and root.name != bundle.bundle_sha256:
        raise BodySwayRuntimeCaptureV2StoreError(
            "Runtime capture v2 bundle has the wrong address"
        )
    entries = _inventory(root, {MANIFEST_NAME, "captures"})
    captures = require_real_directory(
        entries["captures"], "Runtime capture v2 PNG directory"
    )
    expected = tuple(bundle.file_items[1:])
    names = {path.removeprefix("captures/") for path, _data in expected}
    image_entries = _inventory(captures, names)
    manifest = read_real_file(
        entries[MANIFEST_NAME], MAX_CAPTURE_DOCUMENT_BYTES, MANIFEST_NAME
    )
    items, total = [], 0
    for path, _payload in expected:
        payload = read_real_file(
            image_entries[path.removeprefix("captures/")],
            MAX_CAPTURE_BYTES, path,
        )
        total += len(payload)
        if total > MAX_CAPTURE_TOTAL_BYTES:
            raise BodySwayRuntimeCaptureV2StoreError(
                "Runtime capture v2 PNG total exceeds its limit"
            )
        items.append((path, payload))
    actual = ((MANIFEST_NAME, manifest),) + tuple(items)
    if actual != bundle.file_items:
        raise BodySwayRuntimeCaptureV2StoreError(
            "Runtime capture v2 bytes differ from their contract"
        )
    document = strict_json_object(manifest, MANIFEST_NAME)
    canonical = json.dumps(
        document, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    if canonical != manifest:
        raise BodySwayRuntimeCaptureV2StoreError(
            "Runtime capture v2 manifest is not canonical"
        )
    require_body_sway_runtime_capture_v2(document, dict(items))
    if body_sway_runtime_capture_v2_bundle_sha256(
        manifest, tuple(items)
    ) != bundle.bundle_sha256:
        raise BodySwayRuntimeCaptureV2StoreError(
            "Runtime capture v2 bundle address is inconsistent"
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
        raise BodySwayRuntimeCaptureV2StoreError(
            "Runtime capture v2 state root is invalid"
        ) from exc
    current = Path(absolute.parts[0])
    require_real_directory(current, "Runtime capture v2 root ancestor")
    for name in absolute.parts[1:]:
        child = current / name
        try:
            child.lstat()
        except FileNotFoundError:
            try:
                child.mkdir()
            except FileExistsError:
                pass
        current = require_real_directory(child, "Runtime capture v2 ancestor")
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
        raise BodySwayRuntimeCaptureV2StoreError(
            "Runtime capture v2 hierarchy disappeared"
        )
    return require_real_directory(found, f"Runtime capture v2 path {name}")


def _inventory(directory, expected):
    try:
        children = list(directory.iterdir())
        if len(children) != len(expected) \
                or {item.name for item in children} != expected \
                or len({item.name.casefold() for item in children}) \
                != len(children):
            raise BodySwayRuntimeCaptureV2StoreError(
                "Runtime capture v2 inventory differs"
            )
        for item in children:
            mode = item.lstat().st_mode
            valid = stat.S_ISDIR(mode) if item.name == "captures" \
                else stat.S_ISREG(mode)
            if is_alias(item) or not valid:
                raise BodySwayRuntimeCaptureV2StoreError(
                    "Runtime capture v2 inventory is unsafe"
                )
        return {item.name: item for item in children}
    except BodySwayRuntimeCaptureV2StoreError:
        raise
    except OSError as exc:
        raise BodySwayRuntimeCaptureV2StoreError(
            "Runtime capture v2 inventory is unreadable"
        ) from exc


def _published(path, bundle, reused):
    return PublishedBodySwayRuntimeCaptureV2(
        path, bundle.project_id, bundle.temporary_preview_v2_sha256,
        bundle.manifest_sha256, bundle.artifact_set_sha256,
        bundle.bundle_sha256, reused,
    )
