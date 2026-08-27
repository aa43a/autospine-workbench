"""Strict terminal assessment validation and aggregation for P10.5d."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .body_sway_dynamic_seam_evidence_profile import (
    MAX_SQUARED_ANCHOR_GAP_PX2,
)
from .body_sway_dynamic_seam_interval_geometry import (
    BodySwayDynamicSeamIntervalBoxAssessment,
    BodySwayDynamicSeamPairIntervalBound,
    BodySwayDynamicSeamRelationshipIntervalBound,
)
from .body_sway_interval_arithmetic import OutwardInterval


GEOMETRY_REASON_CODES = frozenset({
    "anchor_proximity_unproven",
    "non_finite_interval_bound",
})
DISTANCE_METRIC = "outward-squared-euclidean-no-sqrt"


class BodySwayDynamicSeamIntervalResultError(ValueError):
    """Raised when backend terminal evidence changes shape or identity."""


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamPairProof:
    pair_id: str
    max_squared_distance_upper_px2: float | None


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamRelationshipProof:
    relationship_id: str
    pairs: tuple[BodySwayDynamicSeamPairProof, ...]
    max_squared_distance_upper_px2: float | None


def require_dynamic_seam_assessment_values(assessment, inventory):
    """Return the exact per-pair uppers after closed-shape validation."""

    if type(assessment) is not BodySwayDynamicSeamIntervalBoxAssessment \
            or type(assessment.status) is not str \
            or assessment.status not in {"certified", "indeterminate"} \
            or type(assessment.reason_codes) is not tuple \
            or assessment.reason_codes != tuple(sorted(set(
                assessment.reason_codes
            ))) or not set(assessment.reason_codes).issubset(
                GEOMETRY_REASON_CODES
            ) or type(assessment.relationships) is not tuple \
            or type(assessment.threshold_squared_px2) is not float \
            or assessment.threshold_squared_px2 \
                != MAX_SQUARED_ANCHOR_GAP_PX2 \
            or assessment.common_root_translation_cancelled is not True \
            or assessment.distance_metric != DISTANCE_METRIC:
        raise BodySwayDynamicSeamIntervalResultError(
            "Dynamic seam interval assessment is invalid"
        )
    values = []
    if len(assessment.relationships) != len(inventory):
        raise BodySwayDynamicSeamIntervalResultError(
            "Dynamic seam interval relationship evidence differs"
        )
    for row, (relationship_id, pair_ids) in zip(
        assessment.relationships, inventory, strict=True,
    ):
        if type(row) is not BodySwayDynamicSeamRelationshipIntervalBound \
                or row.relationship_id != relationship_id \
                or type(row.pairs) is not tuple \
                or tuple(pair.pair_id for pair in row.pairs) != pair_ids:
            raise BodySwayDynamicSeamIntervalResultError(
                "Dynamic seam interval pair evidence differs"
            )
        row_values = tuple(_upper(pair) for pair in row.pairs)
        if type(row.max_squared_distance_upper_px2) is not float \
                or row.max_squared_distance_upper_px2 != max(row_values):
            raise BodySwayDynamicSeamIntervalResultError(
                "Dynamic seam relationship maximum differs"
            )
        values.append(row_values)
    flat = tuple(value for row in values for value in row)
    expected_reasons = set()
    if not math.isfinite(max(flat)) or any(
        not pair.delta_x_px.finite or not pair.delta_y_px.finite
        for row in assessment.relationships for pair in row.pairs
    ):
        expected_reasons.add("non_finite_interval_bound")
    if not max(flat) <= MAX_SQUARED_ANCHOR_GAP_PX2:
        expected_reasons.add("anchor_proximity_unproven")
    expected_status = "certified" if not expected_reasons else "indeterminate"
    if type(assessment.relationship_count) is not int \
            or type(assessment.pair_count) is not int \
            or type(assessment.max_squared_distance_upper_px2) is not float \
            or assessment.relationship_count != len(inventory) \
            or assessment.pair_count != len(flat) \
            or assessment.max_squared_distance_upper_px2 != max(flat) \
            or assessment.status != expected_status \
            or set(assessment.reason_codes) != expected_reasons:
        raise BodySwayDynamicSeamIntervalResultError(
            "Dynamic seam interval assessment summary differs"
        )
    return tuple(values)


def merge_dynamic_seam_maxima(maxima, values) -> None:
    for target, source in zip(maxima, values, strict=True):
        for index, value in enumerate(source):
            target[index] = max(target[index], value)


def aggregate_dynamic_seam_relationships(inventory, maxima):
    return tuple(
        BodySwayDynamicSeamRelationshipProof(
            relationship_id,
            tuple(BodySwayDynamicSeamPairProof(pair_id, json_upper(value))
                  for pair_id, value in zip(pair_ids, values, strict=True)),
            json_upper(max(values)),
        )
        for (relationship_id, pair_ids), values in zip(
            inventory, maxima, strict=True
        )
    )


def json_upper(value: float) -> float | None:
    return value if math.isfinite(value) else None


def _upper(pair):
    if type(pair) is not BodySwayDynamicSeamPairIntervalBound \
            or type(pair.delta_x_px) is not OutwardInterval \
            or type(pair.delta_y_px) is not OutwardInterval \
            or type(pair.squared_distance_upper_px2) is not float \
            or math.isnan(pair.squared_distance_upper_px2) \
            or pair.squared_distance_upper_px2 < 0.0:
        raise BodySwayDynamicSeamIntervalResultError(
            "Dynamic seam pair upper bound is invalid"
        )
    expected = (pair.delta_x_px.square() + pair.delta_y_px.square()).upper
    if pair.squared_distance_upper_px2 != expected:
        raise BodySwayDynamicSeamIntervalResultError(
            "Dynamic seam pair squared upper differs from its intervals"
        )
    return expected
