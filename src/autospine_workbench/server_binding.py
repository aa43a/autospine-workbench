"""Loopback listener validation and Windows-exclusive HTTP binding."""

from __future__ import annotations

import socket
from http.server import ThreadingHTTPServer
from pathlib import Path

from .http_security import is_loopback_host


class WorkbenchThreadingHTTPServer(ThreadingHTTPServer):
    """Use an exclusive bind where Windows otherwise permits port sharing."""

    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1,
            )
        super().server_bind()

    def server_close(self) -> None:
        manager = getattr(self, "p10_capture_job_manager", None)
        try:
            if manager is not None:
                manager.close()
        finally:
            super().server_close()


def validate_server_configuration(
    host: str, port: int, web_root: Path | None,
) -> Path | None:
    """Validate public startup inputs and resolve the optional static root."""

    if not is_loopback_host(host):
        raise ValueError(
            "AutoSpine workbench may only bind to localhost or a loopback IP."
        )
    if not isinstance(port, int) or isinstance(port, bool) or not (0 <= port <= 65535):
        raise ValueError("port must be an integer between 0 and 65535")
    if web_root is None:
        return None
    resolved_web_root = Path(web_root).expanduser().resolve()
    if not resolved_web_root.is_dir():
        raise ValueError("web_root must be an existing directory")
    return resolved_web_root
