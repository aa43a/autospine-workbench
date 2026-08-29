"""Loopback GET routes for validated automatic P9 review packages."""

from __future__ import annotations

from http import HTTPStatus
import json
from typing import Any, Callable

from .motion_policy_review_packages import (
    MotionPolicyReviewPackageError,
    get_motion_policy_review_package,
    list_motion_policy_review_packages,
)
from .project_store import ProjectStore


SendJson = Callable[[int, Any], None]
ALLOW_METHODS = "GET, HEAD, OPTIONS"


def is_motion_policy_review_package_path(parts: list[str]) -> bool:
    return parts[:3] == ["api", "motion-policy", "review-packages"] and (
        len(parts) == 3 or len(parts) == 4
    )


def dispatch_motion_policy_review_package_get(
    parts: list[str], store: ProjectStore, send_json: SendJson,
) -> bool:
    if parts == ["api", "motion-policy", "review-packages"]:
        try:
            send_json(
                HTTPStatus.OK,
                list_motion_policy_review_packages(store.state_root),
            )
        except MotionPolicyReviewPackageError:
            send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                "error": "motion_policy_package_error",
                "message": "Automatic review packages could not be inspected.",
            })
        return True
    if len(parts) == 4 \
            and parts[:3] == ["api", "motion-policy", "review-packages"]:
        try:
            package = get_motion_policy_review_package(
                store.state_root, parts[3],
            )
        except MotionPolicyReviewPackageError:
            send_json(HTTPStatus.NOT_FOUND, {
                "error": "motion_policy_package_not_found",
                "message": "No validated automatic review package is available.",
            })
        else:
            send_json(HTTPStatus.OK, package)
        return True
    return False


def send_motion_policy_review_package_method_not_allowed(handler: Any) -> None:
    body = json.dumps({
        "error": "method_not_allowed", "message": "Method not allowed.",
    }, separators=(",", ":")).encode("utf-8")
    handler._send_bytes(  # noqa: SLF001 - route adapter uses handler primitive
        HTTPStatus.METHOD_NOT_ALLOWED, body,
        "application/json; charset=utf-8",
        extra_headers={"Allow": ALLOW_METHODS}, visual_review=True,
    )
