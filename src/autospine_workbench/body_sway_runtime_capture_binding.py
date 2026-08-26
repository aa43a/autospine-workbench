"""Internal and authoritative replay for one detached runtime capture value."""

from __future__ import annotations

import os
from pathlib import Path

from .body_sway_runtime_capture_bundle import (
    BodySwayRuntimeCaptureBundle,
    BodySwayRuntimeCaptureBundleError,
    build_body_sway_runtime_capture_bundle,
)
from .body_sway_runtime_capture_reader import (
    VerifiedBodySwayRuntimeCapture,
    VerifiedBodySwayRuntimeCaptureReader,
    VerifiedBodySwayRuntimeCaptureReaderError,
)
from .body_sway_runtime_capture_store import NAMESPACE
from .body_sway_runtime_capture_validation import (
    BodySwayRuntimeCaptureValidationError,
    require_body_sway_runtime_capture,
)


class BodySwayRuntimeCaptureBindingError(RuntimeError):
    """Raised when detached capture values fail internal or stored replay."""


def require_internally_valid_runtime_capture(
    value: VerifiedBodySwayRuntimeCapture,
) -> BodySwayRuntimeCaptureBundle:
    """Revalidate semantics and rebuild bundle identity without filesystem trust."""

    try:
        if type(value) is not VerifiedBodySwayRuntimeCapture:
            raise BodySwayRuntimeCaptureBindingError(
                "Runtime capture value has the wrong representation"
            )
        capture = value.capture
        document, captures = capture.document, capture.capture_bytes
        require_body_sway_runtime_capture(document, captures)
        bundle = build_body_sway_runtime_capture_bundle(capture)
        if bundle.manifest_bytes != capture.canonical_bytes \
                or bundle.capture_bytes != captures \
                or value.bundle_sha256 != bundle.bundle_sha256 \
                or value.project_id != bundle.project_id \
                or value.temporary_preview_sha256 \
                    != bundle.temporary_preview_sha256 \
                or value.artifact_set_sha256 != bundle.artifact_set_sha256:
            raise BodySwayRuntimeCaptureBindingError(
                "Runtime capture value is internally inconsistent"
            )
        _require_address_suffix(value.path, bundle)
        return bundle
    except BodySwayRuntimeCaptureBindingError:
        raise
    except (
        BodySwayRuntimeCaptureBundleError,
        BodySwayRuntimeCaptureValidationError,
        AttributeError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureBindingError(
            f"Runtime capture internal replay failed: {exc}"
        ) from exc


def reload_authoritative_runtime_capture(
    state_root: Path,
    supplied: VerifiedBodySwayRuntimeCapture,
) -> VerifiedBodySwayRuntimeCapture:
    """Reload the four-part address and compare every supplied byte and field."""

    try:
        bundle = require_internally_valid_runtime_capture(supplied)
        loaded = VerifiedBodySwayRuntimeCaptureReader(state_root).load(
            bundle.project_id,
            bundle.temporary_preview_sha256,
            bundle.bundle_sha256,
            bundle.artifact_set_sha256,
        )
        if _absolute(loaded.path) != _absolute(supplied.path) \
                or loaded.bundle_sha256 != supplied.bundle_sha256 \
                or loaded.capture.canonical_bytes \
                    != supplied.capture.canonical_bytes \
                or loaded.capture.capture_bytes != supplied.capture.capture_bytes:
            raise BodySwayRuntimeCaptureBindingError(
                "Supplied capture differs from authoritative store replay"
            )
        return loaded
    except BodySwayRuntimeCaptureBindingError:
        raise
    except (
        VerifiedBodySwayRuntimeCaptureReaderError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureBindingError(
            f"Authoritative runtime capture replay failed: {exc}"
        ) from exc


def _require_address_suffix(
    path: Path, bundle: BodySwayRuntimeCaptureBundle,
) -> None:
    absolute = _absolute(path)
    expected = (
        "builds", bundle.project_id, NAMESPACE,
        bundle.temporary_preview_sha256, bundle.bundle_sha256,
    )
    if len(absolute.parts) < len(expected) \
            or tuple(absolute.parts[-len(expected):]) != expected:
        raise BodySwayRuntimeCaptureBindingError(
            "Runtime capture path differs from its bundle identity"
        )


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(Path(path))))
