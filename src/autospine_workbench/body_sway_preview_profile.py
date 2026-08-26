"""Pinned identities and resource ceilings for P10.3 temporary previews."""

from __future__ import annotations

from typing import Any


COMPILER_ID = "temporary-body-sway-spine42-preview-compiler"
COMPILER_VERSION = "1.0.0"
PREVIEW_ADAPTER_ID = "autospine-spine42-body-sway-preview-adapter"
PREVIEW_ADAPTER_VERSION = "1.0.0"
PROJECTION_DIGEST_DOMAIN = "autospine-body-sway-preview-projection/v1"
ROTATION_TIMELINE_DIGEST_DOMAIN = (
    "autospine-body-sway-preview-rotation-timeline/v1"
)
BASE_ANIMATION_DIGEST_DOMAIN = (
    "autospine-body-sway-preview-base-animation/v1"
)
SETUP_DIGEST_DOMAIN = "autospine-body-sway-preview-setup/v1"
ARTIFACT_SET_DIGEST_DOMAIN = (
    "autospine-temporary-body-sway-preview-artifact-set/v1"
)
CAPTURE_PLAN_DIGEST_DOMAIN = "autospine-body-sway-preview-capture-plan/v1"
BASE_ANIMATION_NAME = "p10.base"
COMBINED_ANIMATION_NAME = "p10.body-sway"
MAX_PREVIEW_SAMPLE_COUNT = 4096
MAX_ROTATION_TRACK_COUNT = 17
MAX_ROTATION_KEY_COUNT = 69_632
NUMERIC_PRECISION_DECIMALS = 9
PREVIEW_SEMANTICS = {
    "mode": "temporary-runtime-preview",
    "runtime_timeline_emitted": True,
    "runtime_timeline_scope": "ephemeral-preview-only",
    "motion_instance_v3_emitted": False,
    "version_neutral_motion_contract_emitted": False,
    "publishable": False,
    "release_authority": False,
    "safe_range_claimed": False,
    "continuous_time_safety_claimed": False,
    "visual_quality_claimed": False,
    "raster_truth_claimed": False,
    "inter_attachment_seam_safety_claimed": False,
    "official_runtime_execution_claimed": False,
    "human_review_claimed": False,
    "content_digests_are_compiler_seals": True,
    "standalone_upstream_authenticity_claimed": False,
    "detached_validation_scope": "structure-and-internal-consistency",
    "upstream_replay_requires_exact_inputs": True,
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


def body_sway_preview_compiler_profile() -> dict[str, Any]:
    """Return the sole detached projection/compiler profile."""

    return {
        "id": COMPILER_ID,
        "version": COMPILER_VERSION,
        "numeric_precision_decimals": NUMERIC_PRECISION_DECIMALS,
        "projection_digest_domain": PROJECTION_DIGEST_DOMAIN,
        "rotation_timeline_digest_domain": ROTATION_TIMELINE_DIGEST_DOMAIN,
        "base_animation_digest_domain": BASE_ANIMATION_DIGEST_DOMAIN,
        "setup_digest_domain": SETUP_DIGEST_DOMAIN,
        "artifact_set_digest_domain": ARTIFACT_SET_DIGEST_DOMAIN,
        "capture_plan_digest_domain": CAPTURE_PLAN_DIGEST_DOMAIN,
        "limits": {
            "max_preview_sample_count": MAX_PREVIEW_SAMPLE_COUNT,
            "max_rotation_track_count": MAX_ROTATION_TRACK_COUNT,
            "max_rotation_key_count": MAX_ROTATION_KEY_COUNT,
        },
    }


def body_sway_preview_adapter_profile() -> dict[str, Any]:
    """Return the exact temporary Spine adapter identity."""

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
    }


def body_sway_preview_runtime_target() -> dict[str, Any]:
    """Return the adapter profile plus the pinned official package integrity."""

    from .spine42_runtime_contract import RUNTIME_NPM_INTEGRITY

    value = body_sway_preview_adapter_profile()
    value["runtime"]["npm_integrity"] = RUNTIME_NPM_INTEGRITY
    return value
