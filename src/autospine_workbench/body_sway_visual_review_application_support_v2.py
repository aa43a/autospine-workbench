"""CAS and consistency helpers for the P10.3c v2 application boundary."""

from __future__ import annotations

from .body_sway_visual_review_application_models_v2 import (
    SubmittedBodySwayVisualReviewV2,
)
from .body_sway_visual_review_errors_v2 import (
    BodySwayVisualReviewRevisionV2Conflict,
)
from .body_sway_visual_review_history_snapshot_v2 import (
    BodySwayVisualReviewHistorySnapshotV2,
)
from .body_sway_visual_review_profile_v2 import MAX_VISUAL_REVIEW_REVISIONS


def require_consistent_visual_review_history_v2(candidate, history) -> None:
    if type(history) is not BodySwayVisualReviewHistorySnapshotV2 \
            or history.project_id != candidate.document["project_id"] \
            or history.candidate_sha256 != candidate.sha256 \
            or history.revision_count != len(history.rows) \
            or history.current_revision != history.revision_count \
            or history.current_revision > MAX_VISUAL_REVIEW_REVISIONS \
            or history.head_decision_sha256 != (
                history.rows[-1].decision_sha256 if history.rows else None
            ):
        raise ValueError("Visual review v2 history snapshot is inconsistent")


def require_visual_review_compare_and_swap_v2(
    submission, decision_sha256, history,
) -> None:
    exact = submission.base_revision == history.current_revision \
        and submission.previous_decision_sha256 == history.head_decision_sha256
    retry = history.current_revision == submission.base_revision + 1 \
        and history.head_decision_sha256 == decision_sha256
    if not exact and not retry:
        raise visual_review_revision_conflict_v2(submission, history)


def visual_review_revision_conflict_v2(submission, history):
    return BodySwayVisualReviewRevisionV2Conflict(
        "Visual review v2 base revision is stale",
        requested_revision=submission.base_revision + 1,
        current_revision=history.current_revision,
        requested_head=submission.previous_decision_sha256,
        current_head=history.head_decision_sha256,
    )


def load_previous_visual_review_decision_v2(
    store, submission, candidate, execution, preview, history,
):
    """Load only the exact predecessor named by the submitted CAS base."""

    base, previous_sha = (
        submission.base_revision, submission.previous_decision_sha256,
    )
    if base == 0:
        return None
    if base > history.current_revision \
            or history.rows[base - 1].decision_sha256 != previous_sha:
        raise visual_review_revision_conflict_v2(submission, history)
    previous = store.load_decision(
        candidate.document["project_id"], candidate.sha256, previous_sha,
        candidates=candidate, execution=execution, preview=preview,
    )
    if previous.document["review"]["revision"] != base:
        raise visual_review_revision_conflict_v2(submission, history)
    return previous


def submitted_visual_review_result_v2(
    address, candidate, document, digest, reused,
) -> SubmittedBodySwayVisualReviewV2:
    summary, gate = document["summary"], document["release_gate"]
    return SubmittedBodySwayVisualReviewV2(
        address, candidate.sha256, digest, document["review"]["revision"],
        document["status"], gate["status"], tuple(gate["reason_codes"]),
        summary["case_count"], summary["approve_count"],
        summary["reject_count"], summary["unobservable_count"], reused,
    )
