"""Preview v2 wrapper around the shared loopback runtime server core."""

from __future__ import annotations

from http.server import ThreadingHTTPServer

from .body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureCollector,
)
from .body_sway_runtime_capture_server_core import (
    create_runtime_capture_server,
)
from .body_sway_runtime_capture_session_v2 import (
    BodySwayRuntimeCaptureSessionV2Error,
    BodySwayRuntimeCaptureSessionsV2,
    require_exact_body_sway_runtime_capture_sessions_v2,
)
from .http_security import is_loopback_host
from .spine42_runtime_inputs import Spine42RuntimePackage
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2


def create_body_sway_runtime_capture_server_v2(
    host: str,
    port: int,
    runtime: Spine42RuntimePackage,
    preview: TemporaryBodySwayPreviewV2,
    sessions: BodySwayRuntimeCaptureSessionsV2,
    collector: BodySwayRuntimeCaptureCollector,
) -> ThreadingHTTPServer:
    """Validate all v2 types before entering the shared transport core."""

    if not is_loopback_host(host):
        raise ValueError("Runtime capture v2 server requires loopback")
    if type(runtime) is not Spine42RuntimePackage \
            or type(preview) is not TemporaryBodySwayPreviewV2 \
            or type(sessions) is not BodySwayRuntimeCaptureSessionsV2 \
            or type(collector) is not BodySwayRuntimeCaptureCollector:
        raise ValueError("Runtime capture v2 server inputs are inconsistent")
    try:
        sessions = require_exact_body_sway_runtime_capture_sessions_v2(
            preview, runtime, sessions,
        )
    except BodySwayRuntimeCaptureSessionV2Error as exc:
        raise ValueError(str(exc)) from exc
    return create_runtime_capture_server(
        host, port, runtime, preview.artifact_bytes, sessions, collector,
        server_header="AutoSpineBodySwayHarness/2",
    )


__all__ = ["create_body_sway_runtime_capture_server_v2"]
