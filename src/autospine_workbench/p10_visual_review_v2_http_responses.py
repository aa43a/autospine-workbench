"""Sanitized public responses for the P10.3c v2 route family."""

from __future__ import annotations

from http import HTTPStatus


def not_found(send):
    send(HTTPStatus.NOT_FOUND, {
        "error": "visual_review_v2_not_found",
        "message": "The exact P10.3c v2 resource was not found.",
    })


def job_incomplete(send):
    send(HTTPStatus.CONFLICT, {
        "error": "runtime_capture_job_not_completed",
        "message": "Official Runtime capture must complete before review.",
    })


def source_changed(send):
    send(HTTPStatus.CONFLICT, {
        "error": "visual_review_v2_source_changed",
        "message": "Current P10.1 or capture framing changed; run a new capture.",
    })


def invalid_address(send):
    send(HTTPStatus.BAD_REQUEST, {
        "error": "invalid_visual_review_v2_address",
        "message": "The P10.3c v2 address is invalid.",
    })


def invalid_submission(send):
    send(HTTPStatus.BAD_REQUEST, {
        "error": "invalid_visual_review_v2_submission",
        "message": "The P10.3c v2 submission is invalid.",
    })


def internal_error(send):
    send(HTTPStatus.INTERNAL_SERVER_ERROR, {
        "error": "visual_review_v2_error",
        "message": "The P10.3c v2 request could not be completed safely.",
    })


__all__ = [
    "internal_error", "invalid_address", "invalid_submission",
    "job_incomplete", "not_found", "source_changed",
]
