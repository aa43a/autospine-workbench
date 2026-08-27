"""Small history/CAS helpers for the P10.5b application boundary."""

from __future__ import annotations

from .seam_anchor_review_application_models import SubmittedSeamAnchorReview
from .seam_anchor_review_errors import SeamAnchorReviewRevisionConflict
from .seam_anchor_review_history_models import SeamAnchorReviewHistorySnapshot
from .seam_anchor_review_profile import MAX_SEAM_ANCHOR_REVIEW_REVISIONS


def require_consistent_seam_anchor_review_history(candidate, history) -> None:
    if type(history) is not SeamAnchorReviewHistorySnapshot \
            or history.project_id != candidate.document["project_id"] \
            or history.candidate_sha256 != candidate.sha256 \
            or history.revision_count != len(history.rows) \
            or history.current_revision != history.revision_count \
            or history.current_revision > MAX_SEAM_ANCHOR_REVIEW_REVISIONS \
            or tuple(row.revision for row in history.rows) \
                != tuple(range(1, len(history.rows) + 1)) \
            or history.head_decision_sha256 != (
                history.rows[-1].decision_sha256 if history.rows else None
            ):
        raise ValueError("Seam-review history snapshot is inconsistent")


def require_seam_anchor_review_compare_and_swap(
    submission, decision_sha256: str, history,
) -> None:
    exact = submission.base_revision == history.current_revision \
        and submission.previous_decision_sha256 == history.head_decision_sha256
    retry = history.current_revision == submission.base_revision + 1 \
        and history.head_decision_sha256 == decision_sha256
    if not exact and not retry:
        raise seam_anchor_review_revision_conflict(submission, history)


def seam_anchor_review_revision_conflict(submission, history):
    return SeamAnchorReviewRevisionConflict(
        "Seam-review base revision is stale",
        requested_revision=submission.base_revision + 1,
        current_revision=history.current_revision,
        requested_head=submission.previous_decision_sha256,
        current_head=history.head_decision_sha256,
    )


def submitted_seam_anchor_review_result(
    address, candidate, document, digest: str, reused: bool,
) -> SubmittedSeamAnchorReview:
    summary, gate = document["summary"], document["release_gate"]
    return SubmittedSeamAnchorReview(
        address, candidate.sha256, digest, document["review"]["revision"],
        document["status"], gate["status"], tuple(gate["reason_codes"]),
        summary["relationship_count"], summary["accept_count"],
        summary["adjust_count"], summary["reject_count"],
        summary["unobservable_count"], summary["anchor_pair_count"], reused,
    )
