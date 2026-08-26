"""Safe loopback-only HTTP API for the AutoSpine workbench."""

from __future__ import annotations

import json
import socket
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .analysis_routes import dispatch_analysis_artifact_get
from .contracts import ContractValidationError
from .http_security import (
    allowed_origin as _allowed_origin,
    host_header_is_local as _host_header_is_local,
    is_loopback_host as _is_loopback_host,
)
from .http_file_response import send_file_response
from .http_json_request import HttpJsonRequestError, read_json_object_request
from .http_request_path import safe_url_path_parts
from .mesh_bundle_routes import dispatch_mesh_bundle_get
from .project_store import (
    AssetNotFoundError,
    ProjectNotFoundError,
    ProjectStore,
    ProjectStoreError,
    RevisionConflictError,
)
from .project_routes import dispatch_project_get
from .split_preview_routes import dispatch_split_preview_get


def _handler_factory(store: ProjectStore, web_root: Path | None) -> type[BaseHTTPRequestHandler]:
    class WorkbenchHandler(BaseHTTPRequestHandler):
        server_version = "AutoSpineWorkbench/0.1"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, format_string: str, *args: Any) -> None:
            # Keep the standard useful request log, but never include request bodies.
            super().log_message(format_string, *args)

        def _common_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Vary", "Origin")
            # The workbench serves many layer images at once. Closing each
            # response avoids idle HTTP/1.1 handler threads later printing
            # socket timeout noise in the local authoring terminal.
            self.send_header("Connection", "close")
            self.close_connection = True
            origin = _allowed_origin(self.headers.get("Origin"))
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)

        def _send_bytes(
            self,
            status: int,
            body: bytes,
            content_type: str,
            *,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self._common_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if extra_headers:
                for key, value in extra_headers.items():
                    self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD" and body:
                self.wfile.write(body)

        def _send_json(self, status: int, value: Any) -> None:
            body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._send_bytes(status, body, "application/json; charset=utf-8")

        def _send_png(self, body: bytes) -> None:
            self._send_bytes(HTTPStatus.OK, body, "image/png")

        def _send_error_json(self, status: int, code: str, message: str) -> None:
            self._send_json(status, {"error": code, "message": message})

        def _mesh_bundle_path(self, parts: list[str]) -> bool:
            return len(parts) >= 4 and parts[:2] == ["api", "projects"] \
                and parts[3] == "mesh-bundles"

        def _send_method_not_allowed(self, *, read_only: bool = False) -> None:
            allow = "GET, HEAD, OPTIONS" if read_only else "GET, HEAD, PUT, OPTIONS"
            message = "Mesh bundle evidence is read-only." if read_only else "Method not allowed."
            body = json.dumps({"error": "method_not_allowed", "message": message},
                              separators=(",", ":")).encode("utf-8")
            self._send_bytes(
                HTTPStatus.METHOD_NOT_ALLOWED, body,
                "application/json; charset=utf-8", extra_headers={"Allow": allow},
            )

        def _send_file(self, path: Path) -> None:
            send_file_response(self, path, self._common_headers)

        def _path_parts(self) -> list[str]:
            return safe_url_path_parts(self.path)

        def _dispatch_api_get(self, parts: list[str]) -> bool:
            if dispatch_project_get(parts, store, self._send_json, self._send_file):
                return True
            if dispatch_mesh_bundle_get(
                parts, store, self._send_json, self._send_error_json, self._send_png
            ):
                return True
            if dispatch_analysis_artifact_get(
                parts, store, self._send_json, self._send_error_json
            ):
                return True
            if dispatch_split_preview_get(
                parts,
                store,
                self._send_json,
                self._send_error_json,
                self._send_file,
            ):
                return True
            return False

        def _serve_static(self, parts: list[str]) -> bool:
            if web_root is None:
                return False
            relative = Path(*parts) if parts else Path("index.html")
            candidate = web_root / relative
            try:
                root = web_root.resolve(strict=True)
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(root)
            except (OSError, ValueError):
                # Frontend history routes may fall back to index.html, but
                # asset-like missing paths should remain a 404.
                if parts and "." not in parts[-1]:
                    candidate = web_root / "index.html"
                    try:
                        resolved = candidate.resolve(strict=True)
                        resolved.relative_to(web_root.resolve(strict=True))
                    except (OSError, ValueError):
                        return False
                else:
                    return False
            if not resolved.is_file():
                return False
            self._send_file(resolved)
            return True

        def _handle_get_or_head(self) -> None:
            if not _host_header_is_local(self.headers.get("Host")):
                self._send_error_json(HTTPStatus.FORBIDDEN, "forbidden_host", "Host must be loopback-local.")
                return
            try:
                parts = self._path_parts()
                if parts and parts[0] == "api":
                    if not self._dispatch_api_get(parts):
                        self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", "API route not found.")
                    return
                if self._serve_static(parts):
                    return
                self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", "Resource not found.")
            except ProjectNotFoundError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, "project_not_found", str(exc))
            except AssetNotFoundError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, "asset_not_found", str(exc))
            except ValueError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid_path", str(exc))
            except ProjectStoreError:
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "project_store_error",
                    "The local project store could not complete the request.",
                )

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._handle_get_or_head()

        def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._handle_get_or_head()

        def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if not _host_header_is_local(self.headers.get("Host")):
                self._send_error_json(HTTPStatus.FORBIDDEN, "forbidden_host", "Host must be loopback-local.")
                return
            try:
                parts = self._path_parts()
            except ValueError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid_path", str(exc))
                return
            self.send_response(HTTPStatus.NO_CONTENT)
            self._common_headers()
            methods = "GET, HEAD, OPTIONS" if self._mesh_bundle_path(parts) \
                else "GET, HEAD, PUT, OPTIONS"
            self.send_header("Allow", methods)
            self.send_header("Access-Control-Allow-Methods", methods)
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_PUT(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if not _host_header_is_local(self.headers.get("Host")):
                self._send_error_json(HTTPStatus.FORBIDDEN, "forbidden_host", "Host must be loopback-local.")
                return
            try:
                parts = self._path_parts()
                if self._mesh_bundle_path(parts):
                    self._send_method_not_allowed(read_only=True)
                    return
                if not (
                    len(parts) == 4
                    and parts[:2] == ["api", "projects"]
                    and parts[3] == "overrides"
                ):
                    self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", "API route not found.")
                    return
                try:
                    payload = read_json_object_request(self)
                except HttpJsonRequestError as exc:
                    self._send_error_json(
                        exc.status, exc.code, exc.public_message,
                    )
                    return
                saved = store.save_overrides(parts[2], payload)
                self._send_json(HTTPStatus.OK, saved)
            except ContractValidationError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, exc.as_dict())
            except RevisionConflictError as exc:
                self._send_json(HTTPStatus.CONFLICT, exc.as_dict())
            except ProjectNotFoundError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, "project_not_found", str(exc))
            except ProjectStoreError:
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "project_store_error",
                    "The local project store could not complete the request.",
                )

        def _method_not_allowed(self) -> None:
            if not _host_header_is_local(self.headers.get("Host")):
                self._send_error_json(HTTPStatus.FORBIDDEN, "forbidden_host", "Host must be loopback-local.")
                return
            try:
                parts = self._path_parts()
            except ValueError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid_path", str(exc))
                return
            self._send_method_not_allowed(read_only=self._mesh_bundle_path(parts))

        do_POST = _method_not_allowed
        do_PATCH = _method_not_allowed
        do_DELETE = _method_not_allowed

    return WorkbenchHandler


def create_server(
    host: str,
    port: int,
    workspace_root: Path,
    web_root: Path | None = None,
    state_root: Path | None = None,
) -> ThreadingHTTPServer:
    """Create, but do not start, a loopback-only workbench server."""

    if not _is_loopback_host(host):
        raise ValueError("AutoSpine workbench may only bind to localhost or a loopback IP.")
    if not isinstance(port, int) or isinstance(port, bool) or not (0 <= port <= 65535):
        raise ValueError("port must be an integer between 0 and 65535")
    resolved_web_root: Path | None = None
    if web_root is not None:
        resolved_web_root = Path(web_root).expanduser().resolve()
        if not resolved_web_root.is_dir():
            raise ValueError("web_root must be an existing directory")
    store = ProjectStore(Path(workspace_root), state_root=state_root)
    handler = _handler_factory(store, resolved_web_root)
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except (OSError, socket.error) as exc:
        raise OSError(f"Could not bind AutoSpine workbench to {host}:{port}") from exc
    server.project_store = store  # type: ignore[attr-defined]
    server.web_root = resolved_web_root  # type: ignore[attr-defined]
    return server
