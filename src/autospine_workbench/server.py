"""Safe loopback-only HTTP API for the AutoSpine workbench."""

from __future__ import annotations

import logging
import socket
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .body_sway_visual_review_routes import (
    dispatch_body_sway_visual_review_put,
)
from .contracts import ContractValidationError
from .http_security import host_header_is_local as _host_header_is_local
from .http_json_request import HttpJsonRequestError, read_json_object_request
from .http_static_response import serve_static_response
from .http_workbench_response import WorkbenchResponseMixin
from . import motion_policy_mutation_routes as policy_mutation
from .motion_policy_preflight_routes import (
    dispatch_motion_policy_preflight_post, is_motion_policy_preflight_path,
    send_motion_policy_preflight_method_not_allowed,
)
from . import state_root_preflight
from .motion_policy_review_package_routes import (
    is_motion_policy_review_package_path,
    send_motion_policy_review_package_method_not_allowed,
)
from .motion_policy_review_draft_routes import (
    is_motion_policy_review_draft_get_path,
    send_motion_policy_review_draft_method_not_allowed,
)
from .project_store import (
    AssetNotFoundError,
    ProjectNotFoundError,
    ProjectStore,
    ProjectStoreError,
    RevisionConflictError,
)
from .p10_capture_job_manager import (
    P10CaptureJobManager,
    P10CaptureJobManagerError,
)
from .p10_runtime_capture_routes import (
    dispatch_p10_runtime_capture_post,
    is_p10_runtime_capture_path,
    send_p10_runtime_capture_method_not_allowed,
)
from .p10_visual_review_v2_routes import (
    dispatch_p10_visual_review_v2_put,
)
from .seam_anchor_review_routes import (
    dispatch_seam_anchor_review_post,
    is_seam_anchor_review_path,
)
from .seam_anchor_review_replay_cache import SeamAnchorReviewReplayCache
from .server_binding import WorkbenchThreadingHTTPServer, validate_server_configuration
from .server_get_routes import dispatch_workbench_api_get
from .server_method_routes import send_workbench_route_method_not_allowed
from .workbench_options import send_workbench_options


_LOG = logging.getLogger(__name__)
def _handler_factory(
    store: ProjectStore, web_root: Path | None,
    replay_cache: SeamAnchorReviewReplayCache,
    capture_manager: P10CaptureJobManager,
) -> type[BaseHTTPRequestHandler]:
    class WorkbenchHandler(WorkbenchResponseMixin, BaseHTTPRequestHandler):
        server_version = "AutoSpineWorkbench/0.1"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, format_string: str, *args: Any) -> None:
            # Keep the standard useful request log, but never include request bodies.
            super().log_message(format_string, *args)

        def _dispatch_api_get(self, parts: list[str]) -> bool:
            return dispatch_workbench_api_get(
                parts, store, replay_cache, capture_manager, self,
            )

        def _serve_static(self, parts: list[str]) -> bool:
            if web_root is not None and parts[:1] == ["docs"]:
                if len(parts) < 2 or Path(parts[-1]).suffix.lower() != ".md":
                    return False
                return serve_static_response(
                    parts[1:], web_root.parent / "docs",
                    self._send_static_file,
                )
            return serve_static_response(
                parts, web_root, self._send_static_file
            )

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
            except ProjectStoreError as exc:
                _LOG.exception("Project store GET failed: %s", type(exc).__name__)
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
            send_workbench_options(parts, self)

        def do_PUT(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if not _host_header_is_local(self.headers.get("Host")):
                self._send_error_json(HTTPStatus.FORBIDDEN, "forbidden_host", "Host must be loopback-local.")
                return
            try:
                parts = self._path_parts()
                if policy_mutation.is_motion_policy_mutation_path(parts):
                    policy_mutation.send_motion_policy_mutation_method_not_allowed(parts, self)
                    return
                if is_motion_policy_preflight_path(parts):
                    send_motion_policy_preflight_method_not_allowed(self)
                    return
                if is_motion_policy_review_package_path(parts):
                    send_motion_policy_review_package_method_not_allowed(self)
                    return
                if is_motion_policy_review_draft_get_path(parts):
                    send_motion_policy_review_draft_method_not_allowed(self)
                    return
                if dispatch_p10_visual_review_v2_put(
                    parts, capture_manager, store, self,
                    self._send_visual_json,
                ):
                    return
                if is_p10_runtime_capture_path(parts):
                    send_p10_runtime_capture_method_not_allowed(parts, self)
                    return
                if dispatch_body_sway_visual_review_put(
                    parts, store, self, self._send_visual_json,
                ):
                    return
                if is_seam_anchor_review_path(parts):
                    self._send_seam_anchor_review_method_not_allowed(parts)
                    return
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
            except ProjectStoreError as exc:
                _LOG.exception("Project store PUT failed: %s", type(exc).__name__)
                self._send_error_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "project_store_error",
                    "The local project store could not complete the request.",
                )

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if not _host_header_is_local(self.headers.get("Host")):
                self._send_error_json(
                    HTTPStatus.FORBIDDEN, "forbidden_host",
                    "Host must be loopback-local.",
                )
                return
            try:
                parts = self._path_parts()
            except ValueError as exc:
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST, "invalid_path", str(exc)
                )
                return
            if policy_mutation.dispatch_motion_policy_mutation_post(
                parts, self, store, self._send_visual_json,
            ):
                return
            if dispatch_p10_runtime_capture_post(
                parts, self, capture_manager, self._send_visual_json,
            ):
                return
            if dispatch_motion_policy_preflight_post(
                parts, self, self._send_visual_json,
            ):
                return
            if dispatch_seam_anchor_review_post(
                parts, store, self, self._send_visual_json, replay_cache,
            ):
                return
            self._send_route_method_not_allowed(parts)

        def _method_not_allowed(self) -> None:
            if not _host_header_is_local(self.headers.get("Host")):
                self._send_error_json(HTTPStatus.FORBIDDEN, "forbidden_host", "Host must be loopback-local.")
                return
            try:
                parts = self._path_parts()
            except ValueError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "invalid_path", str(exc))
                return
            self._send_route_method_not_allowed(parts)

        def _send_route_method_not_allowed(self, parts: list[str]) -> None:
            send_workbench_route_method_not_allowed(parts, self)

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

    resolved_web_root = validate_server_configuration(host, port, web_root)
    store = ProjectStore(Path(workspace_root), state_root=state_root)
    try:
        projects = store.list_projects()
        state_root_preflight.preflight_state_root_mutations(
            store.state_root, tuple(project["id"] for project in projects)
        )
    except (
        ProjectStoreError, state_root_preflight.StateRootMutationUnavailable,
    ) as exc:
        raise OSError(
            "Project state preflight failed; verify workspace mutation permissions "
            "and stored decision inputs."
        ) from exc
    replay_cache = SeamAnchorReviewReplayCache(store.state_root)
    try:
        capture_manager = P10CaptureJobManager(store)
    except P10CaptureJobManagerError as exc:
        raise OSError("P10 Runtime capture manager could not start.") from exc
    handler = _handler_factory(
        store, resolved_web_root, replay_cache, capture_manager,
    )
    try:
        server = WorkbenchThreadingHTTPServer((host, port), handler)
    except (OSError, socket.error) as exc:
        capture_manager.close()
        raise OSError(f"Could not bind AutoSpine workbench to {host}:{port}") from exc
    server.project_store = store  # type: ignore[attr-defined]
    server.web_root = resolved_web_root  # type: ignore[attr-defined]
    server.seam_anchor_review_replay_cache = replay_cache  # type: ignore[attr-defined]
    server.p10_capture_job_manager = capture_manager  # type: ignore[attr-defined]
    return server
