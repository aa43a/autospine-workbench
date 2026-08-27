"""Pure all-segment P10.5d reviewed-anchor proximity analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_dynamic_seam_backend_validation import (
    BodySwayDynamicSeamBackendValidationError,
    require_body_sway_dynamic_seam_interval_result,
)
from .body_sway_dynamic_seam_evidence_profile import (
    MAX_BOXES_PER_SEGMENT,
    MAX_DEPTH,
    MAX_TOTAL_BOXES,
    THRESHOLD,
    body_sway_dynamic_seam_claims,
    body_sway_dynamic_seam_problem,
    body_sway_dynamic_seam_segment_sha256,
)
from .body_sway_dynamic_seam_interval import (
    EXCLUSIONS,
    GAIN_MODEL,
    PROOF_METHOD,
    ROUNDING_PROFILE,
    SCOPE,
    TIME_MODEL,
    BodySwayDynamicSeamIntervalBudget,
    BodySwayDynamicSeamIntervalDriverError,
    prove_body_sway_dynamic_seam_sampled_linear_segment,
)
from .body_sway_dynamic_seam_locator import (
    PreparedBodySwayDynamicSeamLocatorSet,
    prepare_body_sway_dynamic_seam_locators,
)
from .body_sway_dynamic_seam_source import (
    BodySwayDynamicSeamSourceError,
    require_body_sway_dynamic_seam_source,
)
from .body_sway_probe_geometry_context import (
    prepare_body_sway_geometry_context,
)
from .body_sway_probe_sampler import prepare_body_sway_sampler


CERTIFIED_STATUS = (
    "continuous_preview_model_reviewed_anchor_proximity_certified"
)
UPSTREAM_CERTIFIED_STATUS = (
    "continuous_preview_model_structural_certified"
)


class BodySwayDynamicSeamAnalysisError(ValueError):
    """Raised when exact sources cannot define the pinned seam problem."""


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamAnalysis:
    """Frozen canonical analysis with detached accessors."""

    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def analyze_body_sway_dynamic_seam_source(
    raw_source: dict[str, Any],
) -> BodySwayDynamicSeamAnalysis:
    """Fully replay a source closure, then prove every adjacent tick pair."""

    try:
        source = require_body_sway_dynamic_seam_source(raw_source)
        return _analyze_admitted_body_sway_dynamic_seam_source(source)
    except BodySwayDynamicSeamAnalysisError:
        raise
    except (
        AttributeError, BodySwayDynamicSeamSourceError, KeyError,
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayDynamicSeamAnalysisError(
            f"Dynamic seam analysis failed: {exc}"
        ) from exc


def _analyze_admitted_body_sway_dynamic_seam_source(
    source: dict[str, Any],
) -> BodySwayDynamicSeamAnalysis:
    proof = source["body_sway_continuous_preview_proof"]
    continuous = proof["source"]
    candidate = continuous["amplitude_envelope_candidate"]
    parameters = candidate["reviewed_selection"]["parameters"]
    motion = continuous["motion_instance_v2"]
    ticks = continuous["preview_projection"]["sample_ticks"]
    problem = body_sway_dynamic_seam_problem(
        source["source_set_sha256"], list(ticks),
        source["reviewed_seam_anchor_set"],
    )
    sampler = prepare_body_sway_sampler(
        candidate["timing"], motion["tracks"],
        cycles=parameters["cycles"],
        per_bone_amplitude_deg=parameters["per_bone_amplitude_deg"],
        per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
    )
    samples = tuple(sampler.sample(tick) for tick in ticks)
    if tuple(sample.tick for sample in samples) != tuple(ticks):
        raise BodySwayDynamicSeamAnalysisError(
            "Dynamic seam sampler ticks differ from the exact problem"
        )
    context = prepare_body_sway_geometry_context(
        continuous["rig_ir"], continuous["target_profile"]
    )
    locator_set = prepare_body_sway_dynamic_seam_locators(
        continuous["rig_ir"], context,
        source["reviewed_seam_anchor_set"],
    )
    segments = _analyze_segments(locator_set, context, samples)
    upstream_certified = proof["status"] == UPSTREAM_CERTIFIED_STATUS
    segments_certified = bool(segments) and all(
        row["status"] == "continuous_anchor_proximity_certified"
        for row in segments
    )
    certified = upstream_certified and segments_certified
    analysis = {
        "problem": problem,
        "segments": segments,
        "claims": body_sway_dynamic_seam_claims(certified),
        "status": CERTIFIED_STATUS if certified else "indeterminate",
        "summary": _summary(
            segments, proof["status"], upstream_certified,
            problem["reviewed_anchor_inventory"],
        ),
    }
    return BodySwayDynamicSeamAnalysis(_canonical(analysis))


def _analyze_segments(locator_set, context, samples):
    segments, used_boxes = [], 0
    for left, right in zip(samples, samples[1:]):
        remaining = MAX_TOTAL_BOXES - used_boxes
        if remaining <= 0:
            row = _indeterminate_segment(
                locator_set, left.tick, right.tick,
                "global_subdivision_box_budget_exhausted",
            )
        else:
            budget = BodySwayDynamicSeamIntervalBudget(
                max_depth=MAX_DEPTH,
                max_boxes=min(MAX_BOXES_PER_SEGMENT, remaining),
            )
            row = _prove_segment(
                locator_set, context, left, right, budget
            )
        used_boxes += row["evaluated_box_count"]
        if "interval_backend_error" in row["reason_codes"]:
            used_boxes = MAX_TOTAL_BOXES
        segments.append(row)
    return segments


def _prove_segment(locator_set, context, left, right, budget):
    try:
        proof = prove_body_sway_dynamic_seam_sampled_linear_segment(
            locator_set, context, left, right, budget=budget
        )
        row = require_body_sway_dynamic_seam_interval_result(
            proof, locator_set=locator_set,
            left_tick=left.tick, right_tick=right.tick, budget=budget,
        )
    except (
        ArithmeticError, BodySwayDynamicSeamBackendValidationError,
        BodySwayDynamicSeamIntervalDriverError, RuntimeError,
        TypeError, ValueError,
    ):
        row = _indeterminate_segment(
            locator_set, left.tick, right.tick, "interval_backend_error"
        )
    row["segment_evidence_sha256"] = (
        body_sway_dynamic_seam_segment_sha256(row)
    )
    return row


def _indeterminate_segment(locator_set, left_tick, right_tick, reason):
    relationships = [{
        "relationship_id": relationship.relationship_id,
        "pairs": [{
            "pair_id": pair.pair_id,
            "max_squared_distance_upper_px2": None,
        } for pair in relationship.anchors],
        "max_squared_distance_upper_px2": None,
    } for relationship in locator_set.relationships]
    row = {
        "left_tick": left_tick, "right_tick": right_tick,
        "status": "indeterminate", "reason_codes": [reason],
        "relationships": relationships,
        "max_squared_distance_upper_px2": None,
        "threshold_squared_px2": THRESHOLD["max_squared_anchor_gap_px2"],
        "evaluated_box_count": 0,
        "certified_terminal_box_count": 0,
        "indeterminate_terminal_box_count": 1,
        "maximum_depth_reached": 0,
        "relationship_count": len(relationships),
        "pair_count": sum(len(row["pairs"]) for row in relationships),
        "time_model": TIME_MODEL, "gain_model": GAIN_MODEL,
        "proof_method": PROOF_METHOD, "rounding_profile": ROUNDING_PROFILE,
        "scope": list(SCOPE), "exclusions": list(EXCLUSIONS),
        "metric_interpretation": THRESHOLD["interpretation"],
        "visual_seam_quality_claimed": False,
    }
    row["segment_evidence_sha256"] = (
        body_sway_dynamic_seam_segment_sha256(row)
    )
    return row


def _summary(segments, upstream_status, upstream_certified, inventory):
    certified_count = sum(
        row["status"] == "continuous_anchor_proximity_certified"
        for row in segments
    )
    reasons = {reason for row in segments for reason in row["reason_codes"]}
    if not upstream_certified:
        reasons.add("upstream_continuous_preview_model_structural_unproven")
    maxima = [row["max_squared_distance_upper_px2"] for row in segments]
    maximum = None if any(value is None for value in maxima) else max(maxima)
    return {
        "segment_count": len(segments),
        "certified_segment_count": certified_count,
        "indeterminate_segment_count": len(segments) - certified_count,
        "evaluated_box_count": sum(row["evaluated_box_count"]
                                   for row in segments),
        "certified_terminal_box_count": sum(
            row["certified_terminal_box_count"] for row in segments
        ),
        "indeterminate_terminal_box_count": sum(
            row["indeterminate_terminal_box_count"] for row in segments
        ),
        "maximum_depth_reached": max(
            (row["maximum_depth_reached"] for row in segments), default=0
        ),
        "relationship_count": inventory["relationship_count"],
        "anchor_pair_count": inventory["anchor_pair_count"],
        "max_squared_distance_upper_px2": maximum,
        "threshold_squared_px2": THRESHOLD["max_squared_anchor_gap_px2"],
        "upstream_continuous_preview_model_status": upstream_status,
        "all_seam_segments_certified": (
            bool(segments) and certified_count == len(segments)
        ),
        "reason_codes": sorted(reasons),
    }


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
