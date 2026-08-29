"""Loopback HTTP routes for assisted P10.1 body-sway review."""

from __future__ import annotations

from http import HTTPStatus
import json
from typing import Any, Callable

from .http_json_request import (
    HttpJsonRequestError,
    drain_bounded_request_body,
    read_json_object_request,
)
from .idle_behavior_review_application import (
    IdleBehaviorReviewApplication,
    IdleBehaviorReviewApplicationError,
    IdleBehaviorReviewApplicationInvalidSubmission,
    IdleBehaviorReviewApplicationNotFound,
    IdleBehaviorReviewApplicationUnavailable,
)
from .idle_behavior_review_history import (
    IdleBehaviorReviewRevisionConflict,
)
from .idle_behavior_review_http_security import (
    IdleBehaviorReviewHttpSecurityError,
    require_idle_behavior_review_headers,
)
from .idle_behavior_review_packages import (
    IdleBehaviorReviewPackageError,
    list_idle_behavior_review_packages,
)
from .idle_behavior_review_profile import MAX_REQUEST_BYTES
from .project_store import ProjectStore, ProjectStoreError


SendJson = Callable[[int, Any], None]
ALLOW_METHODS = "POST, OPTIONS"
_PREFIX = ["api", "idle-behavior", "review-packages"]
_LIST_FIELDS = (
    "package_id", "project_id", "motion_id", "clip_id",
    "motion_policy_package_id", "p9_decision_sha256", "status",
)


def is_idle_behavior_review_get_path(parts: list[str]) -> bool:
    return parts[:3] == _PREFIX and len(parts) in {3, 4}


def is_idle_behavior_review_mutation_path(parts: list[str]) -> bool:
    return len(parts) == 5 and parts[:3] == _PREFIX \
        and parts[4] == "decisions"


def dispatch_idle_behavior_review_get(
    parts: list[str], store: ProjectStore, send_json: SendJson,
) -> bool:
    """Serve a strict list projection or one exact replayed entry."""

    if not is_idle_behavior_review_get_path(parts):
        return False
    try:
        project_ids = _project_ids(store)
        if len(parts) == 3:
            inventory = list_idle_behavior_review_packages(
                store.state_root, project_ids=project_ids,
            )
            inventory["packages"] = [
                {field: row[field] for field in _LIST_FIELDS}
                for row in inventory["packages"]
            ]
            send_json(HTTPStatus.OK, inventory)
        else:
            entry = IdleBehaviorReviewApplication(store.state_root).prepare(
                parts[3], project_ids=project_ids,
            )
            send_json(HTTPStatus.OK, entry)
    except IdleBehaviorReviewApplicationNotFound:
        _not_found(send_json)
    except IdleBehaviorReviewPackageError:
        _internal(send_json)
    except IdleBehaviorReviewApplicationUnavailable:
        _unavailable(send_json)
    except (IdleBehaviorReviewApplicationError, ProjectStoreError):
        _internal(send_json)
    return True


def dispatch_idle_behavior_review_post(
    parts: list[str], handler: Any, store: ProjectStore,
    send_json: SendJson,
) -> bool:
    """CAS one explicitly confirmed human decision and return no paths."""

    if not is_idle_behavior_review_mutation_path(parts):
        return False
    try:
        require_idle_behavior_review_headers(handler.headers)
        payload = read_json_object_request(
            handler, maximum_bytes=MAX_REQUEST_BYTES,
        )
        receipt = IdleBehaviorReviewApplication(store.state_root).submit(
            parts[3], payload, project_ids=_project_ids(store),
        )
        send_json(HTTPStatus.OK, receipt)
    except IdleBehaviorReviewHttpSecurityError as exc:
        drain_bounded_request_body(handler, maximum_bytes=MAX_REQUEST_BYTES)
        send_json(HTTPStatus.FORBIDDEN, {
            "error": exc.code, "message": exc.public_message,
        })
    except HttpJsonRequestError as exc:
        send_json(exc.status, {
            "error": exc.code, "message": exc.public_message,
        })
    except IdleBehaviorReviewApplicationNotFound:
        _not_found(send_json)
    except IdleBehaviorReviewApplicationInvalidSubmission:
        send_json(HTTPStatus.BAD_REQUEST, {
            "error": "invalid_idle_behavior_review_submission",
            "message": "The body-sway review submission is invalid.",
        })
    except IdleBehaviorReviewRevisionConflict as exc:
        send_json(HTTPStatus.CONFLICT, {
            "error": "idle_behavior_review_revision_conflict",
            "message": "Review revision is stale; reload exact history.",
            "requested_revision": exc.requested_revision,
            "current_revision": exc.current_revision,
            "requested_head_decision_sha256": exc.requested_head,
            "current_head_decision_sha256": exc.current_head,
        })
    except IdleBehaviorReviewApplicationUnavailable:
        _unavailable(send_json)
    except (IdleBehaviorReviewApplicationError, ProjectStoreError):
        _internal(send_json)
    return True


def send_idle_behavior_review_method_not_allowed(handler: Any) -> None:
    body = json.dumps({
        "error": "method_not_allowed", "message": "Method not allowed.",
    }, separators=(",", ":")).encode("utf-8")
    handler._send_bytes(  # noqa: SLF001 - route adapter primitive
        HTTPStatus.METHOD_NOT_ALLOWED, body,
        "application/json; charset=utf-8",
        extra_headers={"Allow": ALLOW_METHODS}, visual_review=True,
    )


def _project_ids(store: ProjectStore) -> tuple[str, ...]:
    return tuple(project["id"] for project in store.list_projects())


def _not_found(send_json: SendJson) -> None:
    send_json(HTTPStatus.NOT_FOUND, {
        "error": "idle_behavior_review_package_not_found",
        "message": "The exact body-sway review package is unavailable.",
    })


def _unavailable(send_json: SendJson) -> None:
    send_json(HTTPStatus.CONFLICT, {
        "error": "idle_behavior_review_unavailable",
        "message": "The exact body-sway review could not be completed.",
    })


def _internal(send_json: SendJson) -> None:
    send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
        "error": "idle_behavior_review_error",
        "message": "The body-sway review request could not be completed safely.",
    })
