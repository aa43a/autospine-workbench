"""Frozen v1 wrapper around the shared loopback runtime server core."""

from __future__ import annotations

from http.server import ThreadingHTTPServer

from .body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureCollector,
)
from .body_sway_runtime_capture_server_core import (
    MAX_ERROR_BODY,
    MAX_REJECT_DRAIN_BYTES,
    create_runtime_capture_server,
)
from .body_sway_runtime_capture_session import (
    BodySwayRuntimeCaptureSessionError,
    BodySwayRuntimeCaptureSessions,
    require_exact_body_sway_runtime_capture_sessions,
)
from .http_security import is_loopback_host
from .spine42_runtime_inputs import Spine42RuntimePackage
from .temporary_body_sway_preview import TemporaryBodySwayPreview


def create_body_sway_runtime_capture_server(
    host: str,
    port: int,
    runtime: Spine42RuntimePackage,
    preview: TemporaryBodySwayPreview,
    sessions: BodySwayRuntimeCaptureSessions,
    collector: BodySwayRuntimeCaptureCollector,
) -> ThreadingHTTPServer:
    """Validate frozen v1 types before entering the shared transport core."""

    if not is_loopback_host(host):
        raise ValueError("Body-sway runtime harness may only bind to loopback")
    if type(runtime) is not Spine42RuntimePackage \
            or type(preview) is not TemporaryBodySwayPreview \
            or type(collector) is not BodySwayRuntimeCaptureCollector \
            or type(sessions) is not BodySwayRuntimeCaptureSessions:
        raise ValueError("Body-sway runtime harness inputs are inconsistent")
    try:
        sessions = require_exact_body_sway_runtime_capture_sessions(
            preview, runtime, sessions,
        )
    except BodySwayRuntimeCaptureSessionError as exc:
        raise ValueError(str(exc)) from exc
    return create_runtime_capture_server(
        host, port, runtime, preview.artifact_bytes, sessions, collector,
    )


__all__ = [
    "MAX_ERROR_BODY", "MAX_REJECT_DRAIN_BYTES",
    "create_body_sway_runtime_capture_server",
]
