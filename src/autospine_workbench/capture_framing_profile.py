"""Pinned P10.2b capture-framing semantics and resource limits."""

from __future__ import annotations

from typing import Any


FORMAT = "autospine-capture-framing-candidate"
FORMAT_VERSION = 1
DECISION_FORMAT = "autospine-capture-framing-decision"
SUBMISSION_FORMAT = "autospine-capture-framing-submission"
RECEIPT_FORMAT = "autospine-capture-framing-receipt"
INTENT = "capture-framing-human-review-v1"
DECISION_NAMESPACE = "capture-framing-decisions"
MAX_REVISIONS = 64
MAX_REQUEST_BYTES = 256 * 1024
NUMERIC_PRECISION_DECIMALS = 9
CAPTURE_MARGIN_PX = 32
CAPTURE_VIEWPORT = {
    "width": 640,
    "height": 640,
    "device_pixel_ratio": 1,
    "margin_px": {
        "left": CAPTURE_MARGIN_PX,
        "right": CAPTURE_MARGIN_PX,
        "top": CAPTURE_MARGIN_PX,
        "bottom": CAPTURE_MARGIN_PX,
    },
}
ENVELOPE_KINDS = ("setup", "base", "combined")
COORDINATE_TRANSFORM_ID = "rig-canvas-y-down-to-spine-world-y-up-v1"


def capture_framing_profile() -> dict[str, Any]:
    return {
        "id": "capture-framing-candidate-compiler",
        "version": "1.0.0",
        "config": {
            "sample_schedule": "exact-p10.2-probe-schedule",
            "geometry_source": "all-attachment-posed-vertices",
            "required_envelopes": list(ENVELOPE_KINDS),
            "union_policy": "setup-base-combined-full-envelope",
            "world_viewport_aspect": "capture-pixel-aspect",
            "capture_margin_px": CAPTURE_MARGIN_PX,
            "numeric_precision_decimals": NUMERIC_PRECISION_DECIMALS,
            "capture_viewport": dict(CAPTURE_VIEWPORT),
            "coordinate_transform_id": COORDINATE_TRANSFORM_ID,
        },
    }


CANDIDATE_SEMANTICS = {
    "scope": "sampled-capture-framing-candidate-only",
    "authority": "none",
    "setup_envelope_included": True,
    "base_envelope_included": True,
    "combined_envelope_included": True,
    "human_decision_emitted": False,
    "runtime_viewport_emitted": False,
    "runtime_equivalence_claimed": False,
    "visual_quality_claimed": False,
    "continuous_time_safety_claimed": False,
    "release_authority": False,
}

CANDIDATE_RELEASE_GATE = {
    "status": "blocked",
    "reason_codes": [
        "capture_framing_human_review_required",
        "continuous_time_safety_unproven",
        "manual_runtime_preview_required",
        "reviewed_seam_anchors_missing",
        "safe_range_unproven",
    ],
}

DECISION_SEMANTICS = {
    "scope": "sampled-capture-framing-human-decision",
    "human_review_claimed": True,
    "runtime_equivalence_claimed": False,
    "visual_quality_claimed": False,
    "continuous_time_safety_claimed": False,
    "release_authority": False,
}


def capture_framing_decision_release_gate(approved: bool) -> dict[str, Any]:
    reasons = [
        "continuous_time_safety_unproven",
        "manual_runtime_preview_required",
        "reviewed_seam_anchors_missing",
        "safe_range_unproven",
        "temporary_preview_v2_not_compiled",
    ]
    if not approved:
        reasons.append("capture_framing_not_approved")
    return {"status": "blocked", "reason_codes": sorted(reasons)}
