"""Pinned P10.4b2 continuous preview-model proof semantics."""

from __future__ import annotations

import json
from typing import Any

from .body_sway_continuous_interval import (
    DEFAULT_MAX_BOXES,
    DEFAULT_MAX_DEPTH,
    EXCLUSIONS as INTERVAL_EXCLUSIONS,
    SCOPE as INTERVAL_SCOPE,
)
from .body_sway_amplitude_envelope_profile import (
    MAX_ENVELOPE_DOCUMENT_BYTES,
)
from .body_sway_probe_profile import body_sway_probe_profile
from .motion_instance_v2_validation import (
    MAX_DOCUMENT_BYTES as MAX_MOTION_INSTANCE_V2_BYTES,
)
from .temporary_body_sway_preview_validation import (
    MAX_DOCUMENT_BYTES as MAX_TEMPORARY_PREVIEW_BYTES,
)
from .resolved_project import canonical_sha256


ANALYZER_ID = "body-sway-continuous-preview-proof-analyzer"
ANALYZER_VERSION = "1.0.0"
CANONICALIZATION = "canonical-json-utf8-sort-keys-no-nonfinite"
SOURCE_HASH_DOMAIN = "autospine-body-sway-continuous-source/v1"
PROBLEM_HASH_DOMAIN = "autospine-body-sway-continuous-problem/v1"
SEGMENT_HASH_DOMAIN = "autospine-body-sway-continuous-segment/v1"
TICK_PAIRS_HASH_DOMAIN = "autospine-body-sway-adjacent-tick-pairs/v1"
MAX_RIG_IR_BYTES = 64 * 1024 * 1024
MAX_TARGET_PROFILE_BYTES = 64 * 1024 * 1024
MAX_PREVIEW_PROJECTION_BYTES = 64 * 1024 * 1024
MAX_PROOF_OWN_BYTES = 16 * 1024 * 1024
MAX_DOCUMENT_BYTES = (
    MAX_ENVELOPE_DOCUMENT_BYTES + MAX_RIG_IR_BYTES
    + MAX_TARGET_PROFILE_BYTES + MAX_MOTION_INSTANCE_V2_BYTES
    + MAX_TEMPORARY_PREVIEW_BYTES + MAX_PREVIEW_PROJECTION_BYTES
    + MAX_PROOF_OWN_BYTES
)
MAX_TOTAL_BOXES = 32_768
GAIN_DOMAIN = {
    "kind": "coupled-four-bone-uniform-gain",
    "minimum": {"numerator": 0, "denominator": 1},
    "maximum": {"numerator": 1, "denominator": 1},
    "closure": "closed",
}
INTERPOLATION = {
    "rotation": "sampled-linear-between-adjacent-preview-sample-ticks",
    "root_translation": "sampled-linear-between-adjacent-preview-sample-ticks",
    "segment_coverage": "every-adjacent-preview-sample-tick-pair",
}
BACKEND = {
    "interval_arithmetic": (
        "binary64-directed-basic-ops-rational-trig-q9-q4096-v1"
    ),
    "trigonometry": "rational-taylor-enclosure-v1",
    "numeric_enclosure": "q9-per-layer-plus-q4096-half-step-v1",
    "method": "adaptive-interval-box-subdivision-no-point-sampling",
}
RELEASE_BLOCKERS = (
    "motion_instance_v3_not_emitted",
    "preview_model_only",
    "publishable_timeline_not_emitted",
    "reviewed_seam_anchors_missing",
    "runtime_equivalence_unproven",
    "visual_range_unreviewed",
)


def body_sway_continuous_proof_budget() -> dict[str, int]:
    return {
        "max_depth": DEFAULT_MAX_DEPTH,
        "max_boxes_per_segment": DEFAULT_MAX_BOXES,
        "max_total_boxes": MAX_TOTAL_BOXES,
    }


def body_sway_continuous_proof_analyzer_profile() -> dict[str, Any]:
    """Return the immutable proof backend and all fixed thresholds."""

    mesh = body_sway_probe_profile()["config"]["mesh_thresholds"]
    return {
        "id": ANALYZER_ID,
        "version": ANALYZER_VERSION,
        "canonicalization": CANONICALIZATION,
        "config": {
            "gain_domain": _copy(GAIN_DOMAIN),
            "interpolation": _copy(INTERPOLATION),
            "budget": body_sway_continuous_proof_budget(),
            "mesh_thresholds": _copy(mesh),
            "backend": _copy(BACKEND),
            "scope": list(INTERVAL_SCOPE),
            "exclusions": list(INTERVAL_EXCLUSIONS),
        },
    }


def body_sway_continuous_proof_claims(certified: bool) -> dict[str, bool]:
    """Expose only the one conclusion justified by all certified segments."""

    if type(certified) is not bool:
        raise ValueError("Continuous proof claim state must be boolean")
    return {
        "continuous_preview_model_structural_safety": certified,
        "uniform_gain_zero_to_reviewed_structurally_certified": certified,
        "runtime_equivalence": False,
        "visual_range": False,
        "reviewed_seam_anchors": False,
        "motion_instance_v3": False,
        "publishable_timeline": False,
        "release_authority": False,
    }


def body_sway_continuous_proof_problem(
    source_set_sha256: str, sample_ticks: list[int],
) -> dict[str, Any]:
    """Build and seal the sole full-preview proof problem."""

    if not isinstance(source_set_sha256, str) \
            or len(source_set_sha256) != 64 \
            or any(character not in "0123456789abcdef"
                   for character in source_set_sha256):
        raise ValueError("Continuous proof source identity is invalid")
    if not isinstance(sample_ticks, list) or len(sample_ticks) < 2 \
            or any(type(tick) is not int for tick in sample_ticks) \
            or any(left >= right for left, right in zip(
                sample_ticks, sample_ticks[1:]
            )):
        raise ValueError("Continuous proof sample ticks are invalid")
    pairs = [[left, right] for left, right in zip(
        sample_ticks, sample_ticks[1:]
    )]
    config = body_sway_continuous_proof_analyzer_profile()["config"]
    problem = {
        "source_set_sha256": source_set_sha256,
        "gain_domain": config["gain_domain"],
        "time_domain": {
            "sample_ticks": list(sample_ticks),
            "sample_count": len(sample_ticks),
            "segment_count": len(pairs),
            "adjacent_tick_pairs_sha256": canonical_sha256({
                "domain": TICK_PAIRS_HASH_DOMAIN,
                "pairs": pairs,
            }),
        },
        "interpolation": config["interpolation"],
        "budget": config["budget"],
        "mesh_thresholds": config["mesh_thresholds"],
        "backend": config["backend"],
        "scope": config["scope"],
        "exclusions": config["exclusions"],
    }
    problem["problem_sha256"] = body_sway_continuous_problem_sha256(problem)
    return problem


def body_sway_continuous_proof_release_gate(certified: bool) -> dict[str, Any]:
    if type(certified) is not bool:
        raise ValueError("Continuous proof release state must be boolean")
    reasons = list(RELEASE_BLOCKERS)
    if not certified:
        reasons.extend((
            "continuous_preview_model_safety_unproven",
            "unit_gain_interval_unproven",
        ))
    return {"status": "blocked", "reason_codes": sorted(reasons)}


def body_sway_continuous_source_sha256(source: dict[str, Any]) -> str:
    payload = {key: value for key, value in source.items()
               if key != "source_set_sha256"}
    return canonical_sha256({"domain": SOURCE_HASH_DOMAIN, "source": payload})


def body_sway_continuous_problem_sha256(problem: dict[str, Any]) -> str:
    payload = {key: value for key, value in problem.items()
               if key != "problem_sha256"}
    return canonical_sha256({"domain": PROBLEM_HASH_DOMAIN, "problem": payload})


def body_sway_continuous_segment_sha256(segment: dict[str, Any]) -> str:
    payload = {key: value for key, value in segment.items()
               if key != "segment_evidence_sha256"}
    return canonical_sha256({"domain": SEGMENT_HASH_DOMAIN, "segment": payload})


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))
