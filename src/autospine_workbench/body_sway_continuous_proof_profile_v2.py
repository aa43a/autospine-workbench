"""Pinned P10.4b2 v2 continuous preview-model proof semantics."""

from __future__ import annotations

import json
from typing import Any

from .body_sway_continuous_interval import (
    DEFAULT_MAX_BOXES, DEFAULT_MAX_DEPTH, EXCLUSIONS as INTERVAL_EXCLUSIONS,
    SCOPE as INTERVAL_SCOPE,
)
from .body_sway_probe_profile import body_sway_probe_profile
from .resolved_project import canonical_sha256


ANALYZER_ID = "body-sway-continuous-preview-proof-analyzer-v2"
ANALYZER_VERSION = "2.0.0"
SOURCE_HASH_DOMAIN = "autospine-body-sway-continuous-source/v2"
PROBLEM_HASH_DOMAIN = "autospine-body-sway-continuous-problem/v2"
SEGMENT_HASH_DOMAIN = "autospine-body-sway-continuous-segment/v2"
TICK_PAIRS_HASH_DOMAIN = "autospine-body-sway-adjacent-tick-pairs/v2"
MAX_DOCUMENT_BYTES = 160 * 1024 * 1024
MAX_TOTAL_BOXES = 32_768
GAIN_DOMAIN = {
    "kind": "coupled-four-bone-uniform-gain",
    "minimum": {"numerator": 0, "denominator": 1},
    "maximum": {"numerator": 1, "denominator": 1},
    "closure": "closed",
}
INTERPOLATION = {
    "rotation": "sampled-linear-between-adjacent-preview-v2-ticks",
    "root_translation": "sampled-linear-between-adjacent-preview-v2-ticks",
    "segment_coverage": "every-adjacent-preview-v2-tick-pair",
}
BACKEND = {
    "interval_arithmetic":
        "binary64-directed-basic-ops-rational-trig-q9-q4096-v1",
    "trigonometry": "rational-taylor-enclosure-v1",
    "numeric_enclosure": "q9-per-layer-plus-q4096-half-step-v1",
    "method": "adaptive-interval-box-subdivision-no-point-sampling",
}
RELEASE_BLOCKERS = (
    "motion_instance_v3_not_emitted",
    "preview_model_only",
    "publishable_timeline_not_emitted",
    "reviewed_seam_anchors_missing",
    "runtime_continuous_equivalence_unproven",
    "visual_gain_range_unreviewed",
)


def continuous_proof_budget_v2() -> dict[str, int]:
    return {
        "max_depth": DEFAULT_MAX_DEPTH,
        "max_boxes_per_segment": DEFAULT_MAX_BOXES,
        "max_total_boxes": MAX_TOTAL_BOXES,
    }


def continuous_analyzer_profile_v2() -> dict[str, Any]:
    mesh = body_sway_probe_profile()["config"]["mesh_thresholds"]
    return {
        "id": ANALYZER_ID, "version": ANALYZER_VERSION,
        "canonicalization": "canonical-json-utf8-sort-keys-no-nonfinite",
        "config": {
            "gain_domain": _copy(GAIN_DOMAIN),
            "interpolation": _copy(INTERPOLATION),
            "budget": continuous_proof_budget_v2(),
            "mesh_thresholds": _copy(mesh), "backend": _copy(BACKEND),
            "scope": list(INTERVAL_SCOPE),
            "exclusions": list(INTERVAL_EXCLUSIONS),
            "viewport_semantics": "reviewed-world-viewport-v2",
        },
    }


def continuous_claims_v2(certified: bool) -> dict[str, bool]:
    if type(certified) is not bool:
        raise ValueError("Continuous proof v2 state must be boolean")
    return {
        "continuous_preview_model_structural_safety": certified,
        "uniform_gain_zero_to_reviewed_structurally_certified": certified,
        "official_runtime_continuous_equivalence": False,
        "visual_gain_range": False,
        "reviewed_seam_anchors": False,
        "motion_instance_v3": False,
        "publishable_timeline": False,
        "release_authority": False,
    }


def continuous_problem_v2(source_sha: str, ticks: list[int]):
    if not _digest(source_sha) or len(ticks) < 2 \
            or any(type(tick) is not int for tick in ticks) \
            or any(left >= right for left, right in zip(ticks, ticks[1:])):
        raise ValueError("Continuous proof v2 problem is invalid")
    pairs = [[left, right] for left, right in zip(ticks, ticks[1:])]
    config = continuous_analyzer_profile_v2()["config"]
    problem = {
        "source_set_sha256": source_sha,
        "gain_domain": config["gain_domain"],
        "time_domain": {
            "sample_ticks": ticks, "sample_count": len(ticks),
            "segment_count": len(pairs),
            "adjacent_tick_pairs_sha256": canonical_sha256({
                "domain": TICK_PAIRS_HASH_DOMAIN, "pairs": pairs,
            }),
        },
        "interpolation": config["interpolation"],
        "budget": config["budget"],
        "mesh_thresholds": config["mesh_thresholds"],
        "backend": config["backend"], "scope": config["scope"],
        "exclusions": config["exclusions"],
        "viewport_semantics": config["viewport_semantics"],
    }
    problem["problem_sha256"] = continuous_problem_sha256_v2(problem)
    return problem


def continuous_release_gate_v2(certified: bool):
    reasons = list(RELEASE_BLOCKERS)
    if not certified:
        reasons += [
            "continuous_preview_model_safety_unproven",
            "unit_gain_interval_unproven",
        ]
    return {"status": "blocked", "reason_codes": sorted(reasons)}


def continuous_source_sha256_v2(source) -> str:
    payload = {key: value for key, value in source.items()
               if key != "source_set_sha256"}
    return canonical_sha256({"domain": SOURCE_HASH_DOMAIN, "source": payload})


def continuous_problem_sha256_v2(problem) -> str:
    payload = {key: value for key, value in problem.items()
               if key != "problem_sha256"}
    return canonical_sha256({"domain": PROBLEM_HASH_DOMAIN, "problem": payload})


def continuous_segment_sha256_v2(segment) -> str:
    payload = {key: value for key, value in segment.items()
               if key != "segment_evidence_sha256"}
    return canonical_sha256({"domain": SEGMENT_HASH_DOMAIN, "segment": payload})


def _digest(value) -> bool:
    return isinstance(value, str) and len(value) == 64 \
        and all(character in "0123456789abcdef" for character in value)


def _copy(value):
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


__all__ = [
    "MAX_DOCUMENT_BYTES", "continuous_analyzer_profile_v2",
    "continuous_claims_v2", "continuous_problem_sha256_v2",
    "continuous_problem_v2", "continuous_proof_budget_v2",
    "continuous_release_gate_v2", "continuous_segment_sha256_v2",
    "continuous_source_sha256_v2",
]
