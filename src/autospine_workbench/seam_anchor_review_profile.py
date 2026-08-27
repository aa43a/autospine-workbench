"""Pinned P10.5b review semantics, limits, and storage namespaces."""

from __future__ import annotations


MAX_SEAM_ANCHOR_REVIEW_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_SEAM_ANCHOR_REVIEW_REVISIONS = 64
MAX_REVIEW_NOTES_LENGTH = 4096
MAX_RELATIONSHIP_NOTES_LENGTH = 2048
MAX_REVIEW_JSON_NODES = 8192
MAX_REVIEW_JSON_DEPTH = 32
CANDIDATE_NAMESPACE = "seam-anchor-review-candidates"
DECISION_NAMESPACE = "seam-anchor-review-decisions"

DECISION_SEMANTICS = {
    "scope": "reviewed-static-seam-anchor-selection",
    "candidate_only": False,
    "human_review_claimed": True,
    "reviewed_seam_anchor_set_claimed": False,
    "dynamic_seam_safety_claimed": False,
    "visual_seam_quality_claimed": False,
    "runtime_equivalence_claimed": False,
    "publishable": False,
    "release_authority": False,
    "exact_candidate_replay_required": True,
    "exact_p3_locator_validation_required": True,
}

_BASE_BLOCKERS = (
    "dynamic_seam_safety_unproven",
    "reviewed_seam_anchor_set_missing",
    "runtime_equivalence_unproven",
    "visual_seam_quality_unproven",
)


def seam_anchor_review_release_gate(status: str) -> dict[str, object]:
    """Keep release blocked regardless of static selection completion."""

    reasons = list(_BASE_BLOCKERS)
    if status == "reviewed_anchor_set_blocked":
        reasons.append("reviewed_seam_anchor_selection_blocked")
    return {"status": "blocked", "reason_codes": sorted(reasons)}
