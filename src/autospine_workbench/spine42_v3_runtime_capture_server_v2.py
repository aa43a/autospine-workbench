"""Loopback-only HTTP wrapper for exact P10.7b v2 runtime sessions."""

from __future__ import annotations

from http.server import ThreadingHTTPServer

from .http_security import is_loopback_host
from .spine42_runtime_inputs import Spine42RuntimePackage
from .spine42_v3_bundle_reader_v2 import VerifiedSpine42V3BundleV2
from .spine42_v3_runtime_capture_collector_v2 import (
    Spine42V3RuntimeCaptureCollectorV2,
    Spine42V3RuntimeCaptureCollectorV2Error,
)
from .spine42_v3_runtime_capture_page import (
    spine42_v3_runtime_capture_html,
    spine42_v3_runtime_static_snapshots,
)
from .spine42_v3_runtime_capture_server_core import (
    MAX_ERROR_BODY, MAX_REJECT_DRAIN_BYTES,
    create_spine_runtime_capture_server_core,
)
from .spine42_v3_runtime_session_v2 import (
    Spine42V3RuntimeSessionV2Error,
    Spine42V3RuntimeSessionsV2,
    require_exact_spine42_v3_runtime_sessions_v2,
)
from .spine42_v3_runtime_source_bridge_v2 import (
    VerifiedSpine42V3RuntimeSourceV2,
)


def create_spine42_v3_runtime_capture_server_v2(
    host: str,
    port: int,
    runtime: Spine42RuntimePackage,
    bundle: VerifiedSpine42V3BundleV2,
    source: VerifiedSpine42V3RuntimeSourceV2,
    sessions: Spine42V3RuntimeSessionsV2,
    collector: Spine42V3RuntimeCaptureCollectorV2,
) -> ThreadingHTTPServer:
    """Validate all v2 inputs before exposing the transport-only core."""

    if not is_loopback_host(host):
        raise ValueError("Spine v3 runtime harness v2 may only bind to loopback")
    if type(runtime) is not Spine42RuntimePackage \
            or type(bundle) is not VerifiedSpine42V3BundleV2 \
            or type(source) is not VerifiedSpine42V3RuntimeSourceV2 \
            or type(sessions) is not Spine42V3RuntimeSessionsV2 \
            or type(collector) is not Spine42V3RuntimeCaptureCollectorV2:
        raise ValueError("Spine v3 runtime harness v2 inputs are inconsistent")
    try:
        sessions = require_exact_spine42_v3_runtime_sessions_v2(
            bundle, runtime, source, sessions,
        )
    except Spine42V3RuntimeSessionV2Error as exc:
        raise ValueError(str(exc)) from exc
    if collector.artifact_ids != sessions.artifact_ids \
            or collector.session_set_sha256 != sessions.sha256:
        raise ValueError("Spine v3 runtime harness v2 inputs are cross-wired")
    session_bytes = sessions.session_bytes
    return create_spine_runtime_capture_server_core(
        host, port, artifact_ids=sessions.artifact_ids,
        session_bytes=session_bytes,
        static=spine42_v3_runtime_static_snapshots(runtime, bundle),
        collector=collector,
        collector_error_type=Spine42V3RuntimeCaptureCollectorV2Error,
        page_factory=spine42_v3_runtime_capture_html,
        server_header="AutoSpineV3RuntimeHarness/2",
    )


__all__ = [
    "MAX_ERROR_BODY", "MAX_REJECT_DRAIN_BYTES",
    "create_spine42_v3_runtime_capture_server_v2",
]
