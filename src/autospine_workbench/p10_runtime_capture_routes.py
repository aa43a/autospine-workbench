"""Loopback HTTP adapter for package preflight and asynchronous P10 capture."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from .http_json_request import (
    HttpJsonRequestError,
    drain_bounded_request_body,
    read_json_object_request,
)
from .p10_capture_job_contract import P10CaptureJobContractError
from .p10_capture_job_manager import (
    P10CaptureJobManager,
    P10CaptureJobManagerError,
)
from .p10_capture_job_store import (
    MAX_REQUEST_BYTES,
    P10CaptureJobConflict,
    P10CaptureJobStoreError,
)
from .p10_runtime_capture_http_security import (
    P10RuntimeCaptureHttpSecurityError,
    require_p10_runtime_capture_headers,
)


SendJson = Callable[[int, Any], None]
_PREFIX = ["api", "p10", "runtime-capture"]


def p10_runtime_capture_allow_methods(parts: list[str]) -> str | None:
    if _preflight_path(parts) or _job_path(parts):
        return "GET, HEAD, OPTIONS"
    if _job_collection(parts):
        return "POST, OPTIONS"
    if is_p10_runtime_capture_path(parts):
        return "OPTIONS"
    return None


def is_p10_runtime_capture_path(parts: list[str]) -> bool:
    return len(parts) >= 3 and parts[:3] == _PREFIX


def dispatch_p10_runtime_capture_get(
    parts: list[str], manager: P10CaptureJobManager, send_json: SendJson,
) -> bool:
    if _preflight_path(parts):
        try:
            send_json(HTTPStatus.OK, manager.prepare(parts[4]))
        except P10CaptureJobManagerError:
            send_json(HTTPStatus.CONFLICT, {
                "error": "runtime_capture_preflight_unavailable",
                "message": "The current package cannot enter official Runtime capture.",
            })
        return True
    if _job_path(parts):
        try:
            send_json(HTTPStatus.OK, manager.get(parts[4]))
        except (P10CaptureJobStoreError, P10CaptureJobManagerError):
            send_json(HTTPStatus.NOT_FOUND, {
                "error": "runtime_capture_job_not_found",
                "message": "The exact Runtime capture job is unavailable.",
            })
        return True
    return False


def dispatch_p10_runtime_capture_post(
    parts: list[str], handler: Any,
    manager: P10CaptureJobManager, send_json: SendJson,
) -> bool:
    if not _job_collection(parts):
        return False
    try:
        require_p10_runtime_capture_headers(handler.headers)
        payload = read_json_object_request(
            handler, maximum_bytes=MAX_REQUEST_BYTES,
        )
        send_json(HTTPStatus.ACCEPTED, manager.submit(payload))
    except P10RuntimeCaptureHttpSecurityError as exc:
        drain_bounded_request_body(handler, maximum_bytes=MAX_REQUEST_BYTES)
        send_json(HTTPStatus.FORBIDDEN, {
            "error": exc.code, "message": exc.public_message,
        })
    except HttpJsonRequestError as exc:
        send_json(exc.status, {
            "error": exc.code, "message": exc.public_message,
        })
    except P10CaptureJobContractError:
        send_json(HTTPStatus.BAD_REQUEST, {
            "error": "invalid_runtime_capture_request",
            "message": "Both current identities and explicit confirmations are required.",
        })
    except P10CaptureJobConflict:
        send_json(HTTPStatus.CONFLICT, {
            "error": "runtime_capture_job_conflict",
            "message": "The exact Runtime capture job changed; reload its status.",
        })
    except (P10CaptureJobStoreError, P10CaptureJobManagerError):
        send_json(HTTPStatus.CONFLICT, {
            "error": "runtime_capture_job_unavailable",
            "message": "The Runtime capture job could not be queued safely.",
        })
    return True


def send_p10_runtime_capture_method_not_allowed(
    parts: list[str], handler: Any,
) -> None:
    methods = p10_runtime_capture_allow_methods(parts) or "OPTIONS"
    handler._send_bytes(  # noqa: SLF001 - route adapter primitive
        HTTPStatus.METHOD_NOT_ALLOWED,
        b'{"error":"method_not_allowed","message":"Method not allowed."}',
        "application/json; charset=utf-8",
        extra_headers={"Allow": methods}, visual_review=True,
    )


def _preflight_path(parts):
    return len(parts) == 5 and parts[:3] == _PREFIX and parts[3] == "packages"


def _job_collection(parts):
    return parts == [*_PREFIX, "jobs"]


def _job_path(parts):
    return len(parts) == 5 and parts[:4] == [*_PREFIX, "jobs"]


__all__ = [
    "dispatch_p10_runtime_capture_get", "dispatch_p10_runtime_capture_post",
    "is_p10_runtime_capture_path", "p10_runtime_capture_allow_methods",
    "send_p10_runtime_capture_method_not_allowed",
]
