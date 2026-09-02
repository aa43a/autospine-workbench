"""Read-only image acceleration helpers for the P10.3c v2 routes."""

from __future__ import annotations

from http import HTTPStatus
import re
from urllib.parse import urlsplit

from .p10_visual_review_v2_image_cache import (
    P10VisualReviewV2ImageCacheKey,
)
from .p10_visual_review_v2_image_session import (
    P10VisualReviewV2ImageSessionNotFound,
    P10VisualReviewV2ImageSessionStore,
)


_NO_SESSION = object()
_SESSION_QUERY = re.compile(r"session=([A-Za-z0-9_-]{43})")


def image_tail(tail: list[str]) -> bool:
    return len(tail) == 6 and tail[0] == "candidates" \
        and tail[2] == "cases" and tail[4] == "image"


def read_route_shape(tail: list[str]) -> bool:
    return tail in (["candidate"], ["admission"]) \
        or len(tail) == 3 and tail[0] == "candidates" \
            and tail[2] == "history" \
        or len(tail) == 5 and tail[0] == "candidates" \
            and tail[2] == "history" \
        or image_tail(tail)


def review_revision(value: str, maximum: int) -> int | None:
    if not value.isascii() or not value.isdecimal() \
            or value.startswith("0") or len(value) > len(str(maximum)):
        return None
    revision = int(value)
    return revision if 1 <= revision <= maximum else None


def leased_image_for_request(
    sessions: P10VisualReviewV2ImageSessionStore,
    request_target: str, job_id: str, tail: list[str],
):
    """Use a read-only snapshot lease without replaying mutable heads."""

    if not image_tail(tail):
        return None
    token = _session_token(request_target)
    if token is _NO_SESSION:
        return None
    image = sessions.image(
        token, job_id=job_id, candidate_sha256=tail[1],
        case_id=tail[3], png_sha256=tail[5],
    )
    if image is None:
        raise P10VisualReviewV2ImageSessionNotFound(
            "Visual review image session is unavailable"
        )
    return image


def open_image_session(sessions, context, service, candidate_sha256):
    key = P10VisualReviewV2ImageCacheKey(
        context.job_id, context.package_id,
        context.address, candidate_sha256,
    )
    session = sessions.open(
        key,
        loader=lambda: service.prepare_image_snapshot(
            context.address, context.preview,
            candidate_sha256=candidate_sha256,
        ),
    )
    return session.public_document()


def exact_image_for_request(sessions, context, service, tail):
    key = P10VisualReviewV2ImageCacheKey(
        context.job_id, context.package_id,
        context.address, tail[1],
    )
    return sessions.image_cache.image(
        key, case_id=tail[3], png_sha256=tail[5],
        loader=lambda: service.prepare_image_snapshot(
            context.address, context.preview,
            candidate_sha256=tail[1],
        ),
    )


def send_review_image(send_bytes, image) -> None:
    send_bytes(
        HTTPStatus.OK, image.png_bytes, "image/png",
        {"ETag": f'"{image.png_sha256}"'},
    )


def _session_token(target: str):
    try:
        query = urlsplit(target).query
        if not query:
            return _NO_SESSION
    except (TypeError, ValueError):
        raise P10VisualReviewV2ImageSessionNotFound(
            "Visual review image session query is invalid"
        )
    match = _SESSION_QUERY.fullmatch(query)
    if match is None:
        raise P10VisualReviewV2ImageSessionNotFound(
            "Visual review image session query is invalid"
        )
    return match.group(1)


__all__ = [
    "exact_image_for_request", "image_tail",
    "leased_image_for_request", "open_image_session", "read_route_shape",
    "review_revision", "send_review_image",
]
