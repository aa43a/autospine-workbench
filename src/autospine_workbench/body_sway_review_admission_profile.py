"""Pinned P10.4a review-admission semantics and release blockers."""

from __future__ import annotations

from typing import Any


COMPILER_ID = "body-sway-review-admission-compiler"
COMPILER_VERSION = "1.0.0"
MAX_ADMISSION_DOCUMENT_BYTES = 2 * 1024 * 1024

def compiler_profile() -> dict[str, Any]:
    """Return a fresh copy of the pinned compiler identity."""

    return {
        "id": COMPILER_ID,
        "version": COMPILER_VERSION,
        "canonicalization": "canonical-json-utf8-sort-keys-no-nonfinite",
    }


def admission_claims() -> dict[str, bool]:
    """Return fresh, non-escalating P10.4a claims."""

    return {
        "sampled_visual_approved": True,
        "head_observed_at_compile_time": True,
        "safe_range": False,
        "continuous_time": False,
        "reviewed_seam_anchors": False,
        "publishable_timeline": False,
        "release_authority": False,
    }


def admission_release_gate() -> dict[str, Any]:
    """Return a fresh blocked gate with every unresolved proof obligation."""

    return {
        "status": "blocked",
        "reason_codes": [
            "continuous_time_safety_unproven",
            "preview_only_timeline",
            "reviewed_seam_anchors_missing",
            "safe_range_unproven",
        ],
    }


def body_sway_review_head_observation(
    revision: int, head_decision_sha256: str,
) -> dict[str, Any]:
    """Describe the bounded fact established by two matching snapshots."""

    return {
        "method": "double_snapshot",
        "scope": "compile_time",
        "revision": revision,
        "head_decision_sha256": head_decision_sha256,
        "permanent_authority_claimed": False,
    }
