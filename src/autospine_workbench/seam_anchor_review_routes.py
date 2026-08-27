"""Exact, path-free HTTP adapter for P10.5b seam-anchor review."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from .manifest_artifacts import LayerManifestError, require_sha256
from .project_store import ProjectNotFoundError, ProjectStore, ProjectStoreError
from .seam_anchor_review_address import (
    ExactSeamAnchorReviewAddressError,
)
from .seam_anchor_review_application import (
    SeamAnchorReviewApplication,
    SeamAnchorReviewApplicationError,
    SeamAnchorReviewApplicationNotFound,
)
from .seam_anchor_review_errors import SeamAnchorReviewRevisionConflict
from .seam_anchor_review_evidence import (
    SeamAnchorReviewEvidenceError,
    SeamAnchorReviewEvidenceNotFound,
    SeamAnchorReviewEvidenceRepository,
)
from .seam_anchor_review_http_models import (
    candidate_response,
    exact_decision_response,
    history_response,
    submitted_response,
)
from .seam_anchor_review_http_security import (
    SeamAnchorReviewHttpSecurityError,
    require_seam_anchor_review_mutation_headers,
)
from .seam_anchor_review_profile import MAX_SEAM_ANCHOR_REVIEW_DOCUMENT_BYTES
from .seam_anchor_review_replay_cache import SeamAnchorReviewReplayCache
from .seam_anchor_review_route_support import (
    SeamAnchorReviewRouteInvalidSubmission,
    SeamAnchorReviewRouteNotFound,
    exact_address,
    exact_revision,
    send_internal_error,
    send_invalid_address,
    send_invalid_submission,
    send_not_found,
    submission_is_invalid,
)
from .http_json_request import HttpJsonRequestError, read_json_object_request


SendJson = Callable[[int, Any], None]
SendBytes = Callable[[int, bytes, str, dict[str, str] | None], None]
_PREFIX = ("api", "projects")
_SEGMENT = "seam-anchor-reviews"


def is_seam_anchor_review_path(parts: list[str]) -> bool:
    """Return whether decoded path parts enter this exact route family."""

    return len(parts) >= 7 \
        and tuple(parts[:2]) == _PREFIX \
        and parts[3] == _SEGMENT


def seam_anchor_review_allow_methods(parts: list[str]) -> str:
    """Expose only methods supported by the addressed resource."""

    return seam_anchor_review_resource_methods(parts) \
        or "GET, HEAD, OPTIONS"


def seam_anchor_review_resource_methods(parts: list[str]) -> str | None:
    """Return methods only for a syntactically known review resource."""

    if not is_seam_anchor_review_path(parts):
        return None
    tail = parts[7:]
    if _is_decision_collection(tail):
        return "POST, OPTIONS"
    if _is_read_resource(tail):
        return "GET, HEAD, OPTIONS"
    return None


def _is_decision_collection(tail: list[str]) -> bool:
    return len(tail) == 3 and tail[0] == "candidates" \
        and tail[2] == "decisions"


def _is_read_resource(tail: list[str]) -> bool:
    return tail == ["candidate"] \
        or len(tail) in {3, 5} and tail[0] == "candidates" \
        and tail[2] == "history" \
        or len(tail) == 8 and tail[0] == "candidates" \
        and tail[2] == "options" and tail[4] == "attachments" \
        and tail[6] == "images"


def dispatch_seam_anchor_review_get(
    parts: list[str],
    store: ProjectStore,
    send_json: SendJson,
    send_bytes: SendBytes,
    replay_cache: SeamAnchorReviewReplayCache | None = None,
) -> bool:
    """Serve exact candidates, evidence, history, or one decision."""

    if not is_seam_anchor_review_path(parts):
        return False
    if _is_decision_collection(parts[7:]):
        return False
    try:
        address = exact_address(parts)
        store.get_project(address.project_id)
        service = SeamAnchorReviewApplication(
            store.state_root, replay_cache=replay_cache
        )
        evidence = SeamAnchorReviewEvidenceRepository(
            store.state_root, replay_cache=replay_cache
        )
        tail = parts[7:]
        if tail == ["candidate"]:
            prepared = service.prepare(address)
            refs = evidence.attachment_refs(address, prepared)
            send_json(HTTPStatus.OK, candidate_response(prepared, refs))
            return True
        if len(tail) == 8 and tail[0] == "candidates" \
                and tail[2] == "options" and tail[4] == "attachments" \
                and tail[6] == "images":
            candidate_address = require_sha256(
                tail[1], "Seam-review candidate digest"
            )
            image_address = require_sha256(
                tail[7], "Seam-review attachment image digest"
            )
            prepared = service.prepare(address)
            image = evidence.image(
                address, prepared, candidate_sha256=candidate_address,
                option_id=tail[3], attachment_id=tail[5],
                image_sha256=image_address,
            )
            send_bytes(
                HTTPStatus.OK, image.png_bytes, "image/png",
                {"ETag": f'"{image.image_sha256}"'},
            )
            return True
        if len(tail) == 3 and tail[0] == "candidates" \
                and tail[2] == "history":
            candidate_address = require_sha256(
                tail[1], "Seam-review candidate digest"
            )
            prepared = service.prepare(address)
            if prepared.candidate_sha256 != candidate_address:
                raise SeamAnchorReviewRouteNotFound
            send_json(HTTPStatus.OK, history_response(prepared))
            return True
        if len(tail) == 5 and tail[0] == "candidates" \
                and tail[2] == "history":
            candidate_address = require_sha256(
                tail[1], "Seam-review candidate digest"
            )
            decision_address = require_sha256(
                tail[4], "Seam-review decision digest"
            )
            exact = service.exact_decision(
                address, candidate_sha256=candidate_address,
                revision=exact_revision(tail[3]),
                decision_sha256=decision_address,
            )
            send_json(HTTPStatus.OK, exact_decision_response(exact))
            return True
        raise SeamAnchorReviewRouteNotFound
    except (SeamAnchorReviewRouteNotFound,
            SeamAnchorReviewApplicationNotFound,
            SeamAnchorReviewEvidenceNotFound):
        send_not_found(send_json)
    except (ExactSeamAnchorReviewAddressError, LayerManifestError):
        send_invalid_address(send_json)
    except ProjectNotFoundError:
        send_not_found(send_json)
    except (SeamAnchorReviewApplicationError,
            SeamAnchorReviewEvidenceError, ProjectStoreError):
        send_internal_error(send_json)
    return True


def dispatch_seam_anchor_review_post(
    parts: list[str],
    store: ProjectStore,
    handler: Any,
    send_json: SendJson,
    replay_cache: SeamAnchorReviewReplayCache | None = None,
) -> bool:
    """CAS one exhaustive human decision after same-origin validation."""

    if not is_seam_anchor_review_path(parts):
        return False
    tail = parts[7:]
    if not _is_decision_collection(tail):
        if _is_read_resource(tail):
            return False
        send_not_found(send_json)
        return True
    try:
        require_seam_anchor_review_mutation_headers(handler.headers)
        address = exact_address(parts)
        store.get_project(address.project_id)
        candidate_address = require_sha256(
            tail[1], "Seam-review candidate digest"
        )
        payload = read_json_object_request(
            handler,
            maximum_bytes=MAX_SEAM_ANCHOR_REVIEW_DOCUMENT_BYTES,
        )
        if payload.get("candidate_sha256") != candidate_address:
            raise SeamAnchorReviewRouteInvalidSubmission
        result = SeamAnchorReviewApplication(
            store.state_root, replay_cache=replay_cache
        ).submit(address, payload)
        send_json(
            HTTPStatus.OK if result.reused else HTTPStatus.CREATED,
            submitted_response(result),
        )
    except SeamAnchorReviewHttpSecurityError as exc:
        send_json(HTTPStatus.FORBIDDEN, {
            "error": exc.code, "message": exc.public_message,
        })
    except HttpJsonRequestError as exc:
        send_json(exc.status, {
            "error": exc.code, "message": exc.public_message,
        })
    except (ExactSeamAnchorReviewAddressError, LayerManifestError):
        send_invalid_address(send_json)
    except ProjectNotFoundError:
        send_not_found(send_json)
    except SeamAnchorReviewRevisionConflict as exc:
        send_json(HTTPStatus.CONFLICT, {
            "error": "seam_anchor_review_revision_conflict",
            "message": "Seam review revision is stale; reload exact history.",
            "requested_revision": exc.requested_revision,
            "current_revision": exc.current_revision,
            "requested_head_decision_sha256": exc.requested_head,
            "current_head_decision_sha256": exc.current_head,
        })
    except SeamAnchorReviewApplicationError as exc:
        if submission_is_invalid(exc):
            send_invalid_submission(send_json)
        else:
            send_internal_error(send_json)
    except SeamAnchorReviewRouteInvalidSubmission:
        send_invalid_submission(send_json)
    except ProjectStoreError:
        send_internal_error(send_json)
    return True
