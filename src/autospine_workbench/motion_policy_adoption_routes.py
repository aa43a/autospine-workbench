"""Loopback HTTP adapter for exact P9 human adoption and publication."""

from __future__ import annotations

from http import HTTPStatus
import json
from typing import Any, Callable

from .http_json_request import (
    HttpJsonRequestError,
    drain_bounded_request_body,
    read_json_object_request,
)
from .motion_policy_adoption import (
    MotionPolicyAdoptionError,
    MotionPolicyAdoptionPackageNotFoundError,
    MotionPolicyAdoptionUnavailableError,
    adopt_motion_policy_package,
)
from .motion_policy_adoption_http_security import (
    MotionPolicyAdoptionHttpSecurityError,
    require_motion_policy_adoption_headers,
)
from .motion_policy_decision_validation import MAX_DOCUMENT_BYTES
from .project_store import ProjectStore


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
        receipt = adopt_motion_policy_package(
            store.state_root, parts[3], request,
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
