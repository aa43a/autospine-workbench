"""Shared loopback transport for already verified Spine runtime sessions."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from .http_security import allowed_origin, host_header_is_local, is_loopback_host
from .bounded_threading_http_server import _BoundedThreadingHTTPServer
from .safe_input_files import SafeInputFileError, strict_json_object
from .spine42_runtime_contract import canonical_json_bytes
from .spine42_v3_runtime_capture_core import MAX_CAPTURE_BYTES
from .spine42_v3_runtime_capture_page import (
    Spine42V3RuntimeCapturePageError,
    decode_spine42_v3_observables,
)


MAX_ERROR_BODY = 4096
MAX_REJECT_DRAIN_BYTES = 4 * 1024 * 1024


def create_spine_runtime_capture_server_core(
    host, port, *, artifact_ids, session_bytes, static, collector,
    collector_error_type, page_factory,
    server_header="AutoSpineV3RuntimeHarness/1",
) -> ThreadingHTTPServer:
    """Serve immutable inputs after a version wrapper has verified authority."""

    if not is_loopback_host(host):
        raise ValueError("Spine v3 runtime harness may only bind to loopback")
    if type(artifact_ids) is not tuple or not artifact_ids \
            or set(session_bytes) != set(artifact_ids) \
            or any(type(key) is not str or "/" in key for key in artifact_ids):
        raise ValueError("Spine v3 runtime transport inventory is invalid")

    class SpineRuntimeHandler(BaseHTTPRequestHandler):
        server_version = server_header
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
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            capture = path.startswith("/api/capture/")
            error = path.startswith("/api/error/")
            if parsed.query or (not capture and not error):
                self._drain_rejected_body()
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            prefix = "/api/capture/" if capture else "/api/error/"
            artifact_id = path[len(prefix):]
            if artifact_id not in artifact_ids or "/" in artifact_id:
                self._drain_rejected_body()
                self._json(
                    HTTPStatus.BAD_REQUEST, {"error": "unknown_artifact"}
                )
                return
            try:
                if capture:
                    if self.headers.get("Content-Type") != "image/png":
                        self._drain_rejected_body()
                        raise collector_error_type("capture must be image/png")
                    report = collector.record_capture(
                        artifact_id, self._body(MAX_CAPTURE_BYTES),
                        device_pixel_ratio=_positive_int(
                            self.headers.get(
                                "X-Autospine-Device-Pixel-Ratio"
                            ),
                            "DPR", collector_error_type,
                        ),
                        observed_inventory=decode_spine42_v3_observables(
                            self.headers.get(
                                "X-Autospine-Observed-Inventory"
                            )
                        ),
                    )
                else:
                    body = strict_json_object(
                        self._body(MAX_ERROR_BODY), "runtime error",
                    )
                    report = collector.record_error(
                        artifact_id, body.get("message"),
                    )
                self._json(HTTPStatus.OK, {"ok": True, "report": report})
            except (
                SafeInputFileError, Spine42V3RuntimeCapturePageError,
                collector_error_type, ValueError,
            ) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {
                    "error": "invalid_capture", "message": str(exc),
                })

        def _get(self, *, send_body: bool) -> None:
            if not self._request_allowed(require_origin=False):
                return
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            if parsed.query:
                self._json(
                    HTTPStatus.NOT_FOUND, {"error": "not_found"},
                    send_body=send_body,
                )
                return
            if path == "/":
                first = quote(artifact_ids[0], safe="")
                self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
                self._headers(0, "text/plain; charset=utf-8")
                self.send_header("Location", f"/capture/{first}")
                self.end_headers()
                return
            if path == "/api/status":
                self._json(
                    HTTPStatus.OK, collector.status(), send_body=send_body,
                )
                return
            if path.startswith("/api/session/"):
                artifact_id = path.removeprefix("/api/session/")
                if artifact_id in session_bytes and "/" not in artifact_id:
                    self._bytes(
                        HTTPStatus.OK, session_bytes[artifact_id],
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
                    HTTPStatus.OK, body, media_type, send_body=send_body,
                )
                return
            if path.startswith("/capture/"):
                artifact_id = path.removeprefix("/capture/")
                if artifact_id in session_bytes and "/" not in artifact_id:
                    self._bytes(
                        HTTPStatus.OK, page_factory(artifact_id),
                        "text/html; charset=utf-8", send_body=send_body,
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
                self._json(
                    HTTPStatus.FORBIDDEN, {"error": "forbidden_origin"}
                )
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
                raise collector_error_type("invalid Content-Length") from exc
            if not 0 < length <= maximum:
                raise collector_error_type(
                    "request body is outside its byte limit"
                )
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise collector_error_type("request body length changed")
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
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data: blob:; connect-src 'self'; "
                "base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
                "form-action 'none'; worker-src 'none'",
            )
            self.close_connection = True

        def log_message(self, format_string: str, *args: Any) -> None:
            return

    try:
        return _BoundedThreadingHTTPServer((host, port), SpineRuntimeHandler)
    except OSError as exc:
        raise ValueError(
            f"cannot bind Spine v3 runtime harness: {exc}"
        ) from exc


def _positive_int(value, label, error_type):
    try:
        result = int(value) if value is not None else 0
    except ValueError as exc:
        raise error_type(f"{label} header is invalid") from exc
    if result < 1:
        raise error_type(f"{label} header must be positive")
    return result


__all__ = [
    "MAX_ERROR_BODY", "MAX_REJECT_DRAIN_BYTES",
    "create_spine_runtime_capture_server_core",
]
