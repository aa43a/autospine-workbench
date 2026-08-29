"""Atomic immutable store for content-addressed body-sway runtime captures."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat

from .atomic_staging import create_same_parent_staging
from .body_sway_runtime_capture import BodySwayRuntimeCapture
from .body_sway_runtime_capture_bundle import (
    MANIFEST_NAME,
    BodySwayRuntimeCaptureBundle,
    BodySwayRuntimeCaptureBundleError,
    body_sway_runtime_capture_bundle_sha256,
    build_body_sway_runtime_capture_bundle,
)
from .body_sway_runtime_capture_collector import (
    MAX_CAPTURE_BYTES,
    MAX_CAPTURE_TOTAL_BYTES,
)
from .body_sway_runtime_capture_profile import MAX_CAPTURE_DOCUMENT_BYTES
from .body_sway_runtime_capture_validation import (
    BodySwayRuntimeCaptureValidationError,
    require_body_sway_runtime_capture,
)
from .safe_input_files import SafeInputFileError, read_real_file, strict_json_object
from .spine42_bundle_files import (
    Spine42BundleFilesError,
    existing_exact_child,
    is_alias,
    remove_staging,
    require_real_directory,
    sync_directory,
    write_file,
)


NAMESPACE = "body-sway-runtime-captures"


class BodySwayRuntimeCaptureStoreError(RuntimeError):
    """Raised when runtime capture evidence cannot be published safely."""


@dataclass(frozen=True, slots=True)
class PublishedBodySwayRuntimeCapture:
    path: Path
    project_id: str
    temporary_preview_sha256: str
    manifest_sha256: str
    artifact_set_sha256: str
    bundle_sha256: str
    reused: bool


class BodySwayRuntimeCaptureStore:
    """Publish the fixed manifest and PNG inventory under two exact SHAs."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def publish(
        self, capture: BodySwayRuntimeCapture,
    ) -> PublishedBodySwayRuntimeCapture:
        """Validate before creating state and atomically publish exact bytes."""

        try:
            bundle = build_body_sway_runtime_capture_bundle(capture)
        except BodySwayRuntimeCaptureBundleError as exc:
            raise BodySwayRuntimeCaptureStoreError(
                "Runtime capture publication input is invalid"
            ) from exc
        parent: Path | None = None
        staging: Path | None = None
        try:
            parent = _publication_parent(self.state_root, bundle)
            destination = existing_exact_child(parent, bundle.bundle_sha256)
            if destination is not None:
                _verify_directory(destination, bundle)
                return _published(destination, bundle, reused=True)
            staging = create_same_parent_staging(
                parent, prefix=f".{bundle.bundle_sha256[:12]}.",
            )
            require_real_directory(staging, "Runtime capture staging directory")
            captures_dir = staging / "captures"
            captures_dir.mkdir()
            require_real_directory(captures_dir, "Runtime capture PNG directory")
            write_file(staging / MANIFEST_NAME, bundle.manifest_bytes)
            for path, payload in bundle.file_items[1:]:
                write_file(staging / path, payload)
            _verify_directory(staging, bundle, staging=True)
            sync_directory(captures_dir)
            sync_directory(staging)
            try:
                destination = parent / bundle.bundle_sha256
                os.rename(staging, destination)
                staging = None
                sync_directory(parent)
                reused = False
            except OSError:
                destination = existing_exact_child(parent, bundle.bundle_sha256)
                if destination is None:
                    raise
                _verify_directory(destination, bundle)
                reused = True
            _verify_directory(destination, bundle)
            return _published(destination, bundle, reused=reused)
        except BodySwayRuntimeCaptureStoreError:
            raise
        except (
            BodySwayRuntimeCaptureValidationError, OSError,
            SafeInputFileError, Spine42BundleFilesError,
            RuntimeError, TypeError, ValueError,
        ) as exc:
            raise BodySwayRuntimeCaptureStoreError(
                "Could not atomically publish runtime capture bundle"
            ) from exc
        finally:
            if staging is not None:
                remove_staging(staging, parent)


def _verify_directory(
    directory: Path,
    bundle: BodySwayRuntimeCaptureBundle,
    *,
    staging: bool = False,
) -> None:
    """Read all bytes once, validate semantics and require exact equality."""

    root = require_real_directory(directory, "Runtime capture bundle directory")
    if not staging and root.name != bundle.bundle_sha256:
        raise BodySwayRuntimeCaptureStoreError(
            "Runtime capture bundle has the wrong content address"
        )
    root_entries = _inventory(root, {MANIFEST_NAME, "captures"})
    manifest_path = root_entries[MANIFEST_NAME]
    captures_dir = require_real_directory(
        root_entries["captures"], "Runtime capture PNG directory"
    )
    expected = tuple(bundle.file_items[1:])
    names = {path.removeprefix("captures/") for path, _data in expected}
    capture_entries = _inventory(captures_dir, names)
    manifest = read_real_file(
        manifest_path, MAX_CAPTURE_DOCUMENT_BYTES, MANIFEST_NAME
    )
    items: list[tuple[str, bytes]] = []
    total = 0
    for path, _expected_payload in expected:
        name = path.removeprefix("captures/")
        payload = read_real_file(capture_entries[name], MAX_CAPTURE_BYTES, path)
        total += len(payload)
        if total > MAX_CAPTURE_TOTAL_BYTES:
            raise BodySwayRuntimeCaptureStoreError(
                "Runtime capture PNG bytes exceed their total limit"
            )
        items.append((path, payload))
    actual = ((MANIFEST_NAME, manifest),) + tuple(items)
    if actual != bundle.file_items:
        raise BodySwayRuntimeCaptureStoreError(
            "Runtime capture bundle bytes differ from their exact contract"
        )
    document = strict_json_object(manifest, MANIFEST_NAME)
    canonical = json.dumps(
        document, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    if canonical != manifest:
        raise BodySwayRuntimeCaptureStoreError(
            "Runtime capture manifest is not canonical JSON"
        )
    captures = dict(items)
    require_body_sway_runtime_capture(document, captures)
    address = body_sway_runtime_capture_bundle_sha256(manifest, tuple(items))
    if address != bundle.bundle_sha256:
        raise BodySwayRuntimeCaptureStoreError(
            "Runtime capture bundle bytes do not match their address"
        )


def _publication_parent(
    state_root: Path, bundle: BodySwayRuntimeCaptureBundle,
) -> Path:
    root = _safe_state_root(state_root)
    current = root
    for name in (
        "builds", bundle.project_id, NAMESPACE,
        bundle.temporary_preview_sha256,
    ):
        current = _ensure_directory(current, name)
    return current


def _safe_state_root(value: Path) -> Path:
    try:
        absolute = Path(os.path.abspath(os.fspath(Path(value))))
    except (OSError, TypeError, ValueError) as exc:
        raise BodySwayRuntimeCaptureStoreError(
            "Runtime capture state root is invalid"
        ) from exc
    current = Path(absolute.parts[0])
    require_real_directory(current, "Runtime capture state-root ancestor")
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
            child, "Runtime capture state-root ancestor"
        )
    return current


def _ensure_directory(parent: Path, name: str) -> Path:
    found = existing_exact_child(parent, name)
    if found is None:
        try:
            (parent / name).mkdir()
        except FileExistsError:
            pass
        found = existing_exact_child(parent, name)
    if found is None:
        raise BodySwayRuntimeCaptureStoreError(
            "Runtime capture hierarchy disappeared"
        )
    return require_real_directory(found, f"Runtime capture path {name}")


def _inventory(directory: Path, expected: set[str]) -> dict[str, Path]:
    try:
        children = list(directory.iterdir())
    except OSError as exc:
        raise BodySwayRuntimeCaptureStoreError(
            "Runtime capture inventory cannot be read"
        ) from exc
    if len(children) != len(expected) or {item.name for item in children} != expected \
            or len({item.name.casefold() for item in children}) != len(children):
        raise BodySwayRuntimeCaptureStoreError(
            "Runtime capture inventory is incomplete, extra, or wrong-case"
        )
    for item in children:
        if is_alias(item):
            raise BodySwayRuntimeCaptureStoreError(
                "Runtime capture inventory contains an alias"
            )
        try:
            mode = item.lstat().st_mode
        except OSError as exc:
            raise BodySwayRuntimeCaptureStoreError(
                "Runtime capture inventory cannot be inspected"
            ) from exc
        if item.name == "captures":
            valid = stat.S_ISDIR(mode)
        else:
            valid = stat.S_ISREG(mode)
        if not valid:
            raise BodySwayRuntimeCaptureStoreError(
                "Runtime capture inventory entry has the wrong type"
            )
    return {item.name: item for item in children}


def _published(path, bundle, *, reused) -> PublishedBodySwayRuntimeCapture:
    return PublishedBodySwayRuntimeCapture(
        path, bundle.project_id, bundle.temporary_preview_sha256,
        bundle.manifest_sha256, bundle.artifact_set_sha256,
        bundle.bundle_sha256, reused,
    )
