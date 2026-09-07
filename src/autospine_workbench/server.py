"""Safe loopback-only HTTP API for the AutoSpine workbench."""

from __future__ import annotations

import logging
import socket
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .contracts import ContractValidationError
from .http_security import host_header_is_local as _host_header_is_local
from .http_json_request import HttpJsonRequestError, read_json_object_request
from .http_log_redaction import redact_http_log_arguments
from .http_static_response import serve_static_response
from .http_workbench_response import WorkbenchResponseMixin
from . import state_root_preflight
from .project_store import (
    AssetNotFoundError,
    ProjectNotFoundError,
    ProjectStore,
    ProjectStoreError,
    RevisionConflictError,
)
from .p10_capture_job_manager import P10CaptureJobManager
from .p10_safety_analysis_manager_v2 import P10SafetyAnalysisManagerV2
from .p10_dynamic_seam_manager_v2 import P10DynamicSeamManagerV2
from .p10_motion_instance_v3_manager_v2 import (
    P10MotionInstanceV3ManagerV2,
)
from .p10_spine42_v3_manager_v2 import P10Spine42V3ManagerV2
from .p10_spine42_v3_runtime_execution_v2 import execute_p10_spine42_v3_runtime_job_v2
from .p10_spine42_v3_runtime_manager_v2 import P10Spine42V3RuntimeManagerV2
from .p10_visual_review_v2_image_cache import (
    P10VisualReviewV2ImageReplayCache,
)
from .p10_visual_review_v2_image_session import (
    P10VisualReviewV2ImageSessionStore,
)
from .seam_anchor_review_replay_cache import SeamAnchorReviewReplayCache
from .server_binding import WorkbenchThreadingHTTPServer, validate_server_configuration
from .server_get_routes import dispatch_workbench_api_get
from .server_manager_lifecycle import start_workbench_managers
from .server_method_routes import send_workbench_route_method_not_allowed
from .server_write_routes import (
    dispatch_workbench_api_post, dispatch_workbench_api_put,
)
from .workbench_options import send_workbench_options


_LOG = logging.getLogger(__name__)
def _handler_factory(
    store: ProjectStore, web_root: Path | None,
    replay_cache: SeamAnchorReviewReplayCache,
    capture_manager: P10CaptureJobManager,
    safety_analysis_v2_manager: P10SafetyAnalysisManagerV2,
    dynamic_seam_v2_manager: P10DynamicSeamManagerV2,
    motion_instance_v3_v2_manager: P10MotionInstanceV3ManagerV2,
    spine42_v3_v2_manager: P10Spine42V3ManagerV2,
    spine42_v3_runtime_v2_manager: P10Spine42V3RuntimeManagerV2,
    visual_review_v2_image_sessions: P10VisualReviewV2ImageSessionStore,
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
            super().log_message(
                format_string, *redact_http_log_arguments(args),
            )

        def _dispatch_api_get(self, parts: list[str]) -> bool:
            return dispatch_workbench_api_get(
                parts, store, replay_cache, capture_manager,
                safety_analysis_v2_manager,
                dynamic_seam_v2_manager,
                motion_instance_v3_v2_manager,
                spine42_v3_v2_manager,
                spine42_v3_runtime_v2_manager,
                visual_review_v2_image_sessions, self,
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
                if dispatch_workbench_api_put(
                    parts, store, capture_manager, self,
                ):
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
            if dispatch_workbench_api_post(
                parts, store, replay_cache, capture_manager,
                safety_analysis_v2_manager, dynamic_seam_v2_manager,
                motion_instance_v3_v2_manager, spine42_v3_v2_manager,
                spine42_v3_runtime_v2_manager, self,
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
    managers = start_workbench_managers(
        store, P10CaptureJobManager, P10SafetyAnalysisManagerV2,
        P10DynamicSeamManagerV2, P10MotionInstanceV3ManagerV2,
        P10Spine42V3ManagerV2,
        lambda current: P10Spine42V3RuntimeManagerV2(
            current, execution=execute_p10_spine42_v3_runtime_job_v2,
        ),
    )
    capture_manager = managers.capture
    safety_analysis_v2_manager = managers.safety_analysis_v2
    dynamic_seam_v2_manager = managers.dynamic_seam_v2
    motion_instance_v3_v2_manager = managers.motion_instance_v3_v2
    spine42_v3_v2_manager = managers.spine42_v3_v2
    spine42_v3_runtime_v2_manager = managers.spine42_v3_runtime_v2
    visual_review_v2_image_cache = P10VisualReviewV2ImageReplayCache(
        store.state_root,
    )
    visual_review_v2_image_sessions = P10VisualReviewV2ImageSessionStore(
        store.state_root, image_cache=visual_review_v2_image_cache,
    )
    handler = _handler_factory(
        store, resolved_web_root, replay_cache, capture_manager,
        safety_analysis_v2_manager,
        dynamic_seam_v2_manager,
        motion_instance_v3_v2_manager,
        spine42_v3_v2_manager,
        spine42_v3_runtime_v2_manager,
        visual_review_v2_image_sessions,
    )
    try:
        server = WorkbenchThreadingHTTPServer((host, port), handler)
    except (OSError, socket.error) as exc:
        managers.close_after_bind_failure()
        raise OSError(f"Could not bind AutoSpine workbench to {host}:{port}") from exc
    bindings = {
        "project_store": store, "web_root": resolved_web_root,
        "seam_anchor_review_replay_cache": replay_cache,
        "p10_capture_job_manager": capture_manager,
        "p10_safety_analysis_v2_manager": safety_analysis_v2_manager,
        "p10_dynamic_seam_v2_manager": dynamic_seam_v2_manager,
        "p10_motion_instance_v3_v2_manager": motion_instance_v3_v2_manager,
        "p10_spine42_v3_v2_manager": spine42_v3_v2_manager,
        "p10_spine42_v3_runtime_v2_manager": spine42_v3_runtime_v2_manager,
        "p10_visual_review_v2_image_cache": visual_review_v2_image_cache,
        "p10_visual_review_v2_image_sessions": visual_review_v2_image_sessions,
    }
    for name, value in bindings.items():
        setattr(server, name, value)
    return server
