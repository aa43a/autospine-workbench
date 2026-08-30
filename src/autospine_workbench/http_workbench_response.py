"""Shared response primitives for the loopback workbench handler."""

from __future__ import annotations

from http import HTTPStatus
import json
from pathlib import Path
from typing import Any

from .body_sway_visual_review_http_security import visual_review_cors_origin
from .body_sway_visual_review_routes import visual_review_allow_methods
from .http_file_response import send_file_response
from .http_request_path import safe_url_path_parts
from .http_security import allowed_origin
from .seam_anchor_review_routes import seam_anchor_review_allow_methods


LOCAL_REVIEW_CSP = "; ".join((
    "default-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "frame-ancestors 'none'",
    "connect-src 'self'",
    "img-src 'self' data:",
    "script-src 'self'",
    "style-src 'self'",
    "form-action 'self'",
))


class WorkbenchResponseMixin:
    """Provide bounded JSON, PNG, file, CORS, and error responses."""

    def _common_headers(self, *, visual_review: bool = False) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Vary", "Origin")
        self.send_header("Connection", "close")
        self.close_connection = True
        origin = visual_review_cors_origin(self.headers) \
            if visual_review else allowed_origin(self.headers.get("Origin"))
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
        if visual_review:
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        extra_headers: dict[str, str] | None = None,
        visual_review: bool = False,
    ) -> None:
        self.send_response(status)
        self._common_headers(visual_review=visual_review)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def _send_json(self, status: int, value: Any) -> None:
        self._send_bytes(status, _json_bytes(value),
                         "application/json; charset=utf-8")

    def _send_png(self, body: bytes) -> None:
        self._send_bytes(HTTPStatus.OK, body, "image/png")

    def _send_error_json(self, status: int, code: str, message: str) -> None:
        self._send_json(status, {"error": code, "message": message})

    def _send_visual_json(self, status: int, value: Any) -> None:
        self._send_bytes(
            status, _json_bytes(value), "application/json; charset=utf-8",
            visual_review=True,
        )

    def _send_visual_bytes(
        self, status: int, body: bytes, content_type: str,
        extra_headers: dict[str, str] | None,
    ) -> None:
        self._send_bytes(
            status, body, content_type, extra_headers=extra_headers,
            visual_review=True,
        )

    def _mesh_bundle_path(self, parts: list[str]) -> bool:
        return len(parts) >= 4 and parts[:2] == ["api", "projects"] \
            and parts[3] == "mesh-bundles"

    def _send_method_not_allowed(self, *, read_only: bool = False) -> None:
        allow = "GET, HEAD, OPTIONS" if read_only \
            else "GET, HEAD, PUT, OPTIONS"
        message = "Mesh bundle evidence is read-only." if read_only \
            else "Method not allowed."
        self._send_bytes(
            HTTPStatus.METHOD_NOT_ALLOWED,
            _json_bytes({"error": "method_not_allowed", "message": message}),
            "application/json; charset=utf-8", extra_headers={"Allow": allow},
        )

    def _send_visual_method_not_allowed(self, parts: list[str]) -> None:
        self._send_bytes(
            HTTPStatus.METHOD_NOT_ALLOWED,
            _json_bytes({
                "error": "method_not_allowed", "message": "Method not allowed.",
            }),
            "application/json; charset=utf-8",
            extra_headers={"Allow": visual_review_allow_methods(parts)},
            visual_review=True,
        )

    def _send_seam_anchor_review_method_not_allowed(
        self, parts: list[str]
    ) -> None:
        self._send_bytes(
            HTTPStatus.METHOD_NOT_ALLOWED,
            _json_bytes({
                "error": "method_not_allowed", "message": "Method not allowed.",
            }),
            "application/json; charset=utf-8",
            extra_headers={"Allow": seam_anchor_review_allow_methods(parts)},
            visual_review=True,
        )

    def _send_file(self, path: Path) -> None:
        send_file_response(self, path, self._common_headers)

    def _send_static_file(self, path: Path) -> None:
        extra_headers = None
        if path.name in {
            "body-sway-probe.html",
            "body-sway-review.html",
            "document-viewer.html",
            "idle-behavior-review.html",
            "motion-policy-review.html",
            "seam-anchor-review.html",
            "workflow-hub.html",
        }:
            extra_headers = {"Content-Security-Policy": LOCAL_REVIEW_CSP}
        send_file_response(
            self, path, self._common_headers, extra_headers=extra_headers
        )

    def _path_parts(self) -> list[str]:
        return safe_url_path_parts(self.path)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
