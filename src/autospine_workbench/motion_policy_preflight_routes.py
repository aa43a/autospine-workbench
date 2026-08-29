"""Loopback HTTP adapter for zero-write P9 motion-policy preflight."""

from __future__ import annotations

from http import HTTPStatus
import json
from typing import Any, Callable

from .http_json_request import (
    HttpJsonRequestError,
    drain_bounded_request_body,
    read_json_object_request,
)
from .motion_policy_preflight import (
    MotionPolicyPreflightError,
    compile_motion_policy_preflight,
)
from .motion_policy_preflight_http_security import (
    MotionPolicyPreflightHttpSecurityError,
    require_motion_policy_preflight_headers,
)


MAX_REQUEST_BYTES = 48 * 1024 * 1024
ALLOW_METHODS = "POST, OPTIONS"
_PATH = ["api", "motion-policy", "preflight"]
SendJson = Callable[[int, Any], None]


def is_motion_policy_preflight_path(parts: list[str]) -> bool:
    return parts == _PATH


def dispatch_motion_policy_preflight_post(
    parts: list[str], handler: Any, send_json: SendJson,
) -> bool:
    """Validate one in-memory request without reading or writing workspace state."""

    if not is_motion_policy_preflight_path(parts):
        return False
    try:
        require_motion_policy_preflight_headers(handler.headers)
        request = read_json_object_request(
            handler, maximum_bytes=MAX_REQUEST_BYTES
        )
        send_json(HTTPStatus.OK, compile_motion_policy_preflight(request))
    except MotionPolicyPreflightHttpSecurityError as exc:
        drain_bounded_request_body(handler, maximum_bytes=MAX_REQUEST_BYTES)
        send_json(HTTPStatus.FORBIDDEN, {
            "error": exc.code, "message": exc.public_message,
        })
    except HttpJsonRequestError as exc:
        send_json(exc.status, {
            "error": exc.code, "message": exc.public_message,
        })
    except MotionPolicyPreflightError:
        send_json(HTTPStatus.BAD_REQUEST, {
            "error": "invalid_motion_policy_preflight_request",
            "message": "The motion-policy preflight request is invalid.",
        })
    return True


def send_motion_policy_preflight_method_not_allowed(handler: Any) -> None:
    body = json.dumps({
        "error": "method_not_allowed", "message": "Method not allowed.",
    }, separators=(",", ":")).encode("utf-8")
    handler._send_bytes(  # noqa: SLF001 - route adapter uses handler primitive
        HTTPStatus.METHOD_NOT_ALLOWED, body,
        "application/json; charset=utf-8",
        extra_headers={"Allow": ALLOW_METHODS}, visual_review=True,
    )
