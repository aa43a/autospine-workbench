"""Pinned result semantics for P10.5d dynamic seam evidence."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_continuous_proof_profile import (
    BACKEND,
    GAIN_DOMAIN,
    INTERPOLATION,
    body_sway_continuous_proof_problem,
)
from .resolved_project import canonical_sha256
from .reviewed_seam_anchor_set_profile import RELATIONSHIP_IDS
from .reviewed_seam_anchor_set_validation import (
    ReviewedSeamAnchorSetValidationError,
    require_reviewed_seam_anchor_set,
    reviewed_seam_anchor_set_sha256,
)


ANALYZER_ID = "body-sway-dynamic-seam-proximity-analyzer"
ANALYZER_VERSION = "1.0.0"
CANONICALIZATION = "canonical-json-utf8-sort-keys-no-nonfinite"
PROBLEM_HASH_DOMAIN = "autospine-body-sway-dynamic-seam-problem/v1"
SEGMENT_HASH_DOMAIN = "autospine-body-sway-dynamic-seam-segment/v1"
INVENTORY_HASH_DOMAIN = (
    "autospine-body-sway-dynamic-seam-anchor-inventory/v1"
)
MAX_SQUARED_ANCHOR_GAP_PX2 = 4.0
MAX_DEPTH = 14
MAX_BOXES_PER_SEGMENT = 32_768
MAX_TOTAL_BOXES = 32_768
THRESHOLD = {
    "metric": "squared-distance-between-reviewed-anchor-world-points",
    "max_squared_anchor_gap_px2": MAX_SQUARED_ANCHOR_GAP_PX2,
    "equivalent_anchor_gap_px": 2.0,
    "interpretation": "engineering-proxy-not-visual-calibration-threshold",
}
PROXY_BACKEND = {
    **BACKEND,
    "locator_enclosure": (
        "reviewed-region-q4096-or-mesh-barycentric-q65535-rational-v1"
    ),
    "anchor_pose": "exact-rational-lbs-moments-common-root-cancelled-v1",
    "distance_bound": "outward-squared-euclidean-no-square-root-v1",
}
BUDGET = {
    "max_depth": MAX_DEPTH,
    "max_boxes_per_segment": MAX_BOXES_PER_SEGMENT,
    "max_total_boxes": MAX_TOTAL_BOXES,
}
SCOPE = (
    "all-reviewed-anchor-pairs",
    "all-six-static-seam-relationships",
    "all-adjacent-preview-sample-tick-pairs",
    "coupled-uniform-gain-closed-zero-to-one",
)
EXCLUSIONS = (
    "dynamic-seam-safety-claim",
    "full-attachment-boundary-continuity",
    "platform-libm-equivalence",
    "raster-or-visual-seam-calibration",
    "runtime-equivalence",
    "unreviewed-anchor-inference",
)
RELEASE_BLOCKERS = (
    "dynamic_seam_safety_unproven",
    "engineering_proxy_not_visual_calibration",
    "publishable_timeline_not_emitted",
    "runtime_equivalence_unproven",
    "visual_seam_quality_unproven",
)


def body_sway_dynamic_seam_analyzer_profile() -> dict[str, Any]:
    """Return the immutable proxy metric, domain, backend, and budget."""

    return {
        "id": ANALYZER_ID,
        "version": ANALYZER_VERSION,
        "canonicalization": CANONICALIZATION,
        "config": {
            "threshold": _copy(THRESHOLD),
            "gain_domain": _copy(GAIN_DOMAIN),
            "interpolation": _copy(INTERPOLATION),
            "budget": _copy(BUDGET),
            "backend": _copy(PROXY_BACKEND),
            "scope": list(SCOPE),
            "exclusions": list(EXCLUSIONS),
        },
    }


def body_sway_dynamic_seam_problem(
    source_set_sha256: str,
    sample_ticks: list[int],
    reviewed_set: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal one exact source, P10.4b2 domain, and reviewed inventory."""

    try:
        if type(source_set_sha256) is not str \
                or type(sample_ticks) is not list:
            raise ValueError(
                "Dynamic seam source identity and sample ticks need exact types"
            )
        continuous = body_sway_continuous_proof_problem(
            source_set_sha256, sample_ticks
        )
        copied_set = _reviewed_set_copy(reviewed_set)
        relationships = copied_set["relationships"]
        inventory = {
            "relationship_ids": list(RELATIONSHIP_IDS),
            "relationship_count": len(relationships),
            "anchor_pair_count": sum(
                len(row["anchors"]) for row in relationships
            ),
            "reviewed_seam_anchor_set_sha256":
                reviewed_seam_anchor_set_sha256(copied_set),
            "reviewed_anchor_inventory_sha256": canonical_sha256({
                "domain": INVENTORY_HASH_DOMAIN,
                "relationships": relationships,
            }),
        }
        profile = body_sway_dynamic_seam_analyzer_profile()["config"]
        if continuous["gain_domain"] != profile["gain_domain"] \
                or continuous["interpolation"] != profile["interpolation"]:
            raise ValueError("Dynamic seam time/gain domain differs from P10.4b2")
        problem = {
            "source_set_sha256": continuous["source_set_sha256"],
            "gain_domain": continuous["gain_domain"],
            "time_domain": continuous["time_domain"],
            "interpolation": continuous["interpolation"],
            "reviewed_anchor_inventory": inventory,
            "threshold": profile["threshold"],
            "budget": profile["budget"],
            "backend": profile["backend"],
            "scope": profile["scope"],
            "exclusions": profile["exclusions"],
        }
        problem["problem_sha256"] = (
            body_sway_dynamic_seam_problem_sha256(problem)
        )
        return problem
    except (
        KeyError, OverflowError, RecursionError,
        ReviewedSeamAnchorSetValidationError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise ValueError(f"Dynamic seam problem input is invalid: {exc}") \
            from exc


def body_sway_dynamic_seam_claims(certified: bool) -> dict[str, bool]:
    """Expose only reviewed-set binding and the conditional proxy result."""

    _require_bool(certified, "claim state")
    return {
        "reviewed_seam_anchor_set_bound": True,
        "continuous_preview_model_reviewed_anchor_proximity_within_"
        "engineering_tolerance": certified,
        "dynamic_seam_safety": False,
        "visual_seam_quality": False,
        "runtime_equivalence": False,
        "publishable_timeline": False,
        "release_authority": False,
    }


def body_sway_dynamic_seam_release_gate(certified: bool) -> dict[str, Any]:
    """Remain blocked even when every proxy interval is certified."""

    _require_bool(certified, "release state")
    reasons = list(RELEASE_BLOCKERS)
    if not certified:
        reasons.extend((
            "continuous_preview_model_reviewed_anchor_proximity_unproven",
            "unit_gain_interval_unproven",
        ))
    return {"status": "blocked", "reason_codes": sorted(reasons)}


def body_sway_dynamic_seam_problem_sha256(
    problem: Mapping[str, Any],
) -> str:
    """Hash a strict JSON problem without its own seal."""

    root = _strict_object(problem, "problem")
    payload = {key: value for key, value in root.items()
               if key != "problem_sha256"}
    return canonical_sha256({
        "domain": PROBLEM_HASH_DOMAIN,
        "problem": payload,
    })


def body_sway_dynamic_seam_segment_sha256(
    segment: Mapping[str, Any],
) -> str:
    """Hash one strict JSON segment without its own evidence seal."""

    root = _strict_object(segment, "segment")
    payload = {key: value for key, value in root.items()
               if key != "segment_evidence_sha256"}
    return canonical_sha256({
        "domain": SEGMENT_HASH_DOMAIN,
        "segment": payload,
    })


def _reviewed_set_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    root = _strict_object(value, "reviewed seam-anchor set")
    require_reviewed_seam_anchor_set(root)
    return root


def _strict_object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"Dynamic seam {label} must be an exact JSON object")
    return _copy(value)


def _require_bool(value: Any, label: str) -> None:
    if type(value) is not bool:
        raise ValueError(f"Dynamic seam {label} must be boolean")


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))
