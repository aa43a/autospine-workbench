"""Read-only HTTP routing for immutable bilateral split previews."""

from __future__ import annotations

from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import Any

from .project_store import ProjectStore
from .split_preview_repository import (
    SplitPreviewNotFound,
    SplitPreviewRepository,
    SplitPreviewRepositoryError,
)


JsonSender = Callable[[int, Any], None]
ErrorSender = Callable[[int, str, str], None]
FileSender = Callable[[Path], None]


def dispatch_split_preview_get(
    parts: list[str],
    store: ProjectStore,
    send_json: JsonSender,
    send_error: ErrorSender,
    send_file: FileSender,
) -> bool:
    """Serve preview index, artifact, or a manifest-bound child PNG."""

    if (
        len(parts) not in {4, 5, 8}
        or parts[:2] != ["api", "projects"]
        or parts[3] != "split-previews"
    ):
        return False
    project_id = parts[2]
    store.get_project(project_id)
    repository = SplitPreviewRepository(store.state_root)
    try:
        if len(parts) == 4:
            send_json(HTTPStatus.OK, repository.list(project_id))
        elif len(parts) == 5:
            send_json(HTTPStatus.OK, repository.read(project_id, parts[4]))
        elif parts[5] != "parts" or parts[7] not in {"image", "image.png"}:
            return False
        elif parts[6] not in {"left", "right"}:
            send_error(
                HTTPStatus.BAD_REQUEST,
                "invalid_split_side",
                "Split preview side must be left or right.",
            )
        else:
            send_file(repository.child_image(project_id, parts[4], parts[6]))
    except SplitPreviewNotFound:
        send_error(
            HTTPStatus.NOT_FOUND,
            "split_preview_not_found",
            "Split preview was not found.",
        )
    except SplitPreviewRepositoryError:
        send_error(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "split_preview_repository_error",
            "The local split preview repository could not complete the request.",
        )
    return True
