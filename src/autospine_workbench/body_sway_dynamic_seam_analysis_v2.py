"""Bounded P10.5d v2 structural seam analysis over Preview v2 motion."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_dynamic_seam_backend_validation import (
    BodySwayDynamicSeamBackendValidationError,
    require_body_sway_dynamic_seam_interval_result,
)
from .body_sway_dynamic_seam_evidence_profile_v2 import (
    BUDGET,
    CERTIFIED_STATUS,
    SEGMENT_CERTIFIED_STATUS,
    THRESHOLD,
    body_sway_dynamic_seam_claims_v2,
    body_sway_dynamic_seam_problem_v2,
)
from .body_sway_dynamic_seam_evidence_rows_v2 import (
    structure_dynamic_seam_segment_v2,
    summarize_dynamic_seam_segments_v2,
)
from .body_sway_dynamic_seam_interval import (
    EXCLUSIONS as BACKEND_EXCLUSIONS,
    GAIN_MODEL,
    PROOF_METHOD,
    ROUNDING_PROFILE,
    SCOPE as BACKEND_SCOPE,
    TIME_MODEL,
    BodySwayDynamicSeamIntervalBudget,
    BodySwayDynamicSeamIntervalDriverError,
    prove_body_sway_dynamic_seam_sampled_linear_segment,
)
from .body_sway_dynamic_seam_locator import (
    prepare_body_sway_dynamic_seam_locators,
)
from .body_sway_dynamic_seam_validation_v2 import (
    BodySwayDynamicSeamSourceV2ValidationError,
    require_body_sway_dynamic_seam_source_v2,
)
from .body_sway_probe_geometry_context import (
    prepare_body_sway_geometry_context_for_viewport,
)
from .body_sway_probe_sampler import prepare_body_sway_sampler


Progress = Callable[[str, int, int], None]
UPSTREAM_CERTIFIED_STATUS = "continuous_preview_model_structural_certified"


class BodySwayDynamicSeamAnalysisV2Error(ValueError):
    """Raised when an exact v2 source cannot define bounded evidence."""


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamAnalysisV2:
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


def analyze_body_sway_dynamic_seam_source_v2(
    raw_source: dict[str, Any], *, on_progress: Progress | None = None,
) -> BodySwayDynamicSeamAnalysisV2:
    """Replay the source, then evaluate every adjacent Preview v2 segment."""

    try:
        if on_progress is not None and not callable(on_progress):
            raise BodySwayDynamicSeamAnalysisV2Error(
                "Dynamic seam analysis v2 progress callback is invalid"
            )
        source = require_body_sway_dynamic_seam_source_v2(raw_source)
        return _analyze_admitted_body_sway_dynamic_seam_source_v2(
            source, on_progress=on_progress,
        )
    except BodySwayDynamicSeamAnalysisV2Error:
        raise
    except (
        AttributeError, BodySwayDynamicSeamSourceV2ValidationError,
        KeyError, OverflowError, RecursionError, RuntimeError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayDynamicSeamAnalysisV2Error(
            f"Dynamic seam analysis v2 failed: {exc}"
        ) from exc


def _analyze_admitted_body_sway_dynamic_seam_source_v2(
    source: dict[str, Any], *, on_progress: Progress | None,
) -> BodySwayDynamicSeamAnalysisV2:
    proof = source["body_sway_continuous_preview_proof_v2"]
    continuous = proof["source"]
    candidate = continuous["amplitude_envelope_candidate_v2"]
    parameters = candidate["reviewed_selection"]["parameters"]
    ticks = continuous["preview_projection_v2"]["sample_ticks"]
    sampler = prepare_body_sway_sampler(
        candidate["timing"], continuous["motion_instance_v2"]["tracks"],
        cycles=parameters["cycles"],
        per_bone_amplitude_deg=parameters["per_bone_amplitude_deg"],
        per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
    )
    samples = tuple(sampler.sample(tick) for tick in ticks)
    if tuple(sample.tick for sample in samples) != tuple(ticks):
        raise BodySwayDynamicSeamAnalysisV2Error(
            "Dynamic seam v2 sampler ticks differ from the exact problem"
        )
    context = prepare_body_sway_geometry_context_for_viewport(
        continuous["rig_ir"], continuous["target_profile"],
        continuous["reviewed_world_viewport"],
    )
    locators = prepare_body_sway_dynamic_seam_locators(
        continuous["rig_ir"], context,
        source["reviewed_seam_anchor_set_v1"],
    )
    segments = _analyze_segments(
        locators, context, samples, on_progress=on_progress,
    )
    upstream_certified = proof["status"] == UPSTREAM_CERTIFIED_STATUS
    segments_certified = bool(segments) and all(
        row["status"] == SEGMENT_CERTIFIED_STATUS for row in segments
    )
    certified = upstream_certified and segments_certified
    problem = body_sway_dynamic_seam_problem_v2(
        source["source_set_sha256"], list(ticks),
        source["reviewed_seam_anchor_set_v1"],
    )
    analysis = {
        "problem": problem,
        "segments": segments,
        "claims": body_sway_dynamic_seam_claims_v2(certified),
        "status": CERTIFIED_STATUS if certified else "indeterminate",
        "summary": summarize_dynamic_seam_segments_v2(
            segments, proof["status"], upstream_certified,
            problem["reviewed_anchor_inventory"],
        ),
    }
    return BodySwayDynamicSeamAnalysisV2(_canonical(analysis))


def _analyze_segments(locators, context, samples, *, on_progress):
    segments, used_boxes = [], 0
    total = max(0, len(samples) - 1)
    if on_progress is not None:
        on_progress("dynamic_seam_segments", 0, total)
    for index, (left, right) in enumerate(
        zip(samples, samples[1:]), start=1,
    ):
        remaining = BUDGET["max_total_boxes"] - used_boxes
        if remaining <= 0:
            raw = _indeterminate_raw(
                locators, left.tick, right.tick,
                "global_subdivision_box_budget_exhausted",
            )
        else:
            budget = BodySwayDynamicSeamIntervalBudget(
                max_depth=BUDGET["max_depth"],
                max_boxes=min(BUDGET["max_boxes_per_segment"], remaining),
            )
            raw = _prove_segment(locators, context, left, right, budget)
        used_boxes += raw["evaluated_box_count"]
        if "interval_backend_error" in raw["reason_codes"]:
            used_boxes = BUDGET["max_total_boxes"]
        segments.append(structure_dynamic_seam_segment_v2(raw))
        if on_progress is not None:
            on_progress("dynamic_seam_segments", index, total)
    return segments


def _prove_segment(locators, context, left, right, budget):
    try:
        proof = prove_body_sway_dynamic_seam_sampled_linear_segment(
            locators, context, left, right, budget=budget,
        )
        return require_body_sway_dynamic_seam_interval_result(
            proof, locator_set=locators, left_tick=left.tick,
            right_tick=right.tick, budget=budget,
        )
    except (
        ArithmeticError, BodySwayDynamicSeamBackendValidationError,
        BodySwayDynamicSeamIntervalDriverError, OverflowError,
        RuntimeError, TypeError, ValueError,
    ):
        return _indeterminate_raw(
            locators, left.tick, right.tick, "interval_backend_error"
        )


def _indeterminate_raw(locators, left_tick, right_tick, reason):
    relationships = [{
        "relationship_id": relationship.relationship_id,
        "pairs": [{
            "pair_id": pair.pair_id,
            "max_squared_distance_upper_px2": None,
        } for pair in relationship.anchors],
        "max_squared_distance_upper_px2": None,
    } for relationship in locators.relationships]
    return {
        "left_tick": left_tick, "right_tick": right_tick,
        "status": "indeterminate", "reason_codes": [reason],
        "relationships": relationships,
        "max_squared_distance_upper_px2": None,
        "threshold_squared_px2": THRESHOLD["max_squared_anchor_gap_px2"],
        "evaluated_box_count": 0, "certified_terminal_box_count": 0,
        "indeterminate_terminal_box_count": 1,
        "maximum_depth_reached": 0,
        "relationship_count": len(relationships),
        "pair_count": sum(len(row["pairs"]) for row in relationships),
        "time_model": TIME_MODEL, "gain_model": GAIN_MODEL,
        "proof_method": PROOF_METHOD, "rounding_profile": ROUNDING_PROFILE,
        "scope": list(BACKEND_SCOPE),
        "exclusions": list(BACKEND_EXCLUSIONS),
        "metric_interpretation": THRESHOLD["interpretation"],
        "visual_seam_quality_claimed": False,
    }


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


__all__ = [
    "BodySwayDynamicSeamAnalysisV2",
    "BodySwayDynamicSeamAnalysisV2Error",
    "analyze_body_sway_dynamic_seam_source_v2",
]
