"""Same-origin HTTP adapter for automatic P10.6b v2 jobs."""

from __future__ import annotations

from http import HTTPStatus
import re
from urllib.parse import urlsplit

from .http_json_request import (
    HttpJsonRequestError, drain_bounded_request_body,
    read_json_object_request,
)
from .http_security import is_loopback_host
from .p10_motion_instance_v3_job_v2 import P10MotionInstanceV3JobV2Error
from .p10_motion_instance_v3_manager_v2 import (
    P10MotionInstanceV3ManagerV2Error,
)

INTENT = "p10-body-sway-motion-instance-v3-v2"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_PREFIX = ["api", "p10", "runtime-capture", "jobs"]


def is_p10_motion_instance_v3_v2_path(parts):
    return len(parts) >= 13 and parts[:4] == _PREFIX \
        and parts[5:8] == [
            "visual-review-v2", "safety-analysis-v2", "runs",
        ] and parts[9:11] == ["dynamic-seam-v2", "runs"] \
        and parts[12] == "motion-instance-v3-v2"


def p10_motion_instance_v3_v2_allow_methods(parts):
    route = _route(parts)
    if route is None:
        return "OPTIONS" if is_p10_motion_instance_v3_v2_path(parts) else None
    if route[0] == "runs":
        return "POST, OPTIONS"
    if route[0] == "result":
        return "GET, OPTIONS"
    return "GET, HEAD, OPTIONS"


def dispatch_p10_motion_instance_v3_v2_get(parts, manager, handler):
    if not is_p10_motion_instance_v3_v2_path(parts):
        return False
    try:
        _read_headers(handler.headers)
        route = _route(parts)
        if route is None or route[0] == "runs":
            return _error(handler, HTTPStatus.NOT_FOUND, "not_found")
        kind, job, safety, dynamic, run = route
        if kind == "result" and handler.command == "HEAD":
            return send_p10_motion_instance_v3_v2_method_not_allowed(
                parts, handler,
            )
        value = manager.entry(job, safety, dynamic) if kind == "entry" \
            else manager.get(job, safety, dynamic, run) if kind == "run" \
            else manager.result(job, safety, dynamic, run)
        handler._send_visual_json(HTTPStatus.OK, value)
    except _Security as exc:
        handler._send_visual_json(HTTPStatus.FORBIDDEN, {
            "error": exc.code, "message": str(exc),
        })
    except (P10MotionInstanceV3ManagerV2Error,
            P10MotionInstanceV3JobV2Error):
        _error(handler, HTTPStatus.CONFLICT,
               "motion_instance_v3_v2_not_ready")
    except Exception:
        _error(handler, HTTPStatus.INTERNAL_SERVER_ERROR,
               "motion_instance_v3_v2_error")
    return True


def dispatch_p10_motion_instance_v3_v2_post(
    parts, handler, manager, send_json,
):
    route = _route(parts)
    if route is None or route[0] != "runs":
        return False
    try:
        _write_headers(handler.headers)
        payload = read_json_object_request(handler, maximum_bytes=1024)
        if payload:
            send_json(HTTPStatus.BAD_REQUEST, {
                "error": "invalid_motion_instance_v3_v2_request",
                "message": "P10.6b v2 start request must be empty.",
            })
        else:
            send_json(HTTPStatus.ACCEPTED, manager.submit(
                route[1], route[2], route[3],
            ))
    except _Security as exc:
        drain_bounded_request_body(handler, maximum_bytes=1024)
        send_json(HTTPStatus.FORBIDDEN, {
            "error": exc.code, "message": str(exc),
        })
    except HttpJsonRequestError as exc:
        send_json(exc.status, {
            "error": exc.code, "message": exc.public_message,
        })
    except (P10MotionInstanceV3ManagerV2Error,
            P10MotionInstanceV3JobV2Error):
        send_json(HTTPStatus.CONFLICT, {
            "error": "motion_instance_v3_v2_not_ready",
            "message": "The exact completed P10.5d v2 result is unavailable.",
        })
    except Exception:
        send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
            "error": "motion_instance_v3_v2_error",
            "message": "P10.6b v2 request failed closed.",
        })
    return True


def send_p10_motion_instance_v3_v2_method_not_allowed(parts, handler):
    methods = p10_motion_instance_v3_v2_allow_methods(parts) or "OPTIONS"
    handler._send_bytes(
        HTTPStatus.METHOD_NOT_ALLOWED,
        b'{"error":"method_not_allowed","message":"Method not allowed."}',
        "application/json; charset=utf-8", extra_headers={"Allow": methods},
        visual_review=True,
    )
    return True


def _route(parts):
    if not is_p10_motion_instance_v3_v2_path(parts) \
            or any(_SHA.fullmatch(parts[index]) is None
                   for index in (4, 8, 11)):
        return None
    tail = parts[13:]
    base = (parts[4], parts[8], parts[11])
    if not tail:
        return "entry", *base, None
    if tail == ["runs"]:
        return "runs", *base, None
    if len(tail) in {2, 3} and tail[0] == "runs" \
            and _SHA.fullmatch(tail[1]):
        if len(tail) == 2:
            return "run", *base, tail[1]
        if tail[2] == "result":
            return "result", *base, tail[1]
    return None


class _Security(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _read_headers(headers):
    site = _one(headers, "Sec-Fetch-Site", False)
    if site is not None and site not in {"same-origin", "none"}:
        raise _Security("forbidden_fetch_site", "Request is not same-origin.")


def _write_headers(headers):
    host, origin = _one(headers, "Host", True), _one(headers, "Origin", True)
    try:
        parsed = urlsplit(f"//{host}")
        local = parsed.hostname and is_loopback_host(parsed.hostname) \
            and parsed.username is None and parsed.password is None \
            and not parsed.path and not parsed.query and not parsed.fragment
        parsed.port
    except (TypeError, ValueError):
        local = False
    if not local:
        raise _Security("forbidden_host", "Host must be loopback-local.")
    if origin != f"http://{host}":
        raise _Security("forbidden_origin", "Origin must match Host.")
    if _one(headers, "X-Autospine-Intent", True) != INTENT:
        raise _Security("forbidden_intent", "P10.6b v2 intent is missing.")
    _read_headers(headers)


def _one(headers, name, required):
    values = headers.get_all(name, []) or []
    if len(values) != 1:
        if not required and not values:
            return None
        raise _Security("forbidden_headers", f"Exactly one {name} is required.")
    value = values[0]
    if type(value) is not str or not value or value != value.strip() \
            or any(character in value for character in "\r\n\0"):
        raise _Security("forbidden_headers", f"{name} is invalid.")
    return value


def _error(handler, status, code):
    handler._send_visual_json(status, {
        "error": code,
        "message": "The exact P10.6b v2 resource is unavailable.",
    })
    return True


__all__ = [
    "dispatch_p10_motion_instance_v3_v2_get",
    "dispatch_p10_motion_instance_v3_v2_post",
    "is_p10_motion_instance_v3_v2_path",
    "p10_motion_instance_v3_v2_allow_methods",
    "send_p10_motion_instance_v3_v2_method_not_allowed",
]
