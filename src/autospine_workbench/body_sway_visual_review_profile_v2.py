"""Pinned P10.3c v2 review identities, claims, and digest domains."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .body_sway_visual_review_profile import (
    MAX_CASE_NOTES_LENGTH,
    MAX_REVIEW_NOTES_LENGTH,
    MAX_VISUAL_REVIEW_DOCUMENT_BYTES,
    MAX_VISUAL_REVIEW_REVISIONS,
)
from .resolved_project import canonical_sha256


GENERATOR_ID = "body-sway-visual-review-candidate-compiler-v2"
GENERATOR_VERSION = "2.0.0"
BROWSER_PROFILE_DIGEST_DOMAIN = "autospine-body-sway-browser-profile/v2"
CASE_EVIDENCE_DIGEST_DOMAIN = (
    "autospine-body-sway-visual-case-evidence/v2"
)
CANDIDATE_NAMESPACE = "body-sway-visual-review-candidates-v2"
DECISION_NAMESPACE = "body-sway-visual-review-decisions-v2"

CANDIDATE_GENERATOR = {
    "id": GENERATOR_ID,
    "version": GENERATOR_VERSION,
    "browser_profile_digest_domain": BROWSER_PROFILE_DIGEST_DOMAIN,
    "case_evidence_digest_domain": CASE_EVIDENCE_DIGEST_DOMAIN,
    "execution_source": "body-sway-runtime-execution-v1",
}
CANDIDATE_SEMANTICS = {
    "scope": "capture-framed-official-runtime-sampled-visual-review-v2",
    "candidate_only": True,
    "official_runtime_execution_evidence_bound": True,
    "current_preview_v2_replay_required": True,
    "current_framing_head_bound": True,
    "current_p10_1_head_bound": True,
    "human_review_claimed": False,
    "visual_quality_claimed": False,
    "safe_range_claimed": False,
    "continuous_time_safety_claimed": False,
    "inter_attachment_seam_safety_claimed": False,
    "publishable": False,
    "release_authority": False,
    "detached_validation_scope": "shape-and-internal-compiler-seals-only",
    "exact_source_replay_required": True,
}
DECISION_SEMANTICS = {
    **CANDIDATE_SEMANTICS,
    "candidate_only": False,
    "human_review_claimed": True,
    "sampled_visual_review_claimed": True,
}
_BASE_BLOCKERS = (
    "continuous_time_safety_unproven",
    "preview_only_timeline",
    "reviewed_seam_anchors_missing",
    "safe_range_unproven",
)
CANDIDATE_RELEASE_GATE = {
    "status": "blocked",
    "reason_codes": sorted((*_BASE_BLOCKERS, "manual_visual_review_required")),
}


def body_sway_browser_profile_sha256_v2(
    execution_document: Mapping[str, Any],
) -> str:
    return canonical_sha256({
        "domain": BROWSER_PROFILE_DIGEST_DOMAIN,
        "browser": execution_document["browser"],
        "runner": execution_document["runner"],
    })


def body_sway_case_evidence_sha256_v2(
    captured_case: Mapping[str, Any], artifact: Mapping[str, Any],
) -> str:
    return canonical_sha256({
        "domain": CASE_EVIDENCE_DIGEST_DOMAIN,
        "case": captured_case,
        "artifact": artifact,
    })


def body_sway_visual_review_release_gate_v2(status: str) -> dict[str, Any]:
    reasons = list(_BASE_BLOCKERS)
    if status == "sampled_visual_rejected":
        reasons.append("sampled_visual_review_rejected")
    return {"status": "blocked", "reason_codes": sorted(reasons)}


__all__ = [
    "CANDIDATE_GENERATOR", "CANDIDATE_NAMESPACE",
    "CANDIDATE_RELEASE_GATE", "CANDIDATE_SEMANTICS",
    "DECISION_NAMESPACE", "DECISION_SEMANTICS",
    "MAX_CASE_NOTES_LENGTH", "MAX_REVIEW_NOTES_LENGTH",
    "MAX_VISUAL_REVIEW_DOCUMENT_BYTES", "MAX_VISUAL_REVIEW_REVISIONS",
    "body_sway_browser_profile_sha256_v2",
    "body_sway_case_evidence_sha256_v2",
    "body_sway_visual_review_release_gate_v2",
]
