"""Pinned P10.4a v2 review-admission semantics and blockers."""

from __future__ import annotations

from typing import Any


COMPILER_ID = "body-sway-review-admission-v2-compiler"
COMPILER_VERSION = "1.0.0"
MAX_ADMISSION_DOCUMENT_BYTES = 2 * 1024 * 1024


def compiler_profile_v2() -> dict[str, Any]:
    return {
        "id": COMPILER_ID,
        "version": COMPILER_VERSION,
        "canonicalization": "canonical-json-utf8-sort-keys-no-nonfinite",
    }


def admission_claims_v2() -> dict[str, bool]:
    """State only what exact sampled official-runtime evidence proves."""

    return {
        "completed_sampled_execution_bound": True,
        "sampled_visual_approved": True,
        "official_runtime_execution_replayed": True,
        "head_observed_at_compile_time": True,
        "safe_range": False,
        "continuous_time": False,
        "reviewed_seam_anchors": False,
        "inter_attachment_seam_safety": False,
        "publishable_timeline": False,
        "release_authority": False,
    }


def admission_release_gate_v2() -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason_codes": [
            "continuous_time_safety_unproven",
            "preview_only_timeline",
            "reviewed_seam_anchors_missing",
            "safe_range_unproven",
        ],
    }


def body_sway_review_head_observation_v2(
    revision: int, head_decision_sha256: str,
) -> dict[str, Any]:
    return {
        "method": "double_snapshot",
        "scope": "compile_time",
        "revision": revision,
        "head_decision_sha256": head_decision_sha256,
        "source_address_observed_twice": True,
        "permanent_authority_claimed": False,
    }


__all__ = [
    "MAX_ADMISSION_DOCUMENT_BYTES", "admission_claims_v2",
    "admission_release_gate_v2", "body_sway_review_head_observation_v2",
    "compiler_profile_v2",
]
