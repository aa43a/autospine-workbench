"""Small consistency helpers for the P10.3c application boundary."""

from __future__ import annotations

from .body_sway_visual_review_application_models import (
    SubmittedBodySwayVisualReview,
)
from .body_sway_visual_review_history import (
    BodySwayVisualReviewRevisionConflict,
)
from .body_sway_visual_review_history_snapshot import (
    BodySwayVisualReviewHistorySnapshot,
)
from .body_sway_visual_review_profile import MAX_VISUAL_REVIEW_REVISIONS


def require_consistent_visual_review_history(candidate, history) -> None:
    """Reject a malformed public history value before using it for CAS."""

    if type(history) is not BodySwayVisualReviewHistorySnapshot \
            or history.project_id != candidate.document["project_id"] \
            or history.candidate_sha256 != candidate.sha256 \
            or history.revision_count != len(history.rows) \
            or history.current_revision != history.revision_count \
            or history.current_revision > MAX_VISUAL_REVIEW_REVISIONS \
            or history.head_decision_sha256 != (
                history.rows[-1].decision_sha256 if history.rows else None
            ):
        raise ValueError("Visual review history snapshot is inconsistent")


def require_visual_review_compare_and_swap(
    submission, decision_sha256: str, history,
) -> None:
    """Accept the exact base or its sole immediate byte-identical retry."""

    exact = submission.base_revision == history.current_revision \
        and submission.previous_decision_sha256 == history.head_decision_sha256
    immediate_retry = history.current_revision == submission.base_revision + 1 \
        and history.head_decision_sha256 == decision_sha256
    if not exact and not immediate_retry:
        raise visual_review_revision_conflict(submission, history)


def visual_review_revision_conflict(submission, history):
    """Build one bounded structured conflict without filesystem details."""

    return BodySwayVisualReviewRevisionConflict(
        "Visual review base revision is stale",
        requested_revision=submission.base_revision + 1,
        current_revision=history.current_revision,
        requested_head=submission.previous_decision_sha256,
        current_head=history.head_decision_sha256,
    )


def submitted_visual_review_result(
    address, candidate, document, digest: str, reused: bool,
) -> SubmittedBodySwayVisualReview:
    """Project an authoritative decision to a path-free public response."""

    summary, gate = document["summary"], document["release_gate"]
    return SubmittedBodySwayVisualReview(
        address, candidate.sha256, digest, document["review"]["revision"],
        document["status"], gate["status"], tuple(gate["reason_codes"]),
        summary["case_count"], summary["approve_count"],
        summary["reject_count"], summary["unobservable_count"], reused,
    )
