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


def dispatch_candidate_artifact_get(
    parts: list[str],
    store: ProjectStore,
    send_json: JsonSender,
    send_error: ErrorSender,
) -> bool:
    """Serve candidate indexes and artifacts, returning whether the route matched."""

    if (
        len(parts) not in {4, 5}
        or parts[:2] != ["api", "projects"]
        or parts[3] != "candidate-artifacts"
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
    try:
        if len(parts) == 4:
            result = repository.list_joint_candidates(project_id, **context)
        else:
            result = repository.read_joint_candidates(project_id, parts[4], **context)
    except AnalysisArtifactNotFound:
        send_error(
            HTTPStatus.NOT_FOUND,
            "candidate_artifact_not_found",
            "Candidate artifact was not found.",
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
