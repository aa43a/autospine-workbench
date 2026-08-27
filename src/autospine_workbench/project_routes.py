"""Read-only service, project, and project-asset HTTP route dispatch."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .contracts import PROJECT_LIST_SCHEMA_VERSION, contract_descriptor
from .project_store import ProjectStore


SendJson = Callable[[int, Any], None]
SendFile = Callable[[Path], None]


def dispatch_project_get(
    parts: list[str],
    store: ProjectStore,
    send_json: SendJson,
    send_file: SendFile,
) -> bool:
    """Dispatch established health, project, validation, and asset GET routes."""
    if parts == ["api", "health"]:
        send_json(
            HTTPStatus.OK,
            {
                "status": "ok",
                "service": "autospine-workbench",
                "version": __version__,
                "project_count": store.discovered_project_count(),
            },
        )
        return True
    if parts == ["api", "projects"]:
        projects = store.list_projects()
        send_json(
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
        send_json(
            HTTPStatus.OK,
            {
                "schema_version": "autospine-workbench.validation-list/v1",
                "valid": all(report["valid"] for report in reports),
                "reports": reports,
            },
        )
        return True
    if len(parts) < 3 or parts[:2] != ["api", "projects"]:
        return False
    project_id = parts[2]
    if len(parts) == 3:
        send_json(HTTPStatus.OK, store.get_project(project_id))
        return True
    if len(parts) == 4 and parts[3] == "validate":
        send_json(HTTPStatus.OK, store.validate_project(project_id))
        return True
    if len(parts) == 4 and parts[3] == "overrides":
        send_json(HTTPStatus.OK, store.get_project(project_id)["overrides"])
        return True
    if len(parts) == 4 and parts[3] in {
        "composite",
        "composite.png",
        "embedded-composite",
        "contact-sheet",
    }:
        asset = "composite" if parts[3] == "composite.png" else parts[3]
        send_file(store.resolve_asset(project_id, asset))
        return True
    if (
        len(parts) == 6
        and parts[3] == "layers"
        and parts[5] in {"image", "image.png"}
    ):
        send_file(store.resolve_asset(project_id, "layer", parts[4]))
        return True
    return False
