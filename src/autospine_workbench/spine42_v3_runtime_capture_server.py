"""Frozen v1 wrapper for the shared loopback Spine runtime transport."""

from __future__ import annotations

from http.server import ThreadingHTTPServer

from .http_security import is_loopback_host
from .spine42_runtime_inputs import Spine42RuntimePackage
from .spine42_v3_bundle_integrity import VerifiedSpine42V3Bundle
from .spine42_v3_runtime_capture_collector import (
    Spine42V3RuntimeCaptureCollector,
    Spine42V3RuntimeCaptureCollectorError,
)
from .spine42_v3_runtime_capture_page import (
    spine42_v3_runtime_capture_html,
    spine42_v3_runtime_static_snapshots,
)
from .spine42_v3_runtime_capture_server_core import (
    MAX_ERROR_BODY, MAX_REJECT_DRAIN_BYTES,
    create_spine_runtime_capture_server_core,
)
from .spine42_v3_runtime_session import (
    Spine42V3RuntimeSessionError,
    Spine42V3RuntimeSessions,
    require_exact_spine42_v3_runtime_sessions,
)


def create_spine42_v3_runtime_capture_server(
    host: str,
    port: int,
    runtime: Spine42RuntimePackage,
    bundle: VerifiedSpine42V3Bundle,
    sessions: Spine42V3RuntimeSessions,
    collector: Spine42V3RuntimeCaptureCollector,
) -> ThreadingHTTPServer:
    """Validate frozen v1 types before entering the shared transport core."""

    if not is_loopback_host(host):
        raise ValueError("Spine v3 runtime harness may only bind to loopback")
    if type(collector) is not Spine42V3RuntimeCaptureCollector:
        raise ValueError("Spine v3 runtime collector type is invalid")
    try:
        sessions = require_exact_spine42_v3_runtime_sessions(
            bundle, runtime, sessions,
        )
    except Spine42V3RuntimeSessionError as exc:
        raise ValueError(str(exc)) from exc
    if collector.artifact_ids != sessions.artifact_ids \
            or collector.session_set_sha256 != sessions.sha256:
        raise ValueError("Spine v3 runtime harness inputs are cross-wired")
    session_bytes = sessions.session_bytes
    return create_spine_runtime_capture_server_core(
        host, port, artifact_ids=sessions.artifact_ids,
        session_bytes=session_bytes,
        static=spine42_v3_runtime_static_snapshots(runtime, bundle),
        collector=collector,
        collector_error_type=Spine42V3RuntimeCaptureCollectorError,
        page_factory=spine42_v3_runtime_capture_html,
    )


__all__ = [
    "MAX_ERROR_BODY", "MAX_REJECT_DRAIN_BYTES",
    "create_spine42_v3_runtime_capture_server",
]
