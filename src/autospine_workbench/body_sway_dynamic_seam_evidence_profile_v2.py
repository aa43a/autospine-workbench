"""Pinned evidence semantics for BodySwayDynamicSeamProbe v2."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_continuous_proof_profile_v2 import (
    GAIN_DOMAIN,
    INTERPOLATION,
    continuous_problem_v2,
)
from .body_sway_dynamic_seam_evidence_profile import (
    BUDGET,
    PROXY_BACKEND,
    THRESHOLD,
)
from .resolved_project import canonical_sha256
from .reviewed_seam_anchor_set_profile import RELATIONSHIP_IDS
from .reviewed_seam_anchor_set_validation import (
    require_reviewed_seam_anchor_set,
    reviewed_seam_anchor_set_sha256,
)


FORMAT = "autospine-body-sway-dynamic-seam-probe"
FORMAT_VERSION = 2
ANALYZER_ID = "body-sway-dynamic-seam-structural-analyzer-v2"
ANALYZER_VERSION = "2.0.0"
PROBLEM_HASH_DOMAIN = "autospine-body-sway-dynamic-seam-problem/v2"
SEGMENT_HASH_DOMAIN = "autospine-body-sway-dynamic-seam-segment/v2"
INVENTORY_HASH_DOMAIN = (
    "autospine-body-sway-dynamic-seam-anchor-inventory/v2"
)
CERTIFIED_STATUS = (
    "continuous_preview_v2_reviewed_anchor_residual_certified"
)
SEGMENT_CERTIFIED_STATUS = "continuous_anchor_residual_proxy_certified"
OVERLAP_REASON = "attachment_area_overlap_not_modeled"
EVIDENCE_MODEL = {
    "anchor_residual": "reviewed-anchor-squared-distance-upper-bound",
    "gap_proxy": "anchor-residual-upper-bound-not-raster-gap",
    "overlap": "explicit-not-evaluated-by-anchor-locator-proof",
}
SCOPE = (
    "all-reviewed-anchor-pairs",
    "all-six-static-seam-relationships",
    "all-adjacent-preview-v2-tick-pairs",
    "coupled-uniform-gain-closed-zero-to-one",
    "per-relationship-structural-evidence",
)
EXCLUSIONS = (
    "attachment-area-overlap",
    "dynamic-seam-safety-claim",
    "full-attachment-boundary-continuity",
    "official-runtime-equivalence",
    "platform-libm-equivalence",
    "raster-gap-safety",
    "raster-overlap-safety",
    "raster-or-visual-seam-calibration",
    "release-authority",
    "unreviewed-anchor-inference",
)
RELEASE_BLOCKERS = (
    "attachment_overlap_not_modeled",
    "dynamic_seam_safety_unproven",
    "engineering_proxy_not_visual_calibration",
    "official_runtime_equivalence_unproven",
    "publishable_timeline_not_emitted",
    "raster_gap_safety_unproven",
    "raster_overlap_safety_unproven",
    "visual_seam_quality_unproven",
)


def body_sway_dynamic_seam_analyzer_profile_v2() -> dict[str, Any]:
    return {
        "id": ANALYZER_ID,
        "version": ANALYZER_VERSION,
        "canonicalization": "canonical-json-utf8-sort-keys-no-nonfinite",
        "config": {
            "threshold": _copy(THRESHOLD),
            "gain_domain": _copy(GAIN_DOMAIN),
            "interpolation": _copy(INTERPOLATION),
            "budget": _copy(BUDGET),
            "backend": _copy(PROXY_BACKEND),
            "evidence_model": _copy(EVIDENCE_MODEL),
            "scope": list(SCOPE),
            "exclusions": list(EXCLUSIONS),
        },
    }


def body_sway_dynamic_seam_problem_v2(
    source_set_sha256: str,
    sample_ticks: list[int],
    reviewed_set: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        continuous = continuous_problem_v2(source_set_sha256, sample_ticks)
        copied_set = _strict_object(reviewed_set, "reviewed seam-anchor set")
        require_reviewed_seam_anchor_set(copied_set)
        relationships = copied_set["relationships"]
        inventory = {
            "relationship_ids": list(RELATIONSHIP_IDS),
            "relationship_count": len(relationships),
            "anchor_pair_count": sum(
                len(row["anchors"]) for row in relationships
            ),
            "reviewed_seam_anchor_set_v1_sha256":
                reviewed_seam_anchor_set_sha256(copied_set),
            "reviewed_anchor_inventory_sha256": canonical_sha256({
                "domain": INVENTORY_HASH_DOMAIN,
                "relationships": relationships,
            }),
        }
        config = body_sway_dynamic_seam_analyzer_profile_v2()["config"]
        problem = {
            "source_set_sha256": continuous["source_set_sha256"],
            "gain_domain": continuous["gain_domain"],
            "time_domain": continuous["time_domain"],
            "interpolation": continuous["interpolation"],
            "reviewed_anchor_inventory": inventory,
            "threshold": config["threshold"],
            "budget": config["budget"],
            "backend": config["backend"],
            "evidence_model": config["evidence_model"],
            "scope": config["scope"],
            "exclusions": config["exclusions"],
        }
        problem["problem_sha256"] = (
            body_sway_dynamic_seam_problem_sha256_v2(problem)
        )
        return problem
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise ValueError(
            f"Dynamic seam problem v2 input is invalid: {exc}"
        ) from exc


def body_sway_dynamic_seam_claims_v2(certified: bool) -> dict[str, bool]:
    if type(certified) is not bool:
        raise ValueError("Dynamic seam claim v2 state must be boolean")
    return {
        "reviewed_seam_anchor_set_v1_bound": True,
        "continuous_preview_v2_anchor_residual_within_engineering_"
        "tolerance": certified,
        "structural_gap_proxy_within_engineering_tolerance": certified,
        "attachment_area_overlap_assessed": False,
        "dynamic_seam_safety": False,
        "official_runtime_equivalence": False,
        "raster_gap_safety": False,
        "raster_overlap_safety": False,
        "visual_seam_quality": False,
        "publishable_timeline": False,
        "release_authority": False,
    }


def body_sway_dynamic_seam_release_gate_v2(
    certified: bool,
) -> dict[str, Any]:
    if type(certified) is not bool:
        raise ValueError("Dynamic seam release v2 state must be boolean")
    reasons = list(RELEASE_BLOCKERS)
    if not certified:
        reasons.extend((
            "anchor_residual_proxy_unproven",
            "unit_gain_interval_unproven",
        ))
    return {"status": "blocked", "reason_codes": sorted(reasons)}


def body_sway_dynamic_seam_problem_sha256_v2(problem) -> str:
    root = _strict_object(problem, "problem")
    payload = {key: value for key, value in root.items()
               if key != "problem_sha256"}
    return canonical_sha256({
        "domain": PROBLEM_HASH_DOMAIN, "problem": payload,
    })


def body_sway_dynamic_seam_segment_sha256_v2(segment) -> str:
    root = _strict_object(segment, "segment")
    payload = {key: value for key, value in root.items()
               if key != "segment_evidence_sha256"}
    return canonical_sha256({
        "domain": SEGMENT_HASH_DOMAIN, "segment": payload,
    })


def _strict_object(value, label):
    if type(value) is not dict:
        raise ValueError(f"Dynamic seam v2 {label} must be an exact object")
    return _copy(value)


def _copy(value):
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


__all__ = [
    "BUDGET", "CERTIFIED_STATUS", "EVIDENCE_MODEL", "FORMAT",
    "FORMAT_VERSION", "OVERLAP_REASON", "SEGMENT_CERTIFIED_STATUS",
    "THRESHOLD", "body_sway_dynamic_seam_analyzer_profile_v2",
    "body_sway_dynamic_seam_claims_v2",
    "body_sway_dynamic_seam_problem_v2",
    "body_sway_dynamic_seam_release_gate_v2",
    "body_sway_dynamic_seam_segment_sha256_v2",
]
