"""Loopback HTTP adapter for exact P9 human adoption and publication."""

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
from .motion_policy_adoption import (
    MotionPolicyAdoptionError,
    MotionPolicyAdoptionHistoricalError,
    MotionPolicyAdoptionPackageNotFoundError,
    MotionPolicyAdoptionUnavailableError,
    adopt_motion_policy_package,
)
from .motion_policy_adoption_http_security import (
    MotionPolicyAdoptionHttpSecurityError,
    require_motion_policy_adoption_headers,
)
from .motion_policy_decision_validation import MAX_DOCUMENT_BYTES
from .motion_policy_review_packages import (
    MotionPolicyReviewPackageError,
    MotionPolicyReviewPackageHistoricalError,
    require_current_motion_policy_review_package,
)
from .project_store import ProjectStore, ProjectStoreError


MAX_REQUEST_BYTES = MAX_DOCUMENT_BYTES + 1024 * 1024
ALLOW_METHODS = "POST, OPTIONS"
SendJson = Callable[[int, Any], None]


def is_motion_policy_adoption_path(parts: list[str]) -> bool:
    return len(parts) == 5 \
        and parts[:3] == ["api", "motion-policy", "review-packages"] \
        and parts[4] == "adoptions"


def dispatch_motion_policy_adoption_post(
    parts: list[str], handler: Any, store: ProjectStore,
    send_json: SendJson,
) -> bool:
    """Adopt one exact package and return a path-free verified receipt."""

    if not is_motion_policy_adoption_path(parts):
        return False
    try:
        require_motion_policy_adoption_headers(handler.headers)
        request = read_json_object_request(
            handler, maximum_bytes=MAX_REQUEST_BYTES,
        )
        project_ids = _project_ids(store)
        before = rebuild_current_project_chains(store, project_ids)
        try:
            require_current_motion_policy_review_package(
                store.state_root,
                parts[3],
                current_project_chains=before,
            )
        except MotionPolicyReviewPackageHistoricalError as exc:
            raise MotionPolicyAdoptionHistoricalError(
                "Historical motion-policy packages are read-only"
            ) from exc
        except MotionPolicyReviewPackageError as exc:
            raise MotionPolicyAdoptionPackageNotFoundError(
                "The exact motion-policy package is unavailable"
            ) from exc
        after = rebuild_current_project_chains(store, project_ids)
        require_unchanged_current_project_chains(before, after)
        receipt = adopt_motion_policy_package(
            store.state_root,
            parts[3],
            request,
            current_project_chains=after,
        )
        send_json(HTTPStatus.OK, receipt)
    except MotionPolicyAdoptionHttpSecurityError as exc:
        drain_bounded_request_body(handler, maximum_bytes=MAX_REQUEST_BYTES)
        send_json(HTTPStatus.FORBIDDEN, {
            "error": exc.code, "message": exc.public_message,
        })
    except HttpJsonRequestError as exc:
        send_json(exc.status, {
            "error": exc.code, "message": exc.public_message,
        })
    except MotionPolicyAdoptionPackageNotFoundError:
        send_json(HTTPStatus.NOT_FOUND, {
            "error": "motion_policy_package_not_found",
            "message": "The exact motion-policy package is unavailable.",
        })
    except MotionPolicyAdoptionHistoricalError:
        send_json(HTTPStatus.CONFLICT, {
            "error": "motion_policy_package_historical_read_only",
            "message": "Historical motion-policy packages are read-only.",
        })
    except MotionPolicyAdoptionError:
        send_json(HTTPStatus.BAD_REQUEST, {
            "error": "invalid_motion_policy_adoption_request",
            "message": "The motion-policy adoption request is invalid.",
        })
    except MotionPolicyAdoptionUnavailableError:
        send_json(HTTPStatus.CONFLICT, {
            "error": "motion_policy_adoption_unavailable",
            "message": (
                "The exact motion-policy package could not be published."
            ),
        })
    except CurrentProjectChainChangedError:
        send_json(HTTPStatus.CONFLICT, {
            "error": "motion_policy_project_chain_changed",
            "message": "The project changed; reload before adopting.",
        })
    except (CurrentProjectChainError, ProjectStoreError):
        send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
            "error": "motion_policy_project_chain_unavailable",
            "message": "The current project chain could not be inspected.",
        })
    return True


def send_motion_policy_adoption_method_not_allowed(handler: Any) -> None:
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
