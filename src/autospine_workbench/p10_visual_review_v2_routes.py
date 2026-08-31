"""Job-centric, path-free HTTP adapter for P10.3c v2 review."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from .body_sway_runtime_execution_reader import (
    VerifiedBodySwayRuntimeExecutionNotFound,
)
from .body_sway_visual_review_application_v2 import (
    BodySwayVisualReviewApplicationV2,
    BodySwayVisualReviewApplicationV2Error,
    BodySwayVisualReviewApplicationV2InvalidSubmission,
    BodySwayVisualReviewApplicationV2NotFound,
)
from .body_sway_visual_review_decision_v2 import (
    BodySwayVisualReviewDecisionV2Error,
)
from .body_sway_visual_review_errors_v2 import (
    BodySwayVisualReviewRevisionV2Conflict,
)
from .body_sway_visual_review_http_models import (
    candidate_response, exact_decision_response, history_response,
    submitted_response,
)
from .body_sway_visual_review_profile_v2 import (
    MAX_VISUAL_REVIEW_DOCUMENT_BYTES, MAX_VISUAL_REVIEW_REVISIONS,
)
from .body_sway_visual_review_submission import (
    BodySwayVisualReviewSubmissionError,
)
from .http_json_request import (
    HttpJsonRequestError, drain_bounded_request_body,
    read_json_object_request,
)
from .manifest_artifacts import LayerManifestError, require_sha256
from .p10_capture_job_manager import P10CaptureJobManager
from .p10_preview_v2_commands import P10PreviewV2CommandError
from .p10_visual_review_v2_context import (
    P10VisualReviewV2JobIncomplete, P10VisualReviewV2JobNotFound,
    P10VisualReviewV2SourceChanged,
    resolve_p10_visual_review_v2_context,
)
from .p10_visual_review_v2_http_security import (
    P10VisualReviewV2HttpSecurityError,
    require_p10_visual_review_v2_headers,
)
from .p10_visual_review_v2_http_responses import (
    internal_error as _internal_error,
    invalid_address as _invalid_address,
    invalid_submission as _invalid_submission,
    job_incomplete as _job_incomplete,
    not_found as _not_found,
    source_changed as _source_changed,
)
from .project_store import ProjectStore


SendJson = Callable[[int, Any], None]
SendBytes = Callable[[int, bytes, str, dict[str, str] | None], None]
_PREFIX = ["api", "p10", "runtime-capture", "jobs"]
_SEGMENT = "visual-review-v2"


def is_p10_visual_review_v2_path(parts: list[str]) -> bool:
    return len(parts) >= 6 and parts[:4] == _PREFIX \
        and parts[5] == _SEGMENT


def p10_visual_review_v2_allow_methods(parts: list[str]) -> str | None:
    if not is_p10_visual_review_v2_path(parts):
        return None
    tail = parts[6:]
    if len(tail) == 3 and tail[0] == "candidates" \
            and tail[2] == "decisions":
        return "PUT, OPTIONS"
    if _get_shape(tail):
        return "GET, HEAD, OPTIONS"
    return "OPTIONS"


def dispatch_p10_visual_review_v2_get(
    parts: list[str], manager: P10CaptureJobManager, store: ProjectStore,
    send_json: SendJson, send_bytes: SendBytes,
) -> bool:
    if not is_p10_visual_review_v2_path(parts):
        return False
    tail = parts[6:]
    if not _get_shape(tail):
        _not_found(send_json)
        return True
    try:
        context = resolve_p10_visual_review_v2_context(
            manager, store, parts[4],
        )
        service = BodySwayVisualReviewApplicationV2(store.state_root)
        if tail == ["candidate"]:
            prepared = service.prepare(context.address, context.preview)
            value = candidate_response(prepared)
            value["job"] = context.public_job()
            send_json(HTTPStatus.OK, value)
            return True
        if len(tail) == 6 and tail[0] == "candidates" \
                and tail[2] == "cases" and tail[4] == "image":
            image = service.image_evidence(
                context.address, context.preview,
                candidate_sha256=tail[1], case_id=tail[3],
                png_sha256=tail[5],
            )
            send_bytes(
                HTTPStatus.OK, image.png_bytes, "image/png",
                {"ETag": f'"{image.png_sha256}"'},
            )
            return True
        if len(tail) == 3 and tail[0] == "candidates" \
                and tail[2] == "history":
            candidate_address = require_sha256(
                tail[1], "Visual review v2 candidate",
            )
            prepared = service.prepare(context.address, context.preview)
            if prepared.candidate_sha256 != candidate_address:
                raise _NotFound
            value = history_response(prepared)
            value["job_id"] = context.job_id
            send_json(HTTPStatus.OK, value)
            return True
        revision = _revision(tail[3])
        exact = service.exact_decision(
            context.address, context.preview,
            candidate_sha256=tail[1], revision=revision,
            decision_sha256=tail[4],
        )
        value = exact_decision_response(exact)
        value["job_id"] = context.job_id
        send_json(HTTPStatus.OK, value)
    except _NotFound:
        _not_found(send_json)
    except (P10VisualReviewV2JobNotFound,
            BodySwayVisualReviewApplicationV2NotFound):
        _not_found(send_json)
    except P10VisualReviewV2JobIncomplete:
        _job_incomplete(send_json)
    except P10VisualReviewV2SourceChanged:
        _source_changed(send_json)
    except LayerManifestError:
        _invalid_address(send_json)
    except BodySwayVisualReviewApplicationV2Error as exc:
        if isinstance(exc.__cause__, VerifiedBodySwayRuntimeExecutionNotFound):
            _not_found(send_json)
        elif isinstance(exc.__cause__, P10PreviewV2CommandError):
            _source_changed(send_json)
        elif isinstance(exc.__cause__, LayerManifestError):
            _invalid_address(send_json)
        else:
            _internal_error(send_json)
    return True


def dispatch_p10_visual_review_v2_put(
    parts: list[str], manager: P10CaptureJobManager, store: ProjectStore,
    handler: Any, send_json: SendJson,
) -> bool:
    if not is_p10_visual_review_v2_path(parts):
        return False
    tail = parts[6:]
    if len(tail) != 3 or tail[0] != "candidates" \
            or tail[2] != "decisions":
        _not_found(send_json)
        return True
    try:
        require_p10_visual_review_v2_headers(handler.headers)
        candidate_address = require_sha256(
            tail[1], "Visual review v2 candidate",
        )
        payload = read_json_object_request(
            handler, maximum_bytes=MAX_VISUAL_REVIEW_DOCUMENT_BYTES,
        )
        if payload.get("candidate_sha256") != candidate_address:
            raise _InvalidSubmission
        context = resolve_p10_visual_review_v2_context(
            manager, store, parts[4],
        )
        result = BodySwayVisualReviewApplicationV2(store.state_root).submit(
            context.address, context.preview, payload,
        )
        value = submitted_response(result)
        value["job_id"] = context.job_id
        send_json(
            HTTPStatus.OK if result.reused else HTTPStatus.CREATED, value,
        )
    except P10VisualReviewV2HttpSecurityError as exc:
        drain_bounded_request_body(
            handler, maximum_bytes=MAX_VISUAL_REVIEW_DOCUMENT_BYTES,
        )
        send_json(HTTPStatus.FORBIDDEN, {
            "error": exc.code, "message": exc.public_message,
        })
    except HttpJsonRequestError as exc:
        send_json(exc.status, {
            "error": exc.code, "message": exc.public_message,
        })
    except P10VisualReviewV2JobNotFound:
        _not_found(send_json)
    except P10VisualReviewV2JobIncomplete:
        _job_incomplete(send_json)
    except P10VisualReviewV2SourceChanged:
        _source_changed(send_json)
    except LayerManifestError:
        _invalid_address(send_json)
    except BodySwayVisualReviewRevisionV2Conflict as exc:
        send_json(HTTPStatus.CONFLICT, {
            "error": "body_sway_visual_review_v2_revision_conflict",
            "message": "The review baseline is stale; reload exact history.",
            "requested_revision": exc.requested_revision,
            "current_revision": exc.current_revision,
            "requested_head_decision_sha256": exc.requested_head,
            "current_head_decision_sha256": exc.current_head,
        })
    except (_InvalidSubmission,
            BodySwayVisualReviewApplicationV2InvalidSubmission):
        _invalid_submission(send_json)
    except BodySwayVisualReviewApplicationV2Error as exc:
        if isinstance(exc.__cause__, P10PreviewV2CommandError):
            _source_changed(send_json)
        elif isinstance(exc.__cause__, (
            BodySwayVisualReviewDecisionV2Error,
            BodySwayVisualReviewSubmissionError,
        )):
            _invalid_submission(send_json)
        else:
            _internal_error(send_json)
    return True


def send_p10_visual_review_v2_method_not_allowed(parts, handler) -> None:
    methods = p10_visual_review_v2_allow_methods(parts) or "OPTIONS"
    handler._send_bytes(
        HTTPStatus.METHOD_NOT_ALLOWED,
        b'{"error":"method_not_allowed","message":"Method not allowed."}',
        "application/json; charset=utf-8",
        extra_headers={"Allow": methods}, visual_review=True,
    )


def _get_shape(tail):
    return tail == ["candidate"] \
        or len(tail) == 3 and tail[0] == "candidates" \
            and tail[2] == "history" \
        or len(tail) == 5 and tail[0] == "candidates" \
            and tail[2] == "history" \
        or len(tail) == 6 and tail[0] == "candidates" \
            and tail[2] == "cases" and tail[4] == "image"


def _revision(value):
    if not value.isascii() or not value.isdecimal() \
            or value.startswith("0") \
            or len(value) > len(str(MAX_VISUAL_REVIEW_REVISIONS)):
        raise _NotFound
    revision = int(value)
    if not 1 <= revision <= MAX_VISUAL_REVIEW_REVISIONS:
        raise _NotFound
    return revision


class _NotFound(Exception):
    pass


class _InvalidSubmission(Exception):
    pass


__all__ = [
    "dispatch_p10_visual_review_v2_get",
    "dispatch_p10_visual_review_v2_put",
    "is_p10_visual_review_v2_path",
    "p10_visual_review_v2_allow_methods",
    "send_p10_visual_review_v2_method_not_allowed",
]
