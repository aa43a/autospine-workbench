"""Path-free HTTP adapter for asynchronous P10.4b v2 analysis."""

from __future__ import annotations

from http import HTTPStatus
import re
from typing import Any, Callable

from .http_json_request import (
    HttpJsonRequestError, drain_bounded_request_body,
    read_json_object_request,
)
from .p10_safety_analysis_job_store_v2 import (
    P10SafetyAnalysisJobStoreV2Error,
)
from .p10_safety_analysis_manager_v2 import (
    P10SafetyAnalysisManagerV2, P10SafetyAnalysisManagerV2Error,
)
from .p10_safety_analysis_v2_http_security import (
    P10SafetyAnalysisV2HttpSecurityError,
    require_p10_safety_analysis_v2_headers,
    require_p10_safety_analysis_v2_read_headers,
)


SendJson = Callable[[int, Any], None]
MAX_REQUEST_BYTES = 1024
_PREFIX = ["api", "p10", "runtime-capture", "jobs"]
_FAMILY = ["visual-review-v2", "safety-analysis-v2"]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def is_p10_safety_analysis_v2_path(parts: list[str]) -> bool:
    return len(parts) >= 7 and parts[:4] == _PREFIX \
        and parts[5:7] == _FAMILY


def p10_safety_analysis_v2_allow_methods(parts: list[str]) -> str | None:
    route = _route(parts)
    if route is None:
        return "OPTIONS" if is_p10_safety_analysis_v2_path(parts) else None
    kind, _, _ = route
    if kind == "runs":
        return "POST, OPTIONS"
    if kind == "result":
        return "GET, OPTIONS"
    return "GET, HEAD, OPTIONS"


def dispatch_p10_safety_analysis_v2_get(
    parts: list[str], manager: P10SafetyAnalysisManagerV2,
    handler: Any,
) -> bool:
    if not is_p10_safety_analysis_v2_path(parts):
        return False
    try:
        require_p10_safety_analysis_v2_read_headers(handler.headers)
    except P10SafetyAnalysisV2HttpSecurityError as exc:
        handler._send_visual_json(HTTPStatus.FORBIDDEN, {
            "error": exc.code, "message": exc.public_message,
        })
        return True
    route = _route(parts)
    if route is None:
        _not_found(handler._send_visual_json)
        return True
    if route[0] == "runs":
        send_p10_safety_analysis_v2_method_not_allowed(parts, handler)
        return True
    kind, job_id, run_id = route
    if kind == "result" and handler.command == "HEAD":
        send_p10_safety_analysis_v2_method_not_allowed(parts, handler)
        return True
    try:
        if kind == "entry":
            value = manager.entry(job_id)
        elif kind == "run":
            value = manager.get(job_id, run_id)
        else:
            value = manager.result(job_id, run_id)
        handler._send_visual_json(HTTPStatus.OK, value)
    except (P10SafetyAnalysisManagerV2Error,
            P10SafetyAnalysisJobStoreV2Error):
        if kind == "entry":
            _not_ready(handler._send_visual_json)
        else:
            _not_found(handler._send_visual_json)
    except Exception:
        _internal_error(handler._send_visual_json)
    return True


def dispatch_p10_safety_analysis_v2_post(
    parts: list[str], handler: Any,
    manager: P10SafetyAnalysisManagerV2, send_json: SendJson,
) -> bool:
    route = _route(parts)
    if route is None or route[0] != "runs":
        return False
    job_id = route[1]
    try:
        require_p10_safety_analysis_v2_headers(handler.headers)
        payload = read_json_object_request(
            handler, maximum_bytes=MAX_REQUEST_BYTES,
        )
        if payload:
            send_json(HTTPStatus.BAD_REQUEST, {
                "error": "invalid_safety_analysis_v2_request",
                "message": "P10.4b v2 start request must be an empty object.",
            })
            return True
        send_json(HTTPStatus.ACCEPTED, manager.submit(job_id))
    except P10SafetyAnalysisV2HttpSecurityError as exc:
        drain_bounded_request_body(
            handler, maximum_bytes=MAX_REQUEST_BYTES,
        )
        send_json(HTTPStatus.FORBIDDEN, {
            "error": exc.code, "message": exc.public_message,
        })
    except HttpJsonRequestError as exc:
        send_json(exc.status, {
            "error": exc.code, "message": exc.public_message,
        })
    except (P10SafetyAnalysisManagerV2Error,
            P10SafetyAnalysisJobStoreV2Error):
        _not_ready(send_json)
    except Exception:
        _internal_error(send_json)
    return True


def send_p10_safety_analysis_v2_method_not_allowed(parts, handler) -> None:
    methods = p10_safety_analysis_v2_allow_methods(parts) or "OPTIONS"
    handler._send_bytes(  # noqa: SLF001 - route adapter primitive
        HTTPStatus.METHOD_NOT_ALLOWED,
        b'{"error":"method_not_allowed","message":"Method not allowed."}',
        "application/json; charset=utf-8",
        extra_headers={"Allow": methods}, visual_review=True,
    )


def _route(parts):
    if not is_p10_safety_analysis_v2_path(parts) \
            or _SHA256.fullmatch(parts[4]) is None:
        return None
    tail = parts[7:]
    if not tail:
        return "entry", parts[4], None
    if tail == ["runs"]:
        return "runs", parts[4], None
    if len(tail) in {2, 3} and tail[0] == "runs" \
            and _SHA256.fullmatch(tail[1]) is not None:
        if len(tail) == 2:
            return "run", parts[4], tail[1]
        if tail[2] == "result":
            return "result", parts[4], tail[1]
    return None


def _not_found(send_json):
    send_json(HTTPStatus.NOT_FOUND, {
        "error": "safety_analysis_v2_not_found",
        "message": "The exact P10.4b v2 resource was not found.",
    })


def _not_ready(send_json):
    send_json(HTTPStatus.CONFLICT, {
        "error": "safety_analysis_v2_not_ready",
        "message": "Current P10.4a v2 admission cannot start this analysis.",
    })


def _internal_error(send_json):
    send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
        "error": "safety_analysis_v2_error",
        "message": "The P10.4b v2 request could not be completed safely.",
    })


__all__ = [
    "dispatch_p10_safety_analysis_v2_get",
    "dispatch_p10_safety_analysis_v2_post",
    "is_p10_safety_analysis_v2_path",
    "p10_safety_analysis_v2_allow_methods",
    "send_p10_safety_analysis_v2_method_not_allowed",
]
