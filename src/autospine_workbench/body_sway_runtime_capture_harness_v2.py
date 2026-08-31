"""Single-construction boundary for the Preview v2 capture harness."""

from __future__ import annotations

from dataclasses import dataclass
from http.server import ThreadingHTTPServer

from .body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureCollector,
)
from .body_sway_runtime_capture_server_v2 import (
    create_body_sway_runtime_capture_server_v2,
)
from .body_sway_runtime_capture_session_v2 import (
    BodySwayRuntimeCaptureSessionsV2,
    build_body_sway_runtime_capture_sessions_v2,
)
from .spine42_runtime_inputs import Spine42RuntimePackage
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2


@dataclass(frozen=True, slots=True)
class BodySwayRuntimeCaptureHarnessV2:
    server: ThreadingHTTPServer
    collector: BodySwayRuntimeCaptureCollector
    sessions: BodySwayRuntimeCaptureSessionsV2


def build_body_sway_runtime_capture_harness_v2(
    preview: TemporaryBodySwayPreviewV2,
    runtime: Spine42RuntimePackage,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> BodySwayRuntimeCaptureHarnessV2:
    sessions = build_body_sway_runtime_capture_sessions_v2(preview, runtime)
    collector = BodySwayRuntimeCaptureCollector(sessions)
    server = create_body_sway_runtime_capture_server_v2(
        host, port, runtime, preview, sessions, collector,
    )
    return BodySwayRuntimeCaptureHarnessV2(server, collector, sessions)


__all__ = [
    "BodySwayRuntimeCaptureHarnessV2",
    "build_body_sway_runtime_capture_harness_v2",
]
