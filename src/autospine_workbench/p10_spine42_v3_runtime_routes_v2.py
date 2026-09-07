"""Path-free HTTP adapter for authorized P10.7b v2 Runtime jobs."""

from __future__ import annotations

from http import HTTPStatus
import re
from urllib.parse import urlsplit

from .http_json_request import (
    HttpJsonRequestError, drain_bounded_request_body,
    read_json_object_request,
)
from .p10_spine42_v3_runtime_http_security_v2 import (
    P10Spine42V3RuntimeHttpSecurityV2Error,
    require_p10_spine42_v3_runtime_read_headers_v2,
    require_p10_spine42_v3_runtime_write_headers_v2,
)
from .p10_spine42_v3_runtime_manager_v2 import (
    P10Spine42V3RuntimeManagerV2Error,
)
from .p10_spine42_v3_runtime_preflight_validation_v2 import (
    require_preflight_payload_v2,
)


MAX_REQUEST_BYTES = 2 * 1024
_PREFIX = ["api", "p10", "spine42-v3-runtime-v2"]
_SHA = re.compile(r"^[0-9a-f]{64}$")


def is_p10_spine42_v3_runtime_v2_path(parts):
    return len(parts) >= 3 and parts[:3] == _PREFIX


def p10_spine42_v3_runtime_v2_allow_methods(parts):
    route = _route(parts)
    if route == "candidates" or route == "job":
        return "GET, HEAD, OPTIONS"
    if route == "jobs":
        return "POST, OPTIONS"
    return "OPTIONS" if is_p10_spine42_v3_runtime_v2_path(parts) else None


def dispatch_p10_spine42_v3_runtime_v2_get(parts, manager, handler):
    if not is_p10_spine42_v3_runtime_v2_path(parts):
        return False
    route = _route(parts)
    if route == "jobs":
        return send_p10_spine42_v3_runtime_v2_method_not_allowed(
            parts, handler,
        )
    try:
        require_p10_spine42_v3_runtime_read_headers_v2(handler.headers)
        continuation = _query(handler.path, candidates=route == "candidates")
        if route is None:
            return _error(handler, HTTPStatus.NOT_FOUND,
                          "runtime_v2_not_found",
                          "The exact P10.7b v2 resource was not found.")
        value = manager.catalog(continuation) if route == "candidates" \
            else manager.get(parts[4])
        handler._send_visual_json(HTTPStatus.OK, value)
    except P10Spine42V3RuntimeHttpSecurityV2Error as exc:
        _error(handler, HTTPStatus.FORBIDDEN, exc.code, exc.public_message)
    except _RequestError as exc:
        _error(handler, HTTPStatus.BAD_REQUEST, exc.code, exc.message)
    except P10Spine42V3RuntimeManagerV2Error:
        if route == "job":
            _error(handler, HTTPStatus.NOT_FOUND, "runtime_v2_job_not_found",
                   "The exact P10.7b v2 job was not found.")
        else:
            _error(handler, HTTPStatus.CONFLICT,
                   "runtime_v2_catalog_not_ready",
                   "P10.7b v2 candidates are not currently available.")
    except Exception:
        _internal_error(handler)
    return True


def dispatch_p10_spine42_v3_runtime_v2_post(
    parts, handler, manager, send_json,
):
    if _route(parts) != "jobs":
        return False
    try:
        _query(handler.path, candidates=False)
        require_p10_spine42_v3_runtime_write_headers_v2(handler.headers)
        payload = read_json_object_request(
            handler, maximum_bytes=MAX_REQUEST_BYTES,
        )
        require_preflight_payload_v2(payload)
        catalog = manager.catalog(None)
        source = _selection_source(catalog, payload)
        send_json(HTTPStatus.ACCEPTED, manager.submit(
            payload, selection_source=source,
        ))
    except P10Spine42V3RuntimeHttpSecurityV2Error as exc:
        drain_bounded_request_body(
            handler, maximum_bytes=MAX_REQUEST_BYTES,
        )
        _send_error(send_json, HTTPStatus.FORBIDDEN,
                    exc.code, exc.public_message)
    except HttpJsonRequestError as exc:
        _send_error(send_json, exc.status, exc.code, exc.public_message)
    except (_RequestError, ValueError):
        _send_error(
            send_json, HTTPStatus.BAD_REQUEST, "invalid_runtime_v2_request",
            "P10.7b v2 requires the exact six-field authorization request.",
        )
    except P10Spine42V3RuntimeManagerV2Error:
        _send_error(
            send_json, HTTPStatus.CONFLICT, "runtime_v2_job_not_ready",
            "The exact P10.7b v2 job could not be queued safely.",
        )
    except Exception:
        _send_error(
            send_json, HTTPStatus.INTERNAL_SERVER_ERROR,
            "runtime_v2_error",
            "The P10.7b v2 request failed closed.",
        )
    return True


def send_p10_spine42_v3_runtime_v2_method_not_allowed(parts, handler):
    methods = p10_spine42_v3_runtime_v2_allow_methods(parts) or "OPTIONS"
    handler._send_bytes(
        HTTPStatus.METHOD_NOT_ALLOWED,
        b'{"error":"method_not_allowed","message":"Method not allowed."}',
        "application/json; charset=utf-8",
        extra_headers={"Allow": methods}, visual_review=True,
    )
    return True


def _route(parts):
    if not is_p10_spine42_v3_runtime_v2_path(parts):
        return None
    tail = parts[3:]
    if tail == ["candidates"]:
        return "candidates"
    if tail == ["jobs"]:
        return "jobs"
    if len(tail) == 2 and tail[0] == "jobs" \
            and _SHA.fullmatch(tail[1]) is not None:
        return "job"
    return None


def _query(target, *, candidates):
    try:
        query = urlsplit(target).query
    except (TypeError, ValueError) as exc:
        raise _RequestError("invalid_runtime_v2_query",
                            "Request query is invalid.") from exc
    if not query:
        return None
    prefix = "spine_run_id="
    if not candidates or not query.startswith(prefix) \
            or _SHA.fullmatch(query[len(prefix):]) is None:
        raise _RequestError(
            "invalid_runtime_v2_query",
            "Only one lowercase spine_run_id query is supported.",
        )
    return query[len(prefix):]


def _selection_source(catalog, payload):
    if type(catalog) is not dict or type(catalog.get("selection")) is not dict:
        raise RuntimeError("catalog projection invalid")
    selection = catalog["selection"]
    automatic = selection.get("mode") == "automatic" \
        and selection.get("recommended_candidate_id") == payload["candidate_id"] \
        and selection.get("recommended_entry_sha256") == payload["entry_sha256"]
    return "automatic" if automatic else "explicit"


class _RequestError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def _error(handler, status, code, message):
    handler._send_visual_json(status, {"error": code, "message": message})
    return True


def _send_error(send_json, status, code, message):
    send_json(status, {"error": code, "message": message})


def _internal_error(handler):
    _error(handler, HTTPStatus.INTERNAL_SERVER_ERROR, "runtime_v2_error",
           "The P10.7b v2 request failed closed.")


__all__ = [
    "MAX_REQUEST_BYTES", "dispatch_p10_spine42_v3_runtime_v2_get",
    "dispatch_p10_spine42_v3_runtime_v2_post",
    "is_p10_spine42_v3_runtime_v2_path",
    "p10_spine42_v3_runtime_v2_allow_methods",
    "send_p10_spine42_v3_runtime_v2_method_not_allowed",
]
