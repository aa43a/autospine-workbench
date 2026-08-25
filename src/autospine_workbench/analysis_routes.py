"""Read-only HTTP routing for content-addressed analysis artifacts."""

from __future__ import annotations

from collections.abc import Callable
from http import HTTPStatus
from typing import Any

from .analysis_repository import (
    AnalysisArtifactNotFound,
    AnalysisArtifactRepository,
    AnalysisRepositoryError,
)
from .project_store import ProjectStore


JsonSender = Callable[[int, Any], None]
ErrorSender = Callable[[int, str, str], None]


def dispatch_analysis_artifact_get(
    parts: list[str],
    store: ProjectStore,
    send_json: JsonSender,
    send_error: ErrorSender,
) -> bool:
    """Serve validated analysis indexes/artifacts and report whether the route matched."""

    supported = {"candidate-artifacts", "geometry-evidence"}
    if (
        len(parts) not in {4, 5}
        or parts[:2] != ["api", "projects"]
        or parts[3] not in supported
    ):
        return False

    project_id = parts[2]
    project = store.get_project(project_id)
    context = {
        "joint_ids": {item["id"] for item in project["skeleton"]["joints"]},
        "layer_ids": {item["id"] for item in project["layers"]},
        "canvas_width": project["canvas"]["width"],
        "canvas_height": project["canvas"]["height"],
    }
    repository = AnalysisArtifactRepository(store.state_root)
    route = parts[3]
    try:
        if route == "candidate-artifacts" and len(parts) == 4:
            result = repository.list_joint_candidates(project_id, **context)
        elif route == "candidate-artifacts":
            result = repository.read_joint_candidates(project_id, parts[4], **context)
        elif len(parts) == 4:
            result = repository.list_alpha_geometry_evidence(project_id, **context)
        else:
            result = repository.read_alpha_geometry_evidence(project_id, parts[4], **context)
    except AnalysisArtifactNotFound:
        if route == "candidate-artifacts":
            code, message = (
                "candidate_artifact_not_found",
                "Candidate artifact was not found.",
            )
        else:
            code, message = (
                "geometry_evidence_not_found",
                "Geometry evidence was not found.",
            )
        send_error(
            HTTPStatus.NOT_FOUND,
            code,
            message,
        )
    except AnalysisRepositoryError:
        send_error(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "analysis_repository_error",
            "The local analysis repository could not complete the request.",
        )
    else:
        send_json(HTTPStatus.OK, result)
    return True
