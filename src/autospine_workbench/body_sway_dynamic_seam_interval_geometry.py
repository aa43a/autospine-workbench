"""Conservative interval gap bounds for reviewed body-sway seam anchors.

Parent and child locator moments are differenced exactly before interval FK is
injected.  Their common post-LBS root translation therefore cancels
algebraically; only two independent Q4096 output half-steps remain.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math

from .body_sway_dynamic_seam_locator import (
    PreparedBodySwayDynamicSeamLocatorSet,
)
from .body_sway_dynamic_seam_moments import (
    fraction_to_outward_interval,
)
from .body_sway_dynamic_seam_evidence_profile import (
    MAX_SQUARED_ANCHOR_GAP_PX2,
)
from .body_sway_dynamic_seam_interval_validation import (
    require_dynamic_seam_interval_inputs,
    require_dynamic_seam_locator,
)
from .body_sway_interval_arithmetic import OutwardInterval, ZERO
from .body_sway_interval_pose import (
    PreparedBodySwayIntervalPose,
)


_Q4096_DIFFERENCE_HALF_WIDTH = 1.0 / 4096.0
_OUTPUT_DIFFERENCE_ERROR = OutwardInterval(
    -_Q4096_DIFFERENCE_HALF_WIDTH, _Q4096_DIFFERENCE_HALF_WIDTH,
)


class BodySwayDynamicSeamIntervalError(ValueError):
    """Raised when an interval seam box cannot be evaluated exactly."""


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamPairIntervalBound:
    pair_id: str
    delta_x_px: OutwardInterval
    delta_y_px: OutwardInterval
    squared_distance_upper_px2: float


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamRelationshipIntervalBound:
    relationship_id: str
    pairs: tuple[BodySwayDynamicSeamPairIntervalBound, ...]
    max_squared_distance_upper_px2: float


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamIntervalBoxAssessment:
    status: str
    reason_codes: tuple[str, ...]
    relationships: tuple[
        BodySwayDynamicSeamRelationshipIntervalBound, ...
    ]
    max_squared_distance_upper_px2: float
    relationship_count: int
    pair_count: int
    threshold_squared_px2: float
    common_root_translation_cancelled: bool = True
    distance_metric: str = "outward-squared-euclidean-no-sqrt"


@dataclass(frozen=True, slots=True)
class _DifferenceMoment:
    bone_index: int
    bone_id: str
    affine_weight: Fraction
    setup_x_moment: Fraction
    setup_y_moment: Fraction


def assess_body_sway_dynamic_seam_interval_box(
    locator_set: PreparedBodySwayDynamicSeamLocatorSet,
    pose: PreparedBodySwayIntervalPose,
) -> BodySwayDynamicSeamIntervalBoxAssessment:
    """Bound every reviewed pair over one already prepared interval pose."""

    try:
        rig, pose_nonfinite = require_dynamic_seam_interval_inputs(
            locator_set, pose
        )
        relationships = tuple(
            _relationship_bound(row, rig, pose.skin_matrices)
            for row in locator_set.relationships
        )
        maximum = max(
            row.max_squared_distance_upper_px2 for row in relationships
        )
        reasons = set()
        if pose_nonfinite or not math.isfinite(maximum):
            reasons.add("non_finite_interval_bound")
        if not maximum <= MAX_SQUARED_ANCHOR_GAP_PX2:
            reasons.add("anchor_proximity_unproven")
        pair_count = sum(len(row.pairs) for row in relationships)
        return BodySwayDynamicSeamIntervalBoxAssessment(
            status="certified" if not reasons else "indeterminate",
            reason_codes=tuple(sorted(reasons)),
            relationships=relationships,
            max_squared_distance_upper_px2=maximum,
            relationship_count=len(relationships), pair_count=pair_count,
            threshold_squared_px2=MAX_SQUARED_ANCHOR_GAP_PX2,
        )
    except BodySwayDynamicSeamIntervalError:
        raise
    except (
        AttributeError, IndexError, KeyError, OverflowError, TypeError,
        ValueError,
    ) as exc:
        raise BodySwayDynamicSeamIntervalError(
            f"Dynamic seam interval geometry failed: {exc}"
        ) from exc


def _relationship_bound(relationship, rig, matrices):
    pairs = tuple(_pair_bound(pair, rig, matrices)
                  for pair in relationship.anchors)
    return BodySwayDynamicSeamRelationshipIntervalBound(
        relationship.relationship_id, pairs,
        max(row.squared_distance_upper_px2 for row in pairs),
    )


def _pair_bound(pair, rig, matrices):
    moments = _difference_moments(pair, rig)
    x_terms, y_terms = [], []
    for moment in moments:
        matrix = matrices[moment.bone_index]
        _append_term(x_terms, matrix[0], moment.setup_x_moment)
        _append_term(x_terms, matrix[2], moment.setup_y_moment)
        _append_term(x_terms, matrix[4], moment.affine_weight)
        _append_term(y_terms, matrix[1], moment.setup_x_moment)
        _append_term(y_terms, matrix[3], moment.setup_y_moment)
        _append_term(y_terms, matrix[5], moment.affine_weight)
    delta_x = _with_output_error(_outward_sum(x_terms))
    delta_y = _with_output_error(_outward_sum(y_terms))
    squared = delta_x.square() + delta_y.square()
    return BodySwayDynamicSeamPairIntervalBound(
        pair.pair_id, delta_x, delta_y, squared.upper
    )


def _difference_moments(pair, rig):
    totals: dict[tuple[int, str], list[Fraction]] = {}
    for sign, locator in ((Fraction(-1), pair.parent),
                          (Fraction(1), pair.child)):
        for moment in require_dynamic_seam_locator(locator, rig):
            key = moment.bone_index, moment.bone_id
            row = totals.setdefault(
                key, [Fraction(0), Fraction(0), Fraction(0)]
            )
            row[0] += sign * moment.affine_weight
            row[1] += sign * moment.setup_x_moment
            row[2] += sign * moment.setup_y_moment
    return tuple(
        _DifferenceMoment(index, bone_id, *totals[(index, bone_id)])
        for index, bone_id in sorted(totals, key=lambda row: (row[1], row[0]))
        if any(totals[(index, bone_id)])
    )


def _append_term(result, matrix_value, coefficient):
    if coefficient:
        result.append(
            matrix_value * fraction_to_outward_interval(coefficient)
        )


def _outward_sum(terms):
    if not terms:
        return ZERO
    result = terms[0]
    for term in terms[1:]:
        result = result + term
    return result


def _with_output_error(value):
    return _OUTPUT_DIFFERENCE_ERROR if value == ZERO \
        else value + _OUTPUT_DIFFERENCE_ERROR
