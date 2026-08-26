"""Loopback-only official runtime server for P10 preview and fixed captures."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlsplit

from .body_sway_runtime_capture_collector import (
    MAX_CAPTURE_BYTES,
    BodySwayRuntimeCaptureCollector,
    BodySwayRuntimeCaptureCollectorError,
)
from .body_sway_runtime_capture_page import (
    CAPTURE_CSS, CAPTURE_JS, body_sway_capture_case_html,
)
from .body_sway_runtime_capture_session import (
    BodySwayRuntimeCaptureSessionError,
    BodySwayRuntimeCaptureSessions,
    require_exact_body_sway_runtime_capture_sessions,
)
from .http_security import allowed_origin, host_header_is_local, is_loopback_host
from .safe_input_files import SafeInputFileError, strict_json_object
from .spine42_runtime_contract import canonical_json_bytes
from .spine42_runtime_inputs import Spine42RuntimePackage
from .temporary_body_sway_preview import TemporaryBodySwayPreview


MAX_ERROR_BODY = 4096
MAX_REJECT_DRAIN_BYTES = 4 * 1024 * 1024


def create_body_sway_runtime_capture_server(
    host: str,
    port: int,
    runtime: Spine42RuntimePackage,
    preview: TemporaryBodySwayPreview,
    sessions: BodySwayRuntimeCaptureSessions,
    collector: BodySwayRuntimeCaptureCollector,
) -> ThreadingHTTPServer:
    """Serve pinned snapshots, manual player, and all exact capture cases."""

    if not is_loopback_host(host):
        raise ValueError("Body-sway runtime harness may only bind to loopback")
    if type(runtime) is not Spine42RuntimePackage \
            or type(preview) is not TemporaryBodySwayPreview \
            or type(collector) is not BodySwayRuntimeCaptureCollector \
            or type(sessions) is not BodySwayRuntimeCaptureSessions:
        raise ValueError("Body-sway runtime harness inputs are inconsistent")
    try:
        sessions = require_exact_body_sway_runtime_capture_sessions(
            preview, runtime, sessions
        )
    except BodySwayRuntimeCaptureSessionError as exc:
        raise ValueError(str(exc)) from exc
    if collector.case_ids != sessions.case_ids \
            or collector.session_set_sha256 != sessions.sha256:
        raise ValueError("Body-sway runtime harness inputs are cross-wired")
    session_bytes = {
        case_id: canonical_json_bytes(sessions.session(case_id))
        for case_id in sessions.case_ids
    }
    static = _static(runtime, preview)

    class BodySwayRuntimeHandler(BaseHTTPRequestHandler):
        server_version = "AutoSpineBodySwayHarness/1"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(10)

        def do_HEAD(self) -> None:  # noqa: N802
            self._get(send_body=False)

        def do_GET(self) -> None:  # noqa: N802
            self._get(send_body=True)

        def do_POST(self) -> None:  # noqa: N802
            if not self._request_allowed(require_origin=True):
                return
            path = unquote(urlsplit(self.path).path)
            capture = path.startswith("/api/capture/")
            error = path.startswith("/api/error/")
            if not capture and not error:
                self._drain_rejected_body()
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            prefix = "/api/capture/" if capture else "/api/error/"
            case_id = path[len(prefix):]
            if case_id not in collector.case_ids or "/" in case_id:
                self._drain_rejected_body()
                self._json(HTTPStatus.BAD_REQUEST, {"error": "unknown_case"})
                return
            try:
                if capture:
                    if self.headers.get("Content-Type") != "image/png":
                        self._drain_rejected_body()
                        raise BodySwayRuntimeCaptureCollectorError(
                            "capture must be image/png"
                        )
                    report = collector.record_capture(
                        case_id,
                        self._body(MAX_CAPTURE_BYTES),
                        device_pixel_ratio=_positive_int(
                            self.headers.get(
                                "X-Autospine-Device-Pixel-Ratio"
                            ),
                            "DPR",
                        ),
                    )
                else:
                    body = strict_json_object(
                        self._body(MAX_ERROR_BODY), "runtime error"
                    )
                    report = collector.record_error(
                        case_id, body.get("message")
                    )
                self._json(HTTPStatus.OK, {"ok": True, "report": report})
            except (
                BodySwayRuntimeCaptureCollectorError,
                SafeInputFileError,
                ValueError,
            ) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {
                    "error": "invalid_capture", "message": str(exc),
                })

        def _get(self, *, send_body: bool) -> None:
            if not self._request_allowed(require_origin=False):
                return
            path = unquote(urlsplit(self.path).path)
            if path == "/":
                self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
                self._headers(0, "text/plain; charset=utf-8")
                self.send_header("Location", "/runtime/player.html")
                self.end_headers()
                return
            if path == "/api/status":
                self._json(HTTPStatus.OK, collector.status(), send_body=send_body)
                return
            if path.startswith("/api/session/"):
                case_id = path.removeprefix("/api/session/")
                if case_id in session_bytes and "/" not in case_id:
                    self._bytes(
                        HTTPStatus.OK, session_bytes[case_id],
                        "application/json; charset=utf-8", send_body=send_body,
                    )
                else:
                    self._json(
                        HTTPStatus.NOT_FOUND, {"error": "not_found"},
                        send_body=send_body,
                    )
                return
            if path in static:
                body, media_type = static[path]
                self._bytes(
                    HTTPStatus.OK, body, media_type, send_body=send_body
                )
                return
            if path.startswith("/capture/"):
                case_id = path.removeprefix("/capture/")
                if case_id in session_bytes and "/" not in case_id:
                    body = body_sway_capture_case_html(case_id)
                    self._bytes(
                        HTTPStatus.OK, body, "text/html; charset=utf-8",
                        send_body=send_body,
                    )
                else:
                    self._json(
                        HTTPStatus.NOT_FOUND, {"error": "not_found"},
                        send_body=send_body,
                    )
                return
            self._json(
                HTTPStatus.NOT_FOUND, {"error": "not_found"},
                send_body=send_body,
            )

        def _request_allowed(self, *, require_origin: bool) -> bool:
            if not host_header_is_local(self.headers.get("Host")):
                self._drain_rejected_body()
                self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden_host"})
                return False
            origin = self.headers.get("Origin")
            host_header = self.headers.get("Host")
            expected_origin = f"http://{host_header}" if host_header else None
            if require_origin and (
                allowed_origin(origin) is None or origin != expected_origin
            ):
                self._drain_rejected_body()
                self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden_origin"})
                return False
            return True

        def _drain_rejected_body(self) -> None:
            if self.command != "POST":
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return
            if 0 < length <= MAX_REJECT_DRAIN_BYTES:
                self.rfile.read(length)

        def _body(self, maximum: int) -> bytes:
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError as exc:
                raise BodySwayRuntimeCaptureCollectorError(
                    "invalid Content-Length"
                ) from exc
            if not 0 < length <= maximum:
                raise BodySwayRuntimeCaptureCollectorError(
                    "request body is outside its byte limit"
                )
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise BodySwayRuntimeCaptureCollectorError(
                    "request body length changed"
                )
            return raw

        def _json(self, status, value, *, send_body=True) -> None:
            self._bytes(
                status, canonical_json_bytes(value),
                "application/json; charset=utf-8", send_body=send_body,
            )

        def _bytes(self, status, body, media_type, *, send_body) -> None:
            self.send_response(status)
            self._headers(len(body), media_type)
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        def _headers(self, length, media_type) -> None:
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data: blob:; connect-src 'self'",
            )
            self.close_connection = True

        def log_message(self, format_string: str, *args: Any) -> None:
            return

    try:
        return ThreadingHTTPServer((host, port), BodySwayRuntimeHandler)
    except OSError as exc:
        raise ValueError(f"cannot bind body-sway runtime harness: {exc}") from exc


def _static(runtime, preview):
    media = {
        "runtime/player.html": "text/html; charset=utf-8",
        "runtime/session.json": "application/json; charset=utf-8",
        "runtime/skeleton.atlas": "text/plain; charset=utf-8",
        "runtime/skeleton.json": "application/json; charset=utf-8",
        "runtime/skeleton.png": "image/png",
    }
    result = {
        f"/{path}": (raw, media[path])
        for path, raw in preview.artifact_bytes.items()
    }
    result.update({
        "/official/spine-player.min.js": (
            runtime.javascript_bytes, "text/javascript; charset=utf-8",
        ),
        "/official/spine-player.min.css": (
            runtime.stylesheet_bytes, "text/css; charset=utf-8",
        ),
        "/capture/harness.js": (CAPTURE_JS, "text/javascript; charset=utf-8"),
        "/capture/harness.css": (CAPTURE_CSS, "text/css; charset=utf-8"),
    })
    return result


def _positive_int(value: str | None, label: str) -> int:
    try:
        result = int(value) if value is not None else 0
    except ValueError as exc:
        raise BodySwayRuntimeCaptureCollectorError(
            f"{label} header is invalid"
        ) from exc
    if result < 1:
        raise BodySwayRuntimeCaptureCollectorError(
            f"{label} header must be positive"
        )
    return result
