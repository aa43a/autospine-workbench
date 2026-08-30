"""Read-only loopback routes for P10.2 body-sway structural probes."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from .body_sway_probe_application import (
    BodySwayProbeApplication,
    BodySwayProbeApplicationError,
    BodySwayProbeApplicationHeadChanged,
    BodySwayProbeApplicationNotFound,
    BodySwayProbeApplicationUnavailable,
)
from .project_store import ProjectStore, ProjectStoreError


SendJson = Callable[[int, Any], None]
_PREFIX = ["api", "idle-behavior", "structural-probes"]


def is_body_sway_probe_path(parts: list[str]) -> bool:
    """Return whether *parts* names a complete list or detail resource."""

    return parts[:3] == _PREFIX and len(parts) in {3, 4}


def dispatch_body_sway_probe_get(
    parts: list[str], store: ProjectStore, send_json: SendJson,
) -> bool:
    """Serve an authority-free list or one current-head structural report."""

    if not is_body_sway_probe_path(parts):
        return False
    try:
        application = BodySwayProbeApplication(store.state_root)
        project_ids = _project_ids(store)
        if len(parts) == 3:
            payload = application.list_packages(project_ids=project_ids)
        else:
            payload = application.prepare(
                parts[3], project_ids=project_ids,
            )
        send_json(HTTPStatus.OK, payload)
    except BodySwayProbeApplicationNotFound:
        send_json(HTTPStatus.NOT_FOUND, {
            "error": "body_sway_probe_not_found",
            "message": "The exact body-sway structural probe is unavailable.",
        })
    except BodySwayProbeApplicationHeadChanged:
        send_json(HTTPStatus.CONFLICT, {
            "error": "body_sway_probe_head_changed",
            "message": "The P10.1 review head changed; reload the probe list.",
        })
    except BodySwayProbeApplicationUnavailable:
        send_json(HTTPStatus.CONFLICT, {
            "error": "body_sway_probe_unavailable",
            "message": "The body-sway structural probe could not be prepared.",
        })
    except (BodySwayProbeApplicationError, ProjectStoreError):
        send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
            "error": "body_sway_probe_error",
            "message": (
                "The body-sway structural probe request could not be "
                "completed safely."
            ),
        })
    return True


def _project_ids(store: ProjectStore) -> tuple[str, ...]:
    return tuple(project["id"] for project in store.list_projects())
