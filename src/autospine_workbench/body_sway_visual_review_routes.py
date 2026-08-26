"""Exact, path-free HTTP adapter for P10.3c visual review."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from .body_sway_runtime_capture_reader import (
    VerifiedBodySwayRuntimeCaptureNotFound,
)
from .body_sway_visual_review_address import (
    ExactVisualReviewAddress,
    ExactVisualReviewAddressError,
)
from .body_sway_visual_review_application import (
    BodySwayVisualReviewApplication,
    BodySwayVisualReviewApplicationError,
    BodySwayVisualReviewApplicationInvalidSubmission,
    BodySwayVisualReviewApplicationNotFound,
)
from .body_sway_visual_review_errors import (
    BodySwayVisualReviewRevisionConflict,
)
from .body_sway_visual_review_decision import BodySwayVisualReviewDecisionError
from .body_sway_visual_review_http_security import (
    BodySwayVisualReviewHttpSecurityError,
    require_visual_review_mutation_headers,
)
from .body_sway_visual_review_http_models import (
    candidate_response,
    exact_decision_response,
    history_response,
    submitted_response,
)
from .body_sway_visual_review_profile import MAX_VISUAL_REVIEW_REVISIONS
from .body_sway_visual_review_submission import (
    BodySwayVisualReviewSubmissionError,
)
from .http_json_request import HttpJsonRequestError, read_json_object_request
from .manifest_artifacts import LayerManifestError, require_sha256
from .project_store import ProjectNotFoundError, ProjectStore, ProjectStoreError


SendJson = Callable[[int, Any], None]
SendBytes = Callable[[int, bytes, str, dict[str, str] | None], None]
_PREFIX = ("api", "projects")
_CAPTURE_SEGMENT = "body-sway-runtime-captures"
_REVIEW_SEGMENT = "visual-review"


def is_body_sway_visual_review_path(parts: list[str]) -> bool:
    """Return whether decoded path parts enter the dedicated route family."""

    return len(parts) >= 8 \
        and tuple(parts[:2]) == _PREFIX \
        and parts[3] == _CAPTURE_SEGMENT \
        and parts[7] == _REVIEW_SEGMENT


def visual_review_allow_methods(parts: list[str]) -> str:
    """Expose only methods supported by the addressed review resource."""

    tail = parts[8:]
    if len(tail) == 3 and tail[0] == "candidates" \
            and tail[2] == "decisions":
        return "PUT, OPTIONS"
    return "GET, HEAD, OPTIONS"


def dispatch_body_sway_visual_review_get(
    parts: list[str],
    store: ProjectStore,
    send_json: SendJson,
    send_bytes: SendBytes,
) -> bool:
    """Serve one exact candidate, image, history, or decision resource."""

    if not is_body_sway_visual_review_path(parts):
        return False
    try:
        address = _address(parts)
        store.get_project(address.project_id)
        service = BodySwayVisualReviewApplication(store.state_root)
        tail = parts[8:]
        if tail == ["candidate"]:
            prepared = service.prepare(address)
            send_json(HTTPStatus.OK, candidate_response(prepared))
            return True
        if len(tail) == 6 and tail[0] == "candidates" \
                and tail[2] == "cases" and tail[4] == "image":
            image = service.image_evidence(
                address, candidate_sha256=tail[1], case_id=tail[3],
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
                tail[1], "Visual review candidate digest"
            )
            prepared = service.prepare(address)
            if prepared.candidate_sha256 != candidate_address:
                raise _VisualReviewNotFound
            send_json(HTTPStatus.OK, history_response(prepared))
            return True
        if len(tail) == 5 and tail[0] == "candidates" \
                and tail[2] == "history":
            revision = _revision(tail[3])
            exact = service.exact_decision(
                address, candidate_sha256=tail[1], revision=revision,
                decision_sha256=tail[4],
            )
            send_json(HTTPStatus.OK, exact_decision_response(exact))
            return True
        raise _VisualReviewNotFound
    except _VisualReviewNotFound:
        _not_found(send_json)
    except ExactVisualReviewAddressError:
        send_json(HTTPStatus.BAD_REQUEST, {
            "error": "invalid_visual_review_address",
            "message": "The visual review address is invalid.",
        })
    except LayerManifestError:
        send_json(HTTPStatus.BAD_REQUEST, {
            "error": "invalid_visual_review_address",
            "message": "The visual review address is invalid.",
        })
    except ProjectNotFoundError:
        _not_found(send_json)
    except BodySwayVisualReviewApplicationError as exc:
        if _application_not_found(exc):
            _not_found(send_json)
        elif isinstance(exc.__cause__, LayerManifestError):
            send_json(HTTPStatus.BAD_REQUEST, {
                "error": "invalid_visual_review_address",
                "message": "The visual review address is invalid.",
            })
        else:
            _internal_error(send_json)
    except ProjectStoreError:
        _internal_error(send_json)
    return True


def dispatch_body_sway_visual_review_put(
    parts: list[str],
    store: ProjectStore,
    handler: Any,
    send_json: SendJson,
) -> bool:
    """CAS one exact human decision after strict same-origin validation."""

    if not is_body_sway_visual_review_path(parts):
        return False
    tail = parts[8:]
    if len(tail) != 3 or tail[0] != "candidates" \
            or tail[2] != "decisions":
        _not_found(send_json)
        return True
    try:
        require_visual_review_mutation_headers(handler.headers)
        address = _address(parts)
        store.get_project(address.project_id)
        candidate_address = require_sha256(
            tail[1], "Visual review candidate digest"
        )
        payload = read_json_object_request(handler)
        if payload.get("candidate_sha256") != candidate_address:
            raise _VisualReviewInvalidSubmission
        result = BodySwayVisualReviewApplication(store.state_root).submit(
            address, payload
        )
        send_json(
            HTTPStatus.OK if result.reused else HTTPStatus.CREATED,
            submitted_response(result),
        )
    except BodySwayVisualReviewHttpSecurityError as exc:
        send_json(HTTPStatus.FORBIDDEN, {
            "error": exc.code, "message": exc.public_message,
        })
    except HttpJsonRequestError as exc:
        send_json(exc.status, {
            "error": exc.code, "message": exc.public_message,
        })
    except ExactVisualReviewAddressError:
        send_json(HTTPStatus.BAD_REQUEST, {
            "error": "invalid_visual_review_address",
            "message": "The visual review address is invalid.",
        })
    except LayerManifestError:
        send_json(HTTPStatus.BAD_REQUEST, {
            "error": "invalid_visual_review_address",
            "message": "The visual review address is invalid.",
        })
    except ProjectNotFoundError:
        _not_found(send_json)
    except BodySwayVisualReviewRevisionConflict as exc:
        send_json(HTTPStatus.CONFLICT, {
            "error": "body_sway_visual_review_revision_conflict",
            "message": "Visual review revision is stale; reload exact history.",
            "requested_revision": exc.requested_revision,
            "current_revision": exc.current_revision,
            "requested_head_decision_sha256": exc.requested_head,
            "current_head_decision_sha256": exc.current_head,
        })
    except BodySwayVisualReviewApplicationError as exc:
        if _submission_is_invalid(exc):
            send_json(HTTPStatus.BAD_REQUEST, {
                "error": "invalid_visual_review_submission",
                "message": "The visual review submission is invalid.",
            })
        else:
            _internal_error(send_json)
    except _VisualReviewInvalidSubmission:
        send_json(HTTPStatus.BAD_REQUEST, {
            "error": "invalid_visual_review_submission",
            "message": "The visual review submission is invalid.",
        })
    except ProjectStoreError:
        _internal_error(send_json)
    return True


def _address(parts: list[str]) -> ExactVisualReviewAddress:
    return ExactVisualReviewAddress(parts[2], parts[4], parts[5], parts[6])


def _revision(value: str) -> int:
    if not value.isascii() or not value.isdecimal() or value.startswith("0") \
            or len(value) > len(str(MAX_VISUAL_REVIEW_REVISIONS)):
        raise _VisualReviewNotFound
    revision = int(value)
    if not 1 <= revision <= MAX_VISUAL_REVIEW_REVISIONS:
        raise _VisualReviewNotFound
    return revision


def _application_not_found(exc: BaseException) -> bool:
    return isinstance(exc, BodySwayVisualReviewApplicationNotFound) \
        or isinstance(exc.__cause__, VerifiedBodySwayRuntimeCaptureNotFound)


def _submission_is_invalid(exc: BaseException) -> bool:
    return isinstance(exc, BodySwayVisualReviewApplicationInvalidSubmission) \
        or isinstance(exc.__cause__, (
            BodySwayVisualReviewDecisionError,
            BodySwayVisualReviewSubmissionError,
        ))


def _not_found(send_json: SendJson) -> None:
    send_json(HTTPStatus.NOT_FOUND, {
        "error": "visual_review_not_found",
        "message": "The exact visual review resource was not found.",
    })


def _internal_error(send_json: SendJson) -> None:
    send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
        "error": "visual_review_error",
        "message": "The visual review request could not be completed safely.",
    })


class _VisualReviewNotFound(Exception):
    pass


class _VisualReviewInvalidSubmission(Exception):
    pass
