"""Pinned P10.6a v2 setup-local consumer semantics and budgets."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_dynamic_seam_probe_validation_v2 import (
    MAX_DOCUMENT_BYTES as MAX_DYNAMIC_SEAM_PROBE_V2_BYTES,
    MAX_DOCUMENT_JSON_DEPTH as MAX_DYNAMIC_SEAM_PROBE_V2_JSON_DEPTH,
    MAX_DOCUMENT_JSON_NODES as MAX_DYNAMIC_SEAM_PROBE_V2_JSON_NODES,
)
from .motion_instance_v2_validation import (
    MAX_DOCUMENT_BYTES as MAX_MOTION_INSTANCE_V2_BYTES,
)
from .resolved_project import canonical_sha256


FORMAT = "autospine-body-sway-motion-consumer-admission"
FORMAT_VERSION = 2
CORE_FORMAT = "autospine-body-sway-motion-consumer-admission-core"
CORE_FORMAT_VERSION = 2
PROFILE_ID = "body-sway-motion-consumer-admission-v2"
PROFILE_VERSION = "2.0.0"
CANONICALIZATION = "canonical-json-utf8-sort-keys-no-nonfinite"
SOURCE_HASH_DOMAIN = "autospine-body-sway-motion-consumer-source/v2"
MOTION_DOMAIN_HASH_DOMAIN = "autospine-body-sway-motion-domain/v2"
BASE_CHANNELS_HASH_DOMAIN = "autospine-body-sway-base-channels/v2"
HEAD_OBSERVATIONS_HASH_DOMAIN = (
    "autospine-body-sway-motion-consumer-head-observations/v2"
)
MAX_SOURCE_OWN_BYTES = 256 * 1024
MAX_SOURCE_BYTES = MAX_DYNAMIC_SEAM_PROBE_V2_BYTES + MAX_SOURCE_OWN_BYTES
MAX_SOURCE_JSON_NODES = MAX_DYNAMIC_SEAM_PROBE_V2_JSON_NODES + 4096
MAX_SOURCE_JSON_DEPTH = MAX_DYNAMIC_SEAM_PROBE_V2_JSON_DEPTH + 8
MAX_CORE_OWN_BYTES = 4 * 1024 * 1024
MAX_ADMISSION_OWN_BYTES = 2 * 1024 * 1024
MAX_CORE_BYTES = (
    MAX_SOURCE_BYTES + MAX_MOTION_INSTANCE_V2_BYTES + MAX_CORE_OWN_BYTES
)
MAX_DOCUMENT_BYTES = MAX_CORE_BYTES + MAX_ADMISSION_OWN_BYTES
MAX_DOCUMENT_JSON_NODES = MAX_SOURCE_JSON_NODES + 1_000_000
MAX_DOCUMENT_JSON_DEPTH = MAX_SOURCE_JSON_DEPTH + 16

SELECTED_GAIN = {"numerator": 1, "denominator": 1}
PROFILE_CONFIG = {
    "consumer_contract": "version-neutral-setup-local-timeline",
    "selected_gain": SELECTED_GAIN,
    "rotation_interpolation": "sampled-linear",
    "root_translation": "exact-motion-instance-v2-linear",
    "markers": "exact-motion-instance-v2",
    "draw_order": "exact-motion-instance-v2-stepped",
    "source_gate": "exact-p10.5d-v2-bundle-plus-exact-p9-bundle",
    "head_check": "before-and-after-exact-current-v2-head-observation",
    "downstream_motion_instance_payload": "setup-local-v3-compatible",
    "exclusions": [
        "attachment-area-overlap",
        "dynamic-seam-safety",
        "full-attachment-boundary-continuity",
        "raster-or-visual-quality",
        "runtime-equivalence",
        "motion-instance-v3-emission",
        "spine-adapter-emission",
        "release-authority",
    ],
}
CLAIMS = {
    "exact_source_closure": True,
    "current_review_heads_at_compile_time": True,
    "continuous_preview_v2_structural_certified": True,
    "reviewed_anchor_residual_proxy_certified": True,
    "setup_local_timeline_compilation_admitted": True,
    "attachment_area_overlap_assessed": False,
    "dynamic_seam_safety": False,
    "full_attachment_boundary_continuity": False,
    "raster_visual_quality": False,
    "runtime_equivalence": False,
    "motion_instance_v3_emitted": False,
    "spine_adapter_emitted": False,
    "publishable_timeline": False,
    "release_authority": False,
}
RELEASE_GATE = {
    "status": "blocked",
    "reason_codes": [
        "attachment_overlap_not_modeled",
        "dynamic_seam_safety_unproven",
        "full_attachment_boundary_raster_visual_regression_missing",
        "motion_instance_v3_not_emitted",
        "publishable_timeline_not_emitted",
        "runtime_equivalence_unproven",
        "spine_adapter_not_emitted",
    ],
}


def body_sway_motion_consumer_profile_v2() -> dict[str, Any]:
    return {
        "id": PROFILE_ID,
        "version": PROFILE_VERSION,
        "canonicalization": CANONICALIZATION,
        "config": _copy(PROFILE_CONFIG),
    }


def body_sway_motion_consumer_claims_v2() -> dict[str, bool]:
    return _copy(CLAIMS)


def body_sway_motion_consumer_release_gate_v2() -> dict[str, Any]:
    return _copy(RELEASE_GATE)


def body_sway_motion_consumer_source_sha256_v2(source: Mapping) -> str:
    return _seal(SOURCE_HASH_DOMAIN, "source", source, "source_set_sha256")


def body_sway_motion_domain_sha256_v2(domain: Mapping) -> str:
    return _seal(
        MOTION_DOMAIN_HASH_DOMAIN, "motion_domain", domain,
        "motion_domain_sha256",
    )


def body_sway_base_channels_sha256_v2(channels: Mapping) -> str:
    return _seal(
        BASE_CHANNELS_HASH_DOMAIN, "base_channels", channels,
        "base_channels_sha256",
    )


def body_sway_head_observations_sha256_v2(observations: Mapping) -> str:
    return _seal(
        HEAD_OBSERVATIONS_HASH_DOMAIN, "head_observations", observations,
        "head_observations_sha256",
    )


def _seal(domain, label, value, self_field):
    if type(value) is not dict:
        raise ValueError(f"Motion consumer v2 {label} must be an exact object")
    payload = {key: item for key, item in value.items() if key != self_field}
    return canonical_sha256({"domain": domain, label: payload})


def _copy(value):
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


__all__ = [
    "CORE_FORMAT", "CORE_FORMAT_VERSION", "FORMAT", "FORMAT_VERSION",
    "MAX_CORE_BYTES", "MAX_DOCUMENT_BYTES", "MAX_DOCUMENT_JSON_DEPTH",
    "MAX_DOCUMENT_JSON_NODES", "MAX_SOURCE_BYTES", "MAX_SOURCE_JSON_DEPTH",
    "MAX_SOURCE_JSON_NODES", "SELECTED_GAIN",
    "body_sway_base_channels_sha256_v2",
    "body_sway_head_observations_sha256_v2",
    "body_sway_motion_consumer_claims_v2",
    "body_sway_motion_consumer_profile_v2",
    "body_sway_motion_consumer_release_gate_v2",
    "body_sway_motion_consumer_source_sha256_v2",
    "body_sway_motion_domain_sha256_v2",
]
