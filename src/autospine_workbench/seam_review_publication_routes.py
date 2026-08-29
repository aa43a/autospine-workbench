"""Loopback HTTP adapter for package-bound P10.5c publication."""

from __future__ import annotations

from http import HTTPStatus
import json
from typing import Any, Callable

from .http_json_request import (
    HttpJsonRequestError,
    drain_bounded_request_body,
    read_json_object_request,
)
from .project_store import ProjectStore
from .seam_review_publication import (
    SeamReviewPublicationError,
    SeamReviewPublicationPackageNotFoundError,
    SeamReviewPublicationUnavailableError,
    publish_seam_review_package,
)
from .seam_review_publication_http_security import (
    SeamReviewPublicationHttpSecurityError,
    require_seam_review_publication_headers,
)


MAX_REQUEST_BYTES = 16 * 1024
ALLOW_METHODS = "POST, OPTIONS"
SendJson = Callable[[int, Any], None]


def is_seam_review_publication_path(parts: list[str]) -> bool:
    return len(parts) == 5 \
        and parts[:3] == ["api", "motion-policy", "review-packages"] \
        and parts[4] == "seam-publications"


def dispatch_seam_review_publication_post(
    parts: list[str], handler: Any, store: ProjectStore, send_json: SendJson,
) -> bool:
    if not is_seam_review_publication_path(parts):
        return False
    try:
        require_seam_review_publication_headers(handler.headers)
        request = read_json_object_request(
            handler, maximum_bytes=MAX_REQUEST_BYTES,
        )
        receipt = publish_seam_review_package(
            store.state_root, parts[3], request,
        )
        send_json(HTTPStatus.OK, receipt)
    except SeamReviewPublicationHttpSecurityError as exc:
        drain_bounded_request_body(handler, maximum_bytes=MAX_REQUEST_BYTES)
        send_json(HTTPStatus.FORBIDDEN, {
            "error": exc.code, "message": exc.public_message,
        })
    except HttpJsonRequestError as exc:
        send_json(exc.status, {
            "error": exc.code, "message": exc.public_message,
        })
    except SeamReviewPublicationPackageNotFoundError:
        send_json(HTTPStatus.NOT_FOUND, {
            "error": "motion_policy_package_not_found",
            "message": "The exact motion-policy package is unavailable.",
        })
    except SeamReviewPublicationError:
        send_json(HTTPStatus.BAD_REQUEST, {
            "error": "invalid_seam_review_publication_request",
            "message": "The reviewed seam publication request is invalid.",
        })
    except SeamReviewPublicationUnavailableError:
        send_json(HTTPStatus.CONFLICT, {
            "error": "seam_review_publication_unavailable",
            "message": "The current seam review could not be published.",
        })
    return True


def send_seam_review_publication_method_not_allowed(handler: Any) -> None:
    body = json.dumps({
        "error": "method_not_allowed", "message": "Method not allowed.",
    }, separators=(",", ":")).encode("utf-8")
    handler._send_bytes(  # noqa: SLF001 - route adapter uses handler primitive
        HTTPStatus.METHOD_NOT_ALLOWED, body,
        "application/json; charset=utf-8",
        extra_headers={"Allow": ALLOW_METHODS}, visual_review=True,
    )
