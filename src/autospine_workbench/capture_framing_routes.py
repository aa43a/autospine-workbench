"""Loopback HTTP adapter for P10.2b capture-framing decisions."""

from __future__ import annotations

from http import HTTPStatus
import json
from typing import Any, Callable

from .capture_framing_application import (
    CaptureFramingApplication,
    CaptureFramingApplicationHeadChanged,
    CaptureFramingApplicationHistorical,
    CaptureFramingApplicationInvalid,
    CaptureFramingApplicationNotFound,
    CaptureFramingApplicationUnavailable,
)
from .capture_framing_history import CaptureFramingRevisionConflict
from .capture_framing_http_security import (
    CaptureFramingHttpSecurityError,
    require_capture_framing_headers,
)
from .capture_framing_profile import MAX_REQUEST_BYTES
from .current_project_chain import (
    CurrentProjectChainChangedError,
    CurrentProjectChainError,
)
from .http_json_request import (
    HttpJsonRequestError,
    drain_bounded_request_body,
    read_json_object_request,
)
from .project_store import ProjectStore, ProjectStoreError


SendJson = Callable[[int, Any], None]
ALLOW_METHODS = "POST, OPTIONS"
_PREFIX = ["api", "idle-behavior", "structural-probes"]


def is_capture_framing_mutation_path(parts: list[str]) -> bool:
    return len(parts) == 5 and parts[:3] == _PREFIX \
        and parts[4] == "capture-framing-decisions"


def dispatch_capture_framing_post(
    parts: list[str], handler: Any, store: ProjectStore, send_json: SendJson,
) -> bool:
    """CAS one explicitly confirmed framing decision and expose no paths."""

    if not is_capture_framing_mutation_path(parts):
        return False
    try:
        require_capture_framing_headers(handler.headers)
        payload = read_json_object_request(
            handler, maximum_bytes=MAX_REQUEST_BYTES,
        )
        receipt = CaptureFramingApplication(store).submit(parts[3], payload)
        send_json(HTTPStatus.OK, receipt)
    except CaptureFramingHttpSecurityError as exc:
        drain_bounded_request_body(handler, maximum_bytes=MAX_REQUEST_BYTES)
        send_json(HTTPStatus.FORBIDDEN, {
            "error": exc.code, "message": exc.public_message,
        })
    except HttpJsonRequestError as exc:
        send_json(exc.status, {
            "error": exc.code, "message": exc.public_message,
        })
    except CaptureFramingApplicationNotFound:
        send_json(HTTPStatus.NOT_FOUND, {
            "error": "capture_framing_candidate_not_found",
            "message": "The exact capture-framing candidate is unavailable.",
        })
    except CaptureFramingApplicationHistorical:
        send_json(HTTPStatus.CONFLICT, {
            "error": "capture_framing_historical_read_only",
            "message": "Historical structural-probe packages are read-only.",
        })
    except CaptureFramingApplicationInvalid:
        send_json(HTTPStatus.BAD_REQUEST, {
            "error": "invalid_capture_framing_submission",
            "message": "The capture-framing review submission is invalid.",
        })
    except CaptureFramingRevisionConflict as exc:
        send_json(HTTPStatus.CONFLICT, {
            "error": "capture_framing_revision_conflict",
            "message": "Framing revision is stale; reload exact history.",
            "requested_revision": exc.requested_revision,
            "current_revision": exc.current_revision,
            "requested_head_decision_sha256": exc.requested_head,
            "current_head_decision_sha256": exc.current_head,
        })
    except (
        CaptureFramingApplicationHeadChanged,
        CurrentProjectChainChangedError,
    ):
        send_json(HTTPStatus.CONFLICT, {
            "error": "capture_framing_source_changed",
            "message": "The project or P10.1 head changed; reload P10.2.",
        })
    except CaptureFramingApplicationUnavailable:
        send_json(HTTPStatus.CONFLICT, {
            "error": "capture_framing_unavailable",
            "message": "The exact framing decision could not be recorded.",
        })
    except (CurrentProjectChainError, ProjectStoreError):
        send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
            "error": "capture_framing_project_chain_unavailable",
            "message": "The current project chain could not be inspected.",
        })
    return True


def send_capture_framing_method_not_allowed(handler: Any) -> None:
    body = json.dumps({
        "error": "method_not_allowed", "message": "Method not allowed.",
    }, separators=(",", ":")).encode("utf-8")
    handler._send_bytes(  # noqa: SLF001 - route adapter primitive
        HTTPStatus.METHOD_NOT_ALLOWED,
        body,
        "application/json; charset=utf-8",
        extra_headers={"Allow": ALLOW_METHODS},
        visual_review=True,
    )
