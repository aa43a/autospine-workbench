"""Loopback routes for pending P9 drafts and explicit policy promotion."""

from __future__ import annotations

from http import HTTPStatus
import json
from typing import Any, Callable

from .current_project_chain import (
    CurrentProjectChainChangedError,
    CurrentProjectChainError,
    rebuild_current_project_chains,
    require_unchanged_current_project_chains,
)
from .http_json_request import (
    HttpJsonRequestError,
    drain_bounded_request_body,
    read_json_object_request,
)
from .p9_draft_policy_adoption import (
    P9DraftPolicyAdoptionError,
    P9DraftPolicyAdoptionHistoricalError,
    P9DraftPolicyAdoptionUnavailableError,
    prepare_p9_draft_policy_adoption,
    publish_p9_draft_policy_adoption,
)
from .p9_draft_policy_adoption_http_security import (
    P9DraftPolicyAdoptionHttpSecurityError,
    require_p9_draft_policy_adoption_headers,
)
from .p9_review_draft_reader import (
    P9ReviewDraftReadError,
    get_p9_review_draft,
    list_p9_review_drafts,
)
from .motion_policy_project_scope import (
    MotionPolicyProjectScopeError,
    resolve_motion_policy_project_scope,
)
from .project_store import ProjectStore, ProjectStoreError
from .project_authoring_transaction import project_authoring_transaction


SendJson = Callable[[int, Any], None]
READ_METHODS = "GET, HEAD, OPTIONS"
WRITE_METHODS = "POST, OPTIONS"
MAX_REQUEST_BYTES = 16 * 1024


def is_motion_policy_review_draft_get_path(parts: list[str]) -> bool:
    return parts[:3] == ["api", "motion-policy", "review-drafts"] \
        and len(parts) in {3, 4}


def is_p9_draft_policy_adoption_path(parts: list[str]) -> bool:
    return len(parts) == 5 \
        and parts[:3] == ["api", "motion-policy", "review-drafts"] \
        and parts[4] == "policy-adoptions"


def dispatch_motion_policy_review_draft_get(
    parts: list[str], store: ProjectStore, send_json: SendJson,
    request_target: str | None = None,
) -> bool:
    if not is_motion_policy_review_draft_get_path(parts):
        return False
    try:
        project_ids, project_scope = resolve_motion_policy_project_scope(
            store, request_target,
        )
        before = rebuild_current_project_chains(store, project_ids)
        if len(parts) == 3:
            payload = list_p9_review_drafts(
                store.state_root, current_project_chains=before,
                project_ids=project_scope,
            )
        else:
            payload = get_p9_review_draft(
                store.state_root, parts[3],
                current_project_chains=before,
                project_ids=project_scope,
            )
        after = rebuild_current_project_chains(store, project_ids)
        require_unchanged_current_project_chains(before, after)
        send_json(HTTPStatus.OK, payload)
    except P9ReviewDraftReadError:
        send_json(HTTPStatus.NOT_FOUND, {
            "error": "motion_policy_draft_not_found",
            "message": "The exact pending motion-policy draft is unavailable.",
        })
    except CurrentProjectChainChangedError:
        _chain_changed(send_json)
    except (CurrentProjectChainError, ProjectStoreError):
        _chain_unavailable(send_json)
    except MotionPolicyProjectScopeError:
        send_json(HTTPStatus.BAD_REQUEST, {
            "error": "invalid_motion_policy_project_scope",
            "message": "The motion-policy project scope is invalid.",
        })
    return True


def dispatch_p9_draft_policy_adoption_post(
    parts: list[str], handler: Any, store: ProjectStore, send_json: SendJson,
) -> bool:
    if not is_p9_draft_policy_adoption_path(parts):
        return False
    try:
        require_p9_draft_policy_adoption_headers(handler.headers)
        request = read_json_object_request(
            handler, maximum_bytes=MAX_REQUEST_BYTES,
        )
        project_ids = store.discover_project_ids()
        before = rebuild_current_project_chains(store, project_ids)
        prepared = prepare_p9_draft_policy_adoption(
            store.state_root, parts[3], request,
            current_project_chains=before,
        )
        with project_authoring_transaction(
            store.state_root, prepared.project_id,
        ):
            after = rebuild_current_project_chains(store, project_ids)
            require_unchanged_current_project_chains(before, after)
            receipt = publish_p9_draft_policy_adoption(
                store.state_root, prepared,
                current_project_chains=after,
            )
        send_json(HTTPStatus.OK, receipt)
    except P9DraftPolicyAdoptionHttpSecurityError as exc:
        drain_bounded_request_body(handler, maximum_bytes=MAX_REQUEST_BYTES)
        send_json(HTTPStatus.FORBIDDEN, {
            "error": exc.code, "message": exc.public_message,
        })
    except HttpJsonRequestError as exc:
        send_json(exc.status, {
            "error": exc.code, "message": exc.public_message,
        })
    except P9ReviewDraftReadError:
        send_json(HTTPStatus.NOT_FOUND, {
            "error": "motion_policy_draft_not_found",
            "message": "The exact pending motion-policy draft is unavailable.",
        })
    except P9DraftPolicyAdoptionHistoricalError:
        send_json(HTTPStatus.CONFLICT, {
            "error": "motion_policy_draft_historical_read_only",
            "message": "Historical motion-policy drafts are read-only.",
        })
    except P9DraftPolicyAdoptionError:
        send_json(HTTPStatus.BAD_REQUEST, {
            "error": "invalid_depth_policy_adoption_request",
            "message": "The Depth-policy adoption request is invalid.",
        })
    except CurrentProjectChainChangedError:
        _chain_changed(send_json)
    except (CurrentProjectChainError, ProjectStoreError):
        _chain_unavailable(send_json)
    except P9DraftPolicyAdoptionUnavailableError:
        send_json(HTTPStatus.CONFLICT, {
            "error": "depth_policy_adoption_unavailable",
            "message": "The exact Depth-policy package could not be published.",
        })
    return True


def send_motion_policy_review_draft_method_not_allowed(
    handler: Any, *, write: bool = False,
) -> None:
    allow = WRITE_METHODS if write else READ_METHODS
    body = json.dumps({
        "error": "method_not_allowed", "message": "Method not allowed.",
    }, separators=(",", ":")).encode("utf-8")
    handler._send_bytes(  # noqa: SLF001
        HTTPStatus.METHOD_NOT_ALLOWED, body,
        "application/json; charset=utf-8",
        extra_headers={"Allow": allow}, visual_review=True,
    )


def _chain_changed(send_json: SendJson) -> None:
    send_json(HTTPStatus.CONFLICT, {
        "error": "motion_policy_project_chain_changed",
        "message": "The project changed; reload the pending draft.",
    })


def _chain_unavailable(send_json: SendJson) -> None:
    send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
        "error": "motion_policy_project_chain_unavailable",
        "message": "The current project chain could not be inspected.",
    })
