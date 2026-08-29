"""Loopback GET route for exact P9-to-seam review handoff."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from .motion_policy_seam_review_entry import (
    MotionPolicySeamReviewEntryError,
    MotionPolicySeamReviewEntryNotFoundError,
    build_motion_policy_seam_review_entry,
)
from .project_store import ProjectStore


SendJson = Callable[[int, Any], None]
ALLOW_METHODS = "GET, HEAD, OPTIONS"


def is_motion_policy_seam_review_entry_path(parts: list[str]) -> bool:
    return len(parts) == 5 \
        and parts[:3] == ["api", "motion-policy", "review-packages"] \
        and parts[4] == "seam-review-entry"


def dispatch_motion_policy_seam_review_entry_get(
    parts: list[str], store: ProjectStore, send_json: SendJson,
) -> bool:
    """Return one path-free, zero-write seam review entry."""

    if not is_motion_policy_seam_review_entry_path(parts):
        return False
    try:
        entry = build_motion_policy_seam_review_entry(
            store.state_root, parts[3],
        )
    except MotionPolicySeamReviewEntryNotFoundError:
        send_json(HTTPStatus.NOT_FOUND, {
            "error": "motion_policy_package_not_found",
            "message": "The exact motion-policy package is unavailable.",
        })
    except MotionPolicySeamReviewEntryError:
        send_json(HTTPStatus.CONFLICT, {
            "error": "motion_policy_seam_review_entry_unavailable",
            "message": "The exact seam-review entry could not be replayed.",
        })
    else:
        send_json(HTTPStatus.OK, entry)
    return True
