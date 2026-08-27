"""Strict admission for one P10.5d dynamic-seam interval result."""

from __future__ import annotations

import math

from .body_sway_dynamic_seam_evidence_profile import (
    MAX_SQUARED_ANCHOR_GAP_PX2,
    THRESHOLD,
)
from .body_sway_dynamic_seam_interval import (
    EXCLUSIONS,
    GAIN_MODEL,
    PROOF_METHOD,
    ROUNDING_PROFILE,
    SCOPE,
    TIME_MODEL,
    BodySwayDynamicSeamIntervalBudget,
    BodySwayDynamicSeamIntervalProof,
)
from .body_sway_dynamic_seam_interval_results import (
    BodySwayDynamicSeamPairProof,
    BodySwayDynamicSeamRelationshipProof,
)
from .body_sway_dynamic_seam_locator import (
    PreparedBodySwayDynamicSeamLocatorSet,
)


class BodySwayDynamicSeamBackendValidationError(ValueError):
    """Raised when backend evidence changes shape, identity, or semantics."""


_REASON_CODES = {
    "anchor_proximity_unproven",
    "non_finite_interval_bound",
    "parameter_resolution_exhausted",
    "subdivision_box_budget_exhausted",
    "subdivision_depth_exhausted",
}
_GEOMETRY_REASONS = {
    "anchor_proximity_unproven", "non_finite_interval_bound",
}
_STOP_REASONS = {
    "parameter_resolution_exhausted",
    "subdivision_box_budget_exhausted",
    "subdivision_depth_exhausted",
}


def require_body_sway_dynamic_seam_interval_result(
    proof: BodySwayDynamicSeamIntervalProof,
    *,
    locator_set: PreparedBodySwayDynamicSeamLocatorSet,
    left_tick: int,
    right_tick: int,
    budget: BodySwayDynamicSeamIntervalBudget,
) -> dict:
    """Validate and detach the exact result produced by the interval driver."""

    if type(proof) is not BodySwayDynamicSeamIntervalProof \
            or type(locator_set) is not PreparedBodySwayDynamicSeamLocatorSet \
            or type(budget) is not BodySwayDynamicSeamIntervalBudget:
        raise BodySwayDynamicSeamBackendValidationError(
            "Dynamic seam backend result or context type is invalid"
        )
    if type(left_tick) is not int or type(right_tick) is not int \
            or left_tick >= right_tick \
            or type(proof.left_tick) is not int \
            or type(proof.right_tick) is not int \
            or proof.left_tick != left_tick or proof.right_tick != right_tick:
        raise BodySwayDynamicSeamBackendValidationError(
            "Dynamic seam backend endpoint ticks differ"
        )
    _require_fixed_semantics(proof)
    pair_values = _require_relationships(proof, locator_set)
    _require_counts(proof, locator_set, budget)
    _require_conclusion(proof, pair_values)
    return proof.to_dict()


def _require_fixed_semantics(proof) -> None:
    expected = (
        (proof.time_model, TIME_MODEL),
        (proof.gain_model, GAIN_MODEL),
        (proof.proof_method, PROOF_METHOD),
        (proof.rounding_profile, ROUNDING_PROFILE),
        (proof.scope, tuple(SCOPE)),
        (proof.exclusions, tuple(EXCLUSIONS)),
    )
    if any(actual != wanted for actual, wanted in expected) \
            or proof.threshold_squared_px2 != MAX_SQUARED_ANCHOR_GAP_PX2 \
            or type(proof.threshold_squared_px2) is not float \
            or proof.metric_interpretation != THRESHOLD["interpretation"] \
            or proof.visual_seam_quality_claimed is not False:
        raise BodySwayDynamicSeamBackendValidationError(
            "Dynamic seam backend fixed semantics differ"
        )
    if proof.status not in {
        "continuous_anchor_proximity_certified", "indeterminate",
    } or type(proof.reason_codes) is not tuple \
            or proof.reason_codes != tuple(sorted(set(proof.reason_codes))) \
            or any(type(reason) is not str or not reason
                   for reason in proof.reason_codes) \
            or not set(proof.reason_codes) <= _REASON_CODES:
        raise BodySwayDynamicSeamBackendValidationError(
            "Dynamic seam backend conclusion is invalid"
        )


def _require_relationships(proof, locator_set):
    if type(proof.relationships) is not tuple \
            or len(proof.relationships) != len(locator_set.relationships):
        raise BodySwayDynamicSeamBackendValidationError(
            "Dynamic seam backend relationship inventory differs"
        )
    all_values = []
    for actual, prepared in zip(
        proof.relationships, locator_set.relationships, strict=True,
    ):
        if type(actual) is not BodySwayDynamicSeamRelationshipProof \
                or actual.relationship_id != prepared.relationship_id \
                or type(actual.pairs) is not tuple \
                or len(actual.pairs) != len(prepared.anchors):
            raise BodySwayDynamicSeamBackendValidationError(
                "Dynamic seam backend relationship evidence differs"
            )
        values = []
        for pair, locator_pair in zip(
            actual.pairs, prepared.anchors, strict=True,
        ):
            if type(pair) is not BodySwayDynamicSeamPairProof \
                    or pair.pair_id != locator_pair.pair_id:
                raise BodySwayDynamicSeamBackendValidationError(
                    "Dynamic seam backend pair evidence differs"
                )
            values.append(_upper(pair.max_squared_distance_upper_px2))
        if actual.max_squared_distance_upper_px2 != _maximum(values):
            raise BodySwayDynamicSeamBackendValidationError(
                "Dynamic seam backend relationship maximum differs"
            )
        all_values.extend(values)
    if proof.max_squared_distance_upper_px2 != _maximum(all_values):
        raise BodySwayDynamicSeamBackendValidationError(
            "Dynamic seam backend global maximum differs"
        )
    return all_values


def _require_counts(proof, locator_set, budget) -> None:
    pair_count = sum(len(row.anchors) for row in locator_set.relationships)
    counts = (
        proof.evaluated_box_count,
        proof.certified_terminal_box_count,
        proof.indeterminate_terminal_box_count,
        proof.maximum_depth_reached,
        proof.relationship_count,
        proof.pair_count,
    )
    if any(type(value) is not int or value < 0 for value in counts) \
            or not 1 <= proof.evaluated_box_count <= budget.max_boxes \
            or proof.certified_terminal_box_count \
                + proof.indeterminate_terminal_box_count < 1 \
            or proof.evaluated_box_count != 2 * (
                proof.certified_terminal_box_count
                + proof.indeterminate_terminal_box_count
            ) - 1 \
            or proof.maximum_depth_reached > budget.max_depth \
            or proof.relationship_count != len(locator_set.relationships) \
            or proof.pair_count != pair_count:
        raise BodySwayDynamicSeamBackendValidationError(
            "Dynamic seam backend counts or budget usage differ"
        )


def _require_conclusion(proof, pair_values) -> None:
    certified = proof.status == "continuous_anchor_proximity_certified"
    reasons = set(proof.reason_codes)
    has_unknown = any(value is None for value in pair_values)
    has_over_threshold = any(
        value is not None and value > MAX_SQUARED_ANCHOR_GAP_PX2
        for value in pair_values
    )
    if certified:
        invalid = bool(reasons) \
            or proof.indeterminate_terminal_box_count != 0 \
            or proof.certified_terminal_box_count < 1 \
            or has_unknown or has_over_threshold
    else:
        invalid = proof.indeterminate_terminal_box_count < 1 \
            or not reasons & _GEOMETRY_REASONS \
            or not reasons & _STOP_REASONS \
            or has_unknown \
                != ("non_finite_interval_bound" in reasons) \
            or (has_unknown or has_over_threshold) \
                != ("anchor_proximity_unproven" in reasons)
    if invalid:
        raise BodySwayDynamicSeamBackendValidationError(
            "Dynamic seam backend status overclaims its evidence"
        )


def _upper(value):
    if value is None:
        return None
    if type(value) is not float or not math.isfinite(value) or value < 0.0:
        raise BodySwayDynamicSeamBackendValidationError(
            "Dynamic seam backend pair upper is invalid"
        )
    return value


def _maximum(values):
    if not values or any(value is None for value in values):
        return None
    return max(values)
