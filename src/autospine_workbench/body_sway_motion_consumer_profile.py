"""Pinned P10.6a motion-consumer admission semantics and budgets."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_continuous_proof_profile import (
    MAX_PREVIEW_PROJECTION_BYTES,
)
from .body_sway_dynamic_seam_validation import (
    MAX_DOCUMENT_BYTES as MAX_DYNAMIC_SEAM_PROBE_BYTES,
    MAX_DOCUMENT_JSON_DEPTH as MAX_DYNAMIC_SEAM_PROBE_JSON_DEPTH,
    MAX_DOCUMENT_JSON_NODES as MAX_DYNAMIC_SEAM_PROBE_JSON_NODES,
)
from .motion_instance_v2_validation import (
    MAX_DOCUMENT_BYTES as MAX_MOTION_INSTANCE_V2_BYTES,
)
from .resolved_project import canonical_sha256


FORMAT = "autospine-body-sway-motion-consumer-admission"
FORMAT_VERSION = 1
CORE_FORMAT = "autospine-body-sway-motion-consumer-admission-core"
CORE_FORMAT_VERSION = 1
PROFILE_ID = "body-sway-motion-consumer-admission"
PROFILE_VERSION = "1.0.0"
CANONICALIZATION = "canonical-json-utf8-sort-keys-no-nonfinite"
SOURCE_HASH_DOMAIN = "autospine-body-sway-motion-consumer-source/v1"
MOTION_DOMAIN_HASH_DOMAIN = "autospine-body-sway-motion-domain/v1"
BASE_CHANNELS_HASH_DOMAIN = "autospine-body-sway-base-channels/v1"
HEAD_OBSERVATIONS_HASH_DOMAIN = (
    "autospine-body-sway-motion-consumer-head-observations/v1"
)
MAX_SOURCE_OWN_BYTES = 256 * 1024
MAX_SOURCE_BYTES = MAX_DYNAMIC_SEAM_PROBE_BYTES + MAX_SOURCE_OWN_BYTES
MAX_SOURCE_JSON_NODES = MAX_DYNAMIC_SEAM_PROBE_JSON_NODES + 4096
MAX_SOURCE_JSON_DEPTH = MAX_DYNAMIC_SEAM_PROBE_JSON_DEPTH + 8
MAX_CORE_OWN_BYTES = 2 * 1024 * 1024
MAX_ADMISSION_OWN_BYTES = 2 * 1024 * 1024
MAX_CORE_BYTES = (
    MAX_SOURCE_BYTES + MAX_MOTION_INSTANCE_V2_BYTES
    + MAX_PREVIEW_PROJECTION_BYTES + MAX_CORE_OWN_BYTES
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
    "head_check": "before-and-after-exact-current-head-observation",
    "exclusions": [
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
    "continuous_preview_model_structural_certified": True,
    "reviewed_anchor_engineering_proximity_certified": True,
    "setup_local_timeline_compilation_admitted": True,
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
        "dynamic_seam_safety_unproven",
        "full_attachment_boundary_raster_visual_regression_missing",
        "motion_instance_v3_not_emitted",
        "publishable_timeline_not_emitted",
        "runtime_equivalence_unproven",
        "spine_adapter_not_emitted",
    ],
}


def body_sway_motion_consumer_profile() -> dict[str, Any]:
    """Return the immutable setup-local consumer profile."""

    return {
        "id": PROFILE_ID,
        "version": PROFILE_VERSION,
        "canonicalization": CANONICALIZATION,
        "config": _copy(PROFILE_CONFIG),
    }


def body_sway_motion_consumer_claims() -> dict[str, bool]:
    """Return only claims justified by exact closure and compile-time heads."""

    return _copy(CLAIMS)


def body_sway_motion_consumer_release_gate() -> dict[str, Any]:
    """Remain blocked until separate visual/runtime/export evidence exists."""

    return _copy(RELEASE_GATE)


def body_sway_motion_consumer_source_sha256(
    source: Mapping[str, Any],
) -> str:
    """Seal one source closure while excluding its self digest."""

    root = _object(source, "source")
    payload = {key: value for key, value in root.items()
               if key != "source_set_sha256"}
    return canonical_sha256({"domain": SOURCE_HASH_DOMAIN, "source": payload})


def body_sway_motion_domain_sha256(
    motion_domain: Mapping[str, Any],
) -> str:
    """Seal the admitted setup-local timeline domain."""

    root = _object(motion_domain, "motion domain")
    payload = {key: value for key, value in root.items()
               if key != "motion_domain_sha256"}
    return canonical_sha256({
        "domain": MOTION_DOMAIN_HASH_DOMAIN,
        "motion_domain": payload,
    })


def body_sway_base_channels_sha256(channels: Mapping[str, Any]) -> str:
    """Seal exact MIv2 channels inherited without body-sway substitution."""

    root = _object(channels, "base channels")
    payload = {key: value for key, value in root.items()
               if key != "base_channels_sha256"}
    return canonical_sha256({
        "domain": BASE_CHANNELS_HASH_DOMAIN,
        "base_channels": payload,
    })


def body_sway_head_observations_sha256(
    observations: Mapping[str, Any],
) -> str:
    """Seal both equal compile-time head observations."""

    root = _object(observations, "head observations")
    payload = {key: value for key, value in root.items()
               if key != "head_observations_sha256"}
    return canonical_sha256({
        "domain": HEAD_OBSERVATIONS_HASH_DOMAIN,
        "head_observations": payload,
    })


def _object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"Motion consumer {label} must be an exact JSON object")
    return value


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))
