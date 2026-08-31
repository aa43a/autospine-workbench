"""Pinned identities for capture-framed P10.3 temporary previews v2."""

from __future__ import annotations

from typing import Any

from .body_sway_preview_profile import (
    BASE_ANIMATION_NAME,
    COMBINED_ANIMATION_NAME,
    MAX_PREVIEW_SAMPLE_COUNT,
    MAX_ROTATION_KEY_COUNT,
    MAX_ROTATION_TRACK_COUNT,
    NUMERIC_PRECISION_DECIMALS,
)


COMPILER_ID = "temporary-body-sway-spine42-preview-compiler-v2"
COMPILER_VERSION = "2.0.0"
PREVIEW_ADAPTER_ID = "autospine-spine42-body-sway-preview-adapter-v2"
PREVIEW_ADAPTER_VERSION = "2.0.0"
PROJECTION_DIGEST_DOMAIN = "autospine-body-sway-preview-projection/v2"
ROTATION_TIMELINE_DIGEST_DOMAIN = (
    "autospine-body-sway-preview-rotation-timeline/v2"
)
BASE_ANIMATION_DIGEST_DOMAIN = (
    "autospine-body-sway-preview-base-animation/v2"
)
SETUP_DIGEST_DOMAIN = "autospine-body-sway-preview-setup/v2"
SKELETON_HASH_DIGEST_DOMAIN = "autospine-body-sway-preview-skeleton/v2"
CAPTURE_PLAN_DIGEST_DOMAIN = "autospine-body-sway-preview-capture-plan/v2"
CAPTURE_VIEWPORT = {"width": 640, "height": 640}
CAPTURE_DEVICE_PIXEL_RATIO = 1

PREVIEW_SEMANTICS = {
    "mode": "capture-framed-temporary-runtime-preview-v2",
    "runtime_timeline_emitted": True,
    "runtime_timeline_scope": "ephemeral-preview-only",
    "motion_instance_v3_emitted": False,
    "version_neutral_motion_contract_emitted": False,
    "capture_framing_human_review_required": True,
    "capture_framing_changes_rig_geometry": False,
    "publishable": False,
    "release_authority": False,
    "safe_range_claimed": False,
    "continuous_time_safety_claimed": False,
    "visual_quality_claimed": False,
    "raster_truth_claimed": False,
    "inter_attachment_seam_safety_claimed": False,
    "official_runtime_execution_claimed": False,
    "human_visual_review_claimed": False,
    "content_digests_are_compiler_seals": True,
    "standalone_upstream_authenticity_claimed": False,
    "detached_validation_scope": "structure-and-internal-consistency",
    "detached_currentness_claimed": False,
    "upstream_replay_requires_exact_inputs_v2": True,
}

PREVIEW_RELEASE_GATE = {
    "status": "blocked",
    "reason_codes": sorted([
        "continuous_time_safety_unproven",
        "manual_visual_review_required",
        "official_runtime_capture_required",
        "preview_only_timeline",
        "reviewed_seam_anchors_missing",
        "safe_range_unproven",
    ]),
}


def body_sway_preview_compiler_profile_v2() -> dict[str, Any]:
    return {
        "id": COMPILER_ID,
        "version": COMPILER_VERSION,
        "numeric_precision_decimals": NUMERIC_PRECISION_DECIMALS,
        "projection_digest_domain": PROJECTION_DIGEST_DOMAIN,
        "rotation_timeline_digest_domain": ROTATION_TIMELINE_DIGEST_DOMAIN,
        "base_animation_digest_domain": BASE_ANIMATION_DIGEST_DOMAIN,
        "setup_digest_domain": SETUP_DIGEST_DOMAIN,
        "skeleton_hash_digest_domain": SKELETON_HASH_DIGEST_DOMAIN,
        "capture_plan_digest_domain": CAPTURE_PLAN_DIGEST_DOMAIN,
        "capture": {
            "viewport": dict(CAPTURE_VIEWPORT),
            "device_pixel_ratio": CAPTURE_DEVICE_PIXEL_RATIO,
        },
        "limits": {
            "max_preview_sample_count": MAX_PREVIEW_SAMPLE_COUNT,
            "max_rotation_track_count": MAX_ROTATION_TRACK_COUNT,
            "max_rotation_key_count": MAX_ROTATION_KEY_COUNT,
        },
    }


def body_sway_preview_adapter_profile_v2() -> dict[str, Any]:
    from .spine42_contract import (
        SPINE_JSON_VERSION,
        SPINE_MAJOR_MINOR,
        SPINE_RUNTIME_PACKAGE,
        SPINE_RUNTIME_VERSION,
    )

    return {
        "adapter": {
            "id": PREVIEW_ADAPTER_ID,
            "version": PREVIEW_ADAPTER_VERSION,
        },
        "skeleton_format": "json",
        "spine_major_minor": SPINE_MAJOR_MINOR,
        "skeleton_json_version": SPINE_JSON_VERSION,
        "runtime": {
            "package": SPINE_RUNTIME_PACKAGE,
            "version": SPINE_RUNTIME_VERSION,
        },
        "capture_framing": {
            "source": "current-human-reviewed-p10.2b-decision",
            "coordinate_space": "spine-world-bottom-left-y-up",
        },
    }


def body_sway_preview_runtime_target_v2() -> dict[str, Any]:
    from .spine42_runtime_contract import RUNTIME_NPM_INTEGRITY

    value = body_sway_preview_adapter_profile_v2()
    value["runtime"]["npm_integrity"] = RUNTIME_NPM_INTEGRITY
    return value


__all__ = [
    "BASE_ANIMATION_NAME", "COMBINED_ANIMATION_NAME",
    "PREVIEW_RELEASE_GATE", "PREVIEW_SEMANTICS",
    "body_sway_preview_adapter_profile_v2",
    "body_sway_preview_compiler_profile_v2",
    "body_sway_preview_runtime_target_v2",
]
