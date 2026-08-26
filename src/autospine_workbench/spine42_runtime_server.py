"""Loopback-only server for official Spine 4.2 runtime screenshot captures."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlsplit

from .http_security import allowed_origin, host_header_is_local, is_loopback_host
from .safe_input_files import SafeInputFileError, strict_json_object
from .spine42_runtime_contract import canonical_json_bytes
from .spine42_runtime_inputs import (
    Spine42ExportFiles,
    Spine42RuntimePackage,
)
from .spine42_runtime_page import HARNESS_CSS, HARNESS_JS, runtime_case_html
from .spine42_runtime_regression import (
    MAX_CAPTURE_BYTES,
    Spine42CaptureStore,
    Spine42RuntimeRegressionError,
)


MAX_ERROR_BODY = 4096
MAX_REJECT_DRAIN_BYTES = 4 * 1024 * 1024


def create_spine42_runtime_server(
    host: str,
    port: int,
    runtime: Spine42RuntimePackage,
    exports: Spine42ExportFiles,
    session: dict[str, Any],
    capture_store: Spine42CaptureStore,
) -> ThreadingHTTPServer:
    """Create a server that serves only validated in-memory snapshots."""

    if not is_loopback_host(host):
        raise ValueError("Spine runtime harness may only bind to loopback")
    case_id = session["case"]["id"]
    session_bytes = canonical_json_bytes(session)
    static = {
        "/harness.js": (HARNESS_JS, "text/javascript; charset=utf-8"),
        "/harness.css": (HARNESS_CSS, "text/css; charset=utf-8"),
        "/runtime/spine-player.min.js": (
            runtime.javascript_bytes, "text/javascript; charset=utf-8",
        ),
        "/runtime/spine-player.min.css": (
            runtime.stylesheet_bytes, "text/css; charset=utf-8",
        ),
        "/export/skeleton.json": (
            exports.skeleton_bytes, "application/json; charset=utf-8",
        ),
        "/export/skeleton.atlas": (
            exports.atlas_bytes, "text/plain; charset=utf-8",
        ),
        "/export/skeleton.png": (exports.texture_bytes, "image/png"),
        "/api/session": (session_bytes, "application/json; charset=utf-8"),
    }

    class Spine42RuntimeHandler(BaseHTTPRequestHandler):
        server_version = "AutoSpineRuntimeHarness/1"
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
            prefix, capture = "/api/capture/", path.startswith("/api/capture/")
            error = path.startswith("/api/error/")
            if not capture and not error:
                self._drain_rejected_body()
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            supplied = path[len(prefix if capture else "/api/error/"):]
            if supplied != case_id or "/" in supplied:
                self._drain_rejected_body()
                self._json(HTTPStatus.BAD_REQUEST, {"error": "unknown_case"})
                return
            try:
                if capture:
                    if self.headers.get("Content-Type") != "image/png":
                        self._drain_rejected_body()
                        raise Spine42RuntimeRegressionError("capture must be image/png")
                    raw = self._body(MAX_CAPTURE_BYTES)
                    dpr = _positive_int(
                        self.headers.get("X-Autospine-Device-Pixel-Ratio"), "DPR"
                    )
                    report = capture_store.record_capture(
                        supplied, raw, device_pixel_ratio=dpr
                    )
                else:
                    body = strict_json_object(self._body(MAX_ERROR_BODY), "runtime error")
                    report = capture_store.record_error(supplied, body.get("message"))
                self._json(HTTPStatus.OK, {"ok": True, "report": report})
            except (SafeInputFileError, Spine42RuntimeRegressionError, ValueError) as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_capture", "message": str(exc)},
                )

        def _get(self, *, send_body: bool) -> None:
            if not self._request_allowed(require_origin=False):
                return
            path = unquote(urlsplit(self.path).path)
            if path == "/":
                self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
                self._headers(0, "text/plain; charset=utf-8")
                self.send_header("Location", f"/case/{case_id}")
                self.end_headers()
                return
            if path == f"/case/{case_id}":
                body, content_type = runtime_case_html(case_id), "text/html; charset=utf-8"
            elif path == "/api/status":
                self._json(HTTPStatus.OK, capture_store.status(), send_body=send_body)
                return
            elif path in static:
                body, content_type = static[path]
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"}, send_body=send_body)
                return
            self._bytes(HTTPStatus.OK, body, content_type, send_body=send_body)

        def _request_allowed(self, *, require_origin: bool) -> bool:
            if not host_header_is_local(self.headers.get("Host")):
                self._drain_rejected_body()
                self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden_host"})
                return False
            origin = self.headers.get("Origin")
            if require_origin and origin and allowed_origin(origin) is None:
                self._drain_rejected_body()
                self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden_origin"})
                return False
            return True

        def _drain_rejected_body(self) -> None:
            """Avoid a TCP reset while rejecting a bounded in-flight POST body."""

            if self.command != "POST":
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return
            if 0 < length <= MAX_REJECT_DRAIN_BYTES:
                self.rfile.read(length)

        def _body(self, maximum: int) -> bytes:
            raw_length = self.headers.get("Content-Length")
            try:
                length = int(raw_length) if raw_length is not None else -1
            except ValueError as exc:
                raise Spine42RuntimeRegressionError("invalid Content-Length") from exc
            if length < 1 or length > maximum:
                raise Spine42RuntimeRegressionError("request body is outside its byte limit")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise Spine42RuntimeRegressionError("request body length changed")
            return raw

        def _json(
            self, status: int, value: dict[str, Any], *, send_body: bool = True
        ) -> None:
            self._bytes(
                status, canonical_json_bytes(value), "application/json; charset=utf-8",
                send_body=send_body,
            )

        def _bytes(
            self, status: int, body: bytes, content_type: str, *, send_body: bool
        ) -> None:
            self.send_response(status)
            self._headers(len(body), content_type)
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        def _headers(self, length: int, content_type: str) -> None:
            self.send_header("Content-Type", content_type)
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
        return ThreadingHTTPServer((host, port), Spine42RuntimeHandler)
    except OSError as exc:
        raise ValueError(f"cannot bind Spine runtime harness: {exc}") from exc


def _positive_int(value: str | None, label: str) -> int:
    try:
        parsed = int(value) if value is not None else 0
    except ValueError as exc:
        raise Spine42RuntimeRegressionError(f"{label} header is invalid") from exc
    if parsed < 1:
        raise Spine42RuntimeRegressionError(f"{label} header must be positive")
    return parsed
