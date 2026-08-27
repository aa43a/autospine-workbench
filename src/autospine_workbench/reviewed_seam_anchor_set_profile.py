"""Pinned P10.5c static reviewed-anchor compilation profile."""

from __future__ import annotations

from typing import Any

from .seam_anchor_candidate_profile import RELATIONSHIP_PROFILE
from .seam_anchor_review_profile import MAX_SEAM_ANCHOR_REVIEW_REVISIONS


FORMAT = "autospine-reviewed-seam-anchor-set"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_JSON_NODES = 8192
MAX_JSON_DEPTH = 32
REQUIRED_DECISION_STATUS = "reviewed_anchor_set_ready_for_compile"
RELATIONSHIP_IDS = tuple(row[0] for row in RELATIONSHIP_PROFILE)
SOURCE_FIELDS = (
    "layer_manifest_sha256",
    "p3_rig_sha256",
    "p3_bundle_sha256",
    "seam_anchor_candidate_sha256",
    "review_revision",
    "seam_anchor_review_decision_sha256",
)


def reviewed_seam_anchor_set_compiler_profile() -> dict[str, Any]:
    """Return the JSON profile whose changes alter artifact identity."""

    return {
        "compiler": "autospine-reviewed-seam-anchor-set-compiler",
        "compiler_version": 1,
        "candidate_format": "autospine-seam-anchor-candidates@1",
        "decision_format": "autospine-seam-anchor-review-decision@1",
        "required_decision_status": REQUIRED_DECISION_STATUS,
        "max_review_revision": MAX_SEAM_ANCHOR_REVIEW_REVISIONS,
        "allowed_decision_actions": ["accept", "adjust"],
        "relationship_ids": list(RELATIONSHIP_IDS),
        "projection": "materialized-decision-anchor-pairs-only",
        "candidate_reselection": "forbidden",
        "fallback_locator": "forbidden",
    }


SEMANTICS = {
    "scope": "reviewed-static-seam-anchor-set",
    "coordinate_space": "setup-attachment-local",
    "anchor_direction": "parent-to-child",
    "motion_or_clip_input_admitted": False,
    "candidate_reselection_allowed": False,
    "fallback_locator_allowed": False,
}

CLAIMS = {
    "exact_candidate_and_decision_bound": True,
    "human_static_locator_selection_recorded": True,
    "reviewed_seam_anchor_set": True,
    "dynamic_seam_safety": False,
    "visual_seam_quality": False,
    "runtime_equivalence": False,
    "publishable_timeline": False,
    "release_authority": False,
}

RELEASE_GATE = {
    "status": "blocked",
    "reason_codes": [
        "dynamic_seam_safety_unproven",
        "runtime_equivalence_unproven",
        "visual_seam_quality_unproven",
    ],
}
