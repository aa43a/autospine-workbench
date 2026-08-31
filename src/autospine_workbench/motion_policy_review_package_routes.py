"""Loopback GET routes for validated automatic P9 review packages."""

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
from .body_sway_probe_routes import (
    dispatch_body_sway_probe_get,
    is_body_sway_probe_path,
)
from .idle_behavior_review_routes import (
    dispatch_idle_behavior_review_get,
    is_idle_behavior_review_get_path,
)

from .motion_policy_review_packages import (
    MotionPolicyReviewPackageError,
    get_motion_policy_review_package,
    list_motion_policy_review_packages,
)
from .motion_policy_project_scope import (
    MotionPolicyProjectScopeError,
    resolve_motion_policy_project_scope,
)
from .motion_policy_seam_review_entry_routes import (
    dispatch_motion_policy_seam_review_entry_get,
    is_motion_policy_seam_review_entry_path,
)
from .project_store import ProjectStore, ProjectStoreError


SendJson = Callable[[int, Any], None]
ALLOW_METHODS = "GET, HEAD, OPTIONS"


def is_motion_policy_review_package_path(parts: list[str]) -> bool:
    return is_body_sway_probe_path(parts) \
        or is_idle_behavior_review_get_path(parts) \
        or is_motion_policy_seam_review_entry_path(parts) or (
        parts[:3] == ["api", "motion-policy", "review-packages"]
        and len(parts) in {3, 4}
    )


def dispatch_motion_policy_review_package_get(
    parts: list[str], store: ProjectStore, send_json: SendJson,
    request_target: str | None = None,
) -> bool:
    if dispatch_body_sway_probe_get(parts, store, send_json):
        return True
    if dispatch_idle_behavior_review_get(
        parts, store, send_json, request_target,
    ):
        return True
    if dispatch_motion_policy_seam_review_entry_get(parts, store, send_json):
        return True
    if parts == ["api", "motion-policy", "review-packages"]:
        try:
            project_ids, project_scope = resolve_motion_policy_project_scope(
                store, request_target,
            )
            before = rebuild_current_project_chains(store, project_ids)
            payload = list_motion_policy_review_packages(
                store.state_root, current_project_chains=before,
                project_ids=project_scope,
            )
            after = rebuild_current_project_chains(store, project_ids)
            require_unchanged_current_project_chains(before, after)
            send_json(HTTPStatus.OK, payload)
        except CurrentProjectChainChangedError:
            _chain_changed(send_json)
        except (CurrentProjectChainError, ProjectStoreError):
            _chain_unavailable(send_json)
        except MotionPolicyProjectScopeError:
            _invalid_scope(send_json)
        except MotionPolicyReviewPackageError:
            _internal(send_json)
        return True
    if len(parts) == 4 \
            and parts[:3] == ["api", "motion-policy", "review-packages"]:
        try:
            project_ids, project_scope = resolve_motion_policy_project_scope(
                store, request_target,
            )
            before = rebuild_current_project_chains(store, project_ids)
            package = get_motion_policy_review_package(
                store.state_root, parts[3],
                current_project_chains=before,
                project_ids=project_scope,
            )
            after = rebuild_current_project_chains(store, project_ids)
            require_unchanged_current_project_chains(before, after)
        except MotionPolicyReviewPackageError:
            send_json(HTTPStatus.NOT_FOUND, {
                "error": "motion_policy_package_not_found",
                "message": "No validated automatic review package is available.",
            })
        except CurrentProjectChainChangedError:
            _chain_changed(send_json)
        except (CurrentProjectChainError, ProjectStoreError):
            _chain_unavailable(send_json)
        except MotionPolicyProjectScopeError:
            _invalid_scope(send_json)
        else:
            send_json(HTTPStatus.OK, package)
        return True
    return False


def send_motion_policy_review_package_method_not_allowed(handler: Any) -> None:
    body = json.dumps({
        "error": "method_not_allowed", "message": "Method not allowed.",
    }, separators=(",", ":")).encode("utf-8")
    handler._send_bytes(  # noqa: SLF001 - route adapter uses handler primitive
        HTTPStatus.METHOD_NOT_ALLOWED, body,
        "application/json; charset=utf-8",
        extra_headers={"Allow": ALLOW_METHODS}, visual_review=True,
    )


def _project_ids(store: ProjectStore) -> tuple[str, ...]:
    return store.discover_project_ids()


def _chain_changed(send_json: SendJson) -> None:
    send_json(HTTPStatus.CONFLICT, {
        "error": "motion_policy_project_chain_changed",
        "message": "The project changed; reload the motion-policy packages.",
    })


def _chain_unavailable(send_json: SendJson) -> None:
    send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
        "error": "motion_policy_project_chain_unavailable",
        "message": "The current project chain could not be inspected.",
    })


def _internal(send_json: SendJson) -> None:
    send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
        "error": "motion_policy_package_error",
        "message": "Automatic review packages could not be inspected.",
    })


def _invalid_scope(send_json: SendJson) -> None:
    send_json(HTTPStatus.BAD_REQUEST, {
        "error": "invalid_motion_policy_project_scope",
        "message": "The motion-policy project scope is invalid.",
    })
