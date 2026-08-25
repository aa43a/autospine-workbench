"""Read-only HTTP routes for exact verified P3 mesh evidence bundles."""

from __future__ import annotations

from collections.abc import Callable
from http import HTTPStatus
from typing import Any

from .mesh_bundle_evidence import (
    MeshBundleEvidenceError,
    MeshBundleEvidenceNotFound,
    MeshBundleEvidenceRepository,
)
from .project_store import ProjectStore


JsonSender = Callable[[int, Any], None]
ErrorSender = Callable[[int, str, str], None]
PngSender = Callable[[bytes], None]


def dispatch_mesh_bundle_get(
    parts: list[str],
    store: ProjectStore,
    send_json: JsonSender,
    send_error: ErrorSender,
    send_png: PngSender,
) -> bool:
    """Serve discovery, exact double-SHA detail, or a verified PNG."""

    if (
        len(parts) not in {4, 6, 8}
        or parts[:2] != ["api", "projects"]
        or parts[3] != "mesh-bundles"
        or (len(parts) == 8 and parts[6] != "images")
    ):
        return False
    project_id = parts[2]
    store.get_project(project_id)
    repository = MeshBundleEvidenceRepository(store.state_root)
    try:
        if len(parts) == 4:
            send_json(HTTPStatus.OK, repository.list(project_id))
        elif len(parts) == 6:
            send_json(HTTPStatus.OK, repository.read(project_id, parts[4], parts[5]))
        else:
            send_png(repository.image(project_id, parts[4], parts[5], parts[7]))
    except MeshBundleEvidenceNotFound:
        send_error(
            HTTPStatus.NOT_FOUND,
            "mesh_bundle_evidence_not_found",
            "The exact mesh bundle evidence was not found.",
        )
    except MeshBundleEvidenceError:
        send_error(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "mesh_bundle_evidence_error",
            "The mesh bundle evidence could not be strictly verified.",
        )
    return True
