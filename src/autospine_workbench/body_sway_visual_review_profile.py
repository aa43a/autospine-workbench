"""Pinned P10.3c sampled visual-review semantics and digest domains."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .resolved_project import canonical_sha256


GENERATOR_ID = "body-sway-visual-review-candidate-compiler"
GENERATOR_VERSION = "1.0.0"
BROWSER_PROFILE_DIGEST_DOMAIN = "autospine-body-sway-browser-profile/v1"
CASE_EVIDENCE_DIGEST_DOMAIN = "autospine-body-sway-visual-case-evidence/v1"
MAX_VISUAL_REVIEW_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_REVIEW_NOTES_LENGTH = 4096
MAX_CASE_NOTES_LENGTH = 2048
MAX_VISUAL_REVIEW_REVISIONS = 64
CANDIDATE_NAMESPACE = "body-sway-visual-review-candidates"
DECISION_NAMESPACE = "body-sway-visual-review-decisions"

CANDIDATE_GENERATOR = {
    "id": GENERATOR_ID,
    "version": GENERATOR_VERSION,
    "browser_profile_digest_domain": BROWSER_PROFILE_DIGEST_DOMAIN,
    "case_evidence_digest_domain": CASE_EVIDENCE_DIGEST_DOMAIN,
}
CANDIDATE_SEMANTICS = {
    "scope": "sampled-official-runtime-still-visual-review",
    "candidate_only": True,
    "human_review_claimed": False,
    "visual_quality_claimed": False,
    "safe_range_claimed": False,
    "continuous_time_safety_claimed": False,
    "inter_attachment_seam_safety_claimed": False,
    "publishable": False,
    "release_authority": False,
    "detached_validation_scope": "shape-and-internal-compiler-seals-only",
    "content_digests_are_compiler_seals": True,
    "exact_source_replay_required": True,
}
DECISION_SEMANTICS = {
    "scope": "sampled-official-runtime-still-visual-review",
    "candidate_only": False,
    "human_review_claimed": True,
    "sampled_visual_review_claimed": True,
    "safe_range_claimed": False,
    "continuous_time_safety_claimed": False,
    "inter_attachment_seam_safety_claimed": False,
    "publishable": False,
    "release_authority": False,
    "detached_validation_scope": "shape-and-internal-compiler-seals-only",
    "content_digests_are_compiler_seals": True,
    "exact_source_replay_required": True,
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


def body_sway_browser_profile_sha256(
    capture_document: Mapping[str, Any],
) -> str:
    """Seal browser identity and its fixed runner profile in one domain."""

    return canonical_sha256({
        "domain": BROWSER_PROFILE_DIGEST_DOMAIN,
        "browser": capture_document["browser"],
        "runner": capture_document["runner"],
    })


def body_sway_case_evidence_sha256(
    captured_case: Mapping[str, Any], artifact: Mapping[str, Any],
) -> str:
    """Seal one capture-plan case and its exact detached PNG metadata."""

    return canonical_sha256({
        "domain": CASE_EVIDENCE_DIGEST_DOMAIN,
        "case": captured_case,
        "artifact": artifact,
    })


def body_sway_visual_review_release_gate(status: str) -> dict[str, Any]:
    """Keep release blocked after sampled approval or rejection."""

    reasons = list(_BASE_BLOCKERS)
    if status == "sampled_visual_rejected":
        reasons.append("sampled_visual_review_rejected")
    return {"status": "blocked", "reason_codes": sorted(reasons)}
