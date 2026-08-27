"""Small parsing and public-error helpers for seam-review HTTP routes."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from .seam_anchor_review_address import ExactSeamAnchorReviewAddress
from .seam_anchor_review_application import (
    SeamAnchorReviewApplicationInvalidSubmission,
)
from .seam_anchor_review_decision import SeamAnchorReviewDecisionError
from .seam_anchor_review_profile import MAX_SEAM_ANCHOR_REVIEW_REVISIONS
from .seam_anchor_review_submission import SeamAnchorReviewSubmissionError


SendJson = Callable[[int, Any], None]


class SeamAnchorReviewRouteNotFound(Exception):
    pass


class SeamAnchorReviewRouteInvalidSubmission(Exception):
    pass


def exact_address(parts: list[str]) -> ExactSeamAnchorReviewAddress:
    return ExactSeamAnchorReviewAddress(
        parts[2], parts[4], parts[5], parts[6]
    )


def exact_revision(value: str) -> int:
    if not value.isascii() or not value.isdecimal() \
            or value.startswith("0") \
            or len(value) > len(str(MAX_SEAM_ANCHOR_REVIEW_REVISIONS)):
        raise SeamAnchorReviewRouteNotFound
    revision = int(value)
    if not 1 <= revision <= MAX_SEAM_ANCHOR_REVIEW_REVISIONS:
        raise SeamAnchorReviewRouteNotFound
    return revision


def submission_is_invalid(exc: BaseException) -> bool:
    return isinstance(exc, SeamAnchorReviewApplicationInvalidSubmission) \
        or isinstance(exc.__cause__, (
            SeamAnchorReviewDecisionError,
            SeamAnchorReviewSubmissionError,
        ))


def send_invalid_address(send_json: SendJson) -> None:
    send_json(HTTPStatus.BAD_REQUEST, {
        "error": "invalid_seam_anchor_review_address",
        "message": "The seam-anchor review address is invalid.",
    })


def send_invalid_submission(send_json: SendJson) -> None:
    send_json(HTTPStatus.BAD_REQUEST, {
        "error": "invalid_seam_anchor_review_submission",
        "message": "The seam-anchor review submission is invalid.",
    })


def send_not_found(send_json: SendJson) -> None:
    send_json(HTTPStatus.NOT_FOUND, {
        "error": "seam_anchor_review_not_found",
        "message": "The exact seam-anchor review resource was not found.",
    })


def send_internal_error(send_json: SendJson) -> None:
    send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
        "error": "seam_anchor_review_error",
        "message": "The seam-anchor review request could not be completed safely.",
    })
