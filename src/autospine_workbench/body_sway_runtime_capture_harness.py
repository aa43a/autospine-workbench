"""Single-construction boundary for an exact P10 loopback capture harness."""

from __future__ import annotations

from dataclasses import dataclass
from http.server import ThreadingHTTPServer

from .body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureCollector,
)
from .body_sway_runtime_capture_server import (
    create_body_sway_runtime_capture_server,
)
from .body_sway_runtime_capture_session import (
    BodySwayRuntimeCaptureSessions,
    build_body_sway_runtime_capture_sessions,
)
from .spine42_runtime_inputs import Spine42RuntimePackage
from .temporary_body_sway_preview import TemporaryBodySwayPreview


@dataclass(frozen=True, slots=True)
class BodySwayRuntimeCaptureHarness:
    """One server, collector and frozen session set from the same inputs."""

    server: ThreadingHTTPServer
    collector: BodySwayRuntimeCaptureCollector
    sessions: BodySwayRuntimeCaptureSessions


def build_body_sway_runtime_capture_harness(
    preview: TemporaryBodySwayPreview,
    runtime: Spine42RuntimePackage,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> BodySwayRuntimeCaptureHarness:
    """Build all cross-wired-sensitive harness objects in one operation."""

    sessions = build_body_sway_runtime_capture_sessions(preview, runtime)
    collector = BodySwayRuntimeCaptureCollector(sessions)
    server = create_body_sway_runtime_capture_server(
        host, port, runtime, preview, sessions, collector
    )
    return BodySwayRuntimeCaptureHarness(server, collector, sessions)
