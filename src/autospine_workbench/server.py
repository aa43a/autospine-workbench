"""Safe loopback-only HTTP API for the AutoSpine workbench."""

from __future__ import annotations

import json
import mimetypes
import socket
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from . import __version__
from .analysis_routes import dispatch_candidate_artifact_get
from .contracts import (
    ContractValidationError,
    PROJECT_LIST_SCHEMA_VERSION,
    contract_descriptor,
)
from .http_security import (
    allowed_origin as _allowed_origin,
    host_header_is_local as _host_header_is_local,
    is_loopback_host as _is_loopback_host,
)
from .project_store import (
    AssetNotFoundError,
    ProjectNotFoundError,
    ProjectStore,
    ProjectStoreError,
    RevisionConflictError,
)


MAX_REQUEST_BODY = 1024 * 1024


def _decode_json_object(raw: bytes) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(value, dict):
        raise ValueError("request body must be a JSON object")
    return value


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

        def _send_error_json(self, status: int, code: str, message: str) -> None:
            self._send_json(status, {"error": code, "message": message})

        def _send_file(self, path: Path) -> None:
            try:
                stat = path.stat()
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self.send_response(HTTPStatus.OK)
                self._common_headers()
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(stat.st_size))
                self.send_header(
                    "ETag", f'W/"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
                )
                self.end_headers()
                if self.command == "HEAD":
                    return
                with path.open("rb") as handle:
                    while True:
                        chunk = handle.read(64 * 1024)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except (OSError, BrokenPipeError, ConnectionError):
                if not self.wfile.closed:
                    self.close_connection = True

        def _path_parts(self) -> list[str]:
            path = urlsplit(self.path).path
            try:
                parts = [unquote(part) for part in path.split("/") if part]
            except UnicodeError as exc:
                raise ValueError("invalid URL encoding") from exc
            if any(part in {".", ".."} or "\x00" in part or "/" in part or "\\" in part for part in parts):
                raise ValueError("unsafe URL path")
            return parts

        def _dispatch_api_get(self, parts: list[str]) -> bool:
            if parts == ["api", "health"]:
                projects = store.list_projects()
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "service": "autospine-workbench",
                        "version": __version__,
                        "project_count": len(projects),
                    },
                )
                return True
            if parts == ["api", "projects"]:
                projects = store.list_projects()
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "schema_version": PROJECT_LIST_SCHEMA_VERSION,
                        "contract": contract_descriptor("project-list"),
                        "count": len(projects),
                        "projects": projects,
                    },
                )
                return True
            if parts == ["api", "validate"]:
                projects = store.list_projects()
                reports = [store.validate_project(item["id"]) for item in projects]
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "schema_version": "autospine-workbench.validation-list/v1",
                        "valid": all(report["valid"] for report in reports),
                        "reports": reports,
                    },
                )
                return True
            if dispatch_candidate_artifact_get(parts, store, self._send_json, self._send_error_json):
                return True
            if len(parts) >= 3 and parts[:2] == ["api", "projects"]:
                project_id = parts[2]
                if len(parts) == 3:
                    self._send_json(HTTPStatus.OK, store.get_project(project_id))
                    return True
                if len(parts) == 4 and parts[3] == "validate":
                    self._send_json(HTTPStatus.OK, store.validate_project(project_id))
                    return True
                if len(parts) == 4 and parts[3] == "overrides":
                    self._send_json(
                        HTTPStatus.OK, store.get_project(project_id)["overrides"]
                    )
                    return True
                if len(parts) == 4 and parts[3] in {
                    "composite",
                    "composite.png",
                    "embedded-composite",
                    "contact-sheet",
                }:
                    asset = "composite" if parts[3] == "composite.png" else parts[3]
                    self._send_file(store.resolve_asset(project_id, asset))
                    return True
                if (
                    len(parts) == 6
                    and parts[3] == "layers"
                    and parts[5] in {"image", "image.png"}
                ):
                    self._send_file(store.resolve_asset(project_id, "layer", parts[4]))
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
            self.send_response(HTTPStatus.NO_CONTENT)
            self._common_headers()
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, PUT, OPTIONS")
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
                if not (
                    len(parts) == 4
                    and parts[:2] == ["api", "projects"]
                    and parts[3] == "overrides"
                ):
                    self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", "API route not found.")
                    return
                content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type != "application/json":
                    self._send_error_json(
                        HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                        "unsupported_media_type",
                        "Content-Type must be application/json.",
                    )
                    return
                raw_length = self.headers.get("Content-Length")
                try:
                    content_length = int(raw_length or "")
                except ValueError:
                    content_length = -1
                if content_length < 0:
                    self._send_error_json(
                        HTTPStatus.LENGTH_REQUIRED,
                        "length_required",
                        "A valid Content-Length header is required.",
                    )
                    return
                if content_length > MAX_REQUEST_BODY:
                    self._send_error_json(
                        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                        "request_too_large",
                        f"Request bodies are limited to {MAX_REQUEST_BODY} bytes.",
                    )
                    return
                raw_body = self.rfile.read(content_length)
                if len(raw_body) != content_length:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "short_body", "Request body was incomplete.")
                    return
                try:
                    payload = _decode_json_object(raw_body)
                except ValueError as exc:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid_json", str(exc))
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
            self._send_bytes(
                HTTPStatus.METHOD_NOT_ALLOWED,
                b'{"error":"method_not_allowed","message":"Method not allowed."}',
                "application/json; charset=utf-8",
                extra_headers={"Allow": "GET, HEAD, PUT, OPTIONS"},
            )

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
