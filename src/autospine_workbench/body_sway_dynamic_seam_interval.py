"""Adaptive continuous proxy proof for one supplied body-sway segment.

Every terminal time/gain box must certify all reviewed anchor pairs.  This is
an engineering proximity proxy only, never a visual-seam or release claim.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from .body_sway_dynamic_seam_evidence_profile import (
    EXCLUSIONS as PROFILE_EXCLUSIONS,
    MAX_BOXES_PER_SEGMENT,
    MAX_DEPTH,
    MAX_SQUARED_ANCHOR_GAP_PX2,
    PROXY_BACKEND,
    THRESHOLD,
)
from .body_sway_dynamic_seam_interval_geometry import (
    BodySwayDynamicSeamIntervalError as GeometryIntervalError,
    assess_body_sway_dynamic_seam_interval_box,
)
from .body_sway_dynamic_seam_interval_results import (
    BodySwayDynamicSeamIntervalResultError,
    BodySwayDynamicSeamRelationshipProof,
    aggregate_dynamic_seam_relationships,
    json_upper,
    merge_dynamic_seam_maxima,
    require_dynamic_seam_assessment_values,
)
from .body_sway_dynamic_seam_locator import (
    PreparedBodySwayDynamicSeamLocatorSet,
    PreparedBodySwayDynamicSeamPair,
    PreparedBodySwayDynamicSeamRelationship,
)
from .body_sway_interval_arithmetic import OutwardInterval
from .body_sway_interval_pose import (
    BodySwayIntervalPoseError,
    prepare_body_sway_interval_pose,
)
from .body_sway_probe_geometry_context import PreparedBodySwayGeometryContext
from .body_sway_probe_geometry_inputs import (
    BodySwayProbeGeometryError,
    normalize_body_sway_pose_sample,
)
from .body_sway_probe_math import BodySwayPoseSample
from .idle_behavior_inventory import BODY_BONE_IDS
from .reviewed_seam_anchor_set_profile import RELATIONSHIP_IDS


SCOPE = (
    "all-reviewed-anchor-pairs",
    "all-six-static-seam-relationships",
    "one-supplied-increasing-endpoint-segment",
    "coupled-uniform-gain-closed-zero-to-one",
)
EXCLUSIONS = tuple(PROFILE_EXCLUSIONS) + (
    "upstream-preview-key-adjacency-binding",
)
TIME_MODEL = "sampled-linear-over-supplied-endpoint-segment"
GAIN_MODEL = "coupled-four-bone-uniform-gain-closed-unit-interval"
PROOF_METHOD = PROXY_BACKEND["method"]
ROUNDING_PROFILE = PROXY_BACKEND["interval_arithmetic"]


class BodySwayDynamicSeamIntervalDriverError(ValueError):
    """Raised when the segment proof cannot be admitted or evaluated."""


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamIntervalBudget:
    """A caller may only lower the pinned per-segment effort budget."""

    max_depth: int = MAX_DEPTH
    max_boxes: int = MAX_BOXES_PER_SEGMENT

    def __post_init__(self) -> None:
        if type(self.max_depth) is not int \
                or not 0 <= self.max_depth <= MAX_DEPTH \
                or type(self.max_boxes) is not int \
                or not 1 <= self.max_boxes <= MAX_BOXES_PER_SEGMENT:
            raise BodySwayDynamicSeamIntervalDriverError(
                "Dynamic seam interval budget may only lower pinned limits"
            )


@dataclass(frozen=True, slots=True)
class BodySwayDynamicSeamIntervalProof:
    left_tick: int
    right_tick: int
    status: str
    reason_codes: tuple[str, ...]
    relationships: tuple[BodySwayDynamicSeamRelationshipProof, ...]
    max_squared_distance_upper_px2: float | None
    threshold_squared_px2: float
    evaluated_box_count: int
    certified_terminal_box_count: int
    indeterminate_terminal_box_count: int
    maximum_depth_reached: int
    relationship_count: int
    pair_count: int
    time_model: str = TIME_MODEL
    gain_model: str = GAIN_MODEL
    proof_method: str = PROOF_METHOD
    rounding_profile: str = ROUNDING_PROFILE
    scope: tuple[str, ...] = SCOPE
    exclusions: tuple[str, ...] = EXCLUSIONS
    metric_interpretation: str = THRESHOLD["interpretation"]
    visual_seam_quality_claimed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class _Box:
    time_fraction: OutwardInterval
    gain: OutwardInterval
    depth: int


def prove_body_sway_dynamic_seam_sampled_linear_segment(
    locator_set: PreparedBodySwayDynamicSeamLocatorSet,
    context: PreparedBodySwayGeometryContext,
    left: BodySwayPoseSample,
    right: BodySwayPoseSample,
    *,
    budget: BodySwayDynamicSeamIntervalBudget | None = None,
) -> BodySwayDynamicSeamIntervalProof:
    """Cover one exact supplied endpoint segment over time and uniform gain."""

    try:
        admitted, inventory = _admit(locator_set, context, left, right)
        limits = BodySwayDynamicSeamIntervalBudget() \
            if budget is None else budget
        if type(limits) is not BodySwayDynamicSeamIntervalBudget:
            raise BodySwayDynamicSeamIntervalDriverError(
                "Dynamic seam interval budget must be exact"
            )
        return _prove(
            locator_set, context, left, right,
            admitted, inventory, limits,
        )
    except BodySwayDynamicSeamIntervalDriverError:
        raise
    except (
        BodySwayIntervalPoseError, BodySwayProbeGeometryError,
        GeometryIntervalError, BodySwayDynamicSeamIntervalResultError,
    ) as exc:
        raise BodySwayDynamicSeamIntervalDriverError(str(exc)) from exc
    except (
        AttributeError, IndexError, KeyError, OverflowError, TypeError,
        ValueError,
    ) as exc:
        raise BodySwayDynamicSeamIntervalDriverError(
            f"Dynamic seam interval proof failed: {exc}"
        ) from exc


def _admit(locator_set, context, left, right):
    if type(locator_set) is not PreparedBodySwayDynamicSeamLocatorSet \
            or type(context) is not PreparedBodySwayGeometryContext \
            or locator_set._rig is not context.skinning_rig:
        raise BodySwayDynamicSeamIntervalDriverError(
            "Dynamic seam locator set and geometry context are cross-wired"
        )
    normalize_body_sway_pose_sample(left, context.bone_ids)
    normalize_body_sway_pose_sample(right, context.bone_ids)
    if left.tick >= right.tick:
        raise BodySwayDynamicSeamIntervalDriverError(
            "Dynamic seam endpoint ticks are not strictly increasing"
        )
    expected_base = tuple(sorted(context.skinning_rig.bone_ids))
    for endpoint in (left, right):
        if tuple(row[0] for row in endpoint.base_rotation_deg) != expected_base \
                or tuple(row[0] for row in endpoint.overlay_rotation_deg) \
                    != BODY_BONE_IDS:
            raise BodySwayDynamicSeamIntervalDriverError(
                "Dynamic seam endpoint rotation inventory is incomplete"
            )
    relationships = locator_set.relationships
    if type(relationships) is not tuple \
            or tuple(row.relationship_id for row in relationships) \
                != RELATIONSHIP_IDS:
        raise BodySwayDynamicSeamIntervalDriverError(
            "Dynamic seam relationship inventory differs"
        )
    inventory = []
    for relationship in relationships:
        if type(relationship) is not PreparedBodySwayDynamicSeamRelationship \
                or type(relationship.anchors) is not tuple \
                or not 2 <= len(relationship.anchors) <= 8 \
                or any(type(row) is not PreparedBodySwayDynamicSeamPair
                       for row in relationship.anchors):
            raise BodySwayDynamicSeamIntervalDriverError(
                "Dynamic seam pair inventory is invalid"
            )
        pair_ids = tuple(row.pair_id for row in relationship.anchors)
        if pair_ids != tuple(
            f"anchor.{index:03d}" for index in range(len(pair_ids))
        ):
            raise BodySwayDynamicSeamIntervalDriverError(
                "Dynamic seam pair inventory differs"
            )
        inventory.append((relationship.relationship_id, pair_ids))
    return {
        "left_base": dict(left.base_rotation_deg),
        "right_base": dict(right.base_rotation_deg),
        "left_overlay": dict(left.overlay_rotation_deg),
        "right_overlay": dict(right.overlay_rotation_deg),
    }, tuple(inventory)


def _prove(locator_set, context, left, right, admitted, inventory, limits):
    pending = [_Box(
        OutwardInterval(0.0, 1.0), OutwardInterval(0.0, 1.0), 0,
    )]
    maxima = [[-math.inf for _pair in pair_ids]
              for _relationship, pair_ids in inventory]
    evaluated = certified = indeterminate = maximum_depth = 0
    reasons: set[str] = set()
    while pending:
        box = pending.pop()
        assessment = _assess(
            locator_set, context, left, right, admitted, box
        )
        values = require_dynamic_seam_assessment_values(
            assessment, inventory
        )
        evaluated += 1
        maximum_depth = max(maximum_depth, box.depth)
        if assessment.status == "certified":
            certified += 1
            merge_dynamic_seam_maxima(maxima, values)
            continue
        stop_reason = _stop_reason(box, pending, evaluated, limits)
        children = None if stop_reason else _split(box)
        if children is not None:
            pending.extend(reversed(children))
            continue
        indeterminate += 1
        merge_dynamic_seam_maxima(maxima, values)
        reasons.update(assessment.reason_codes)
        reasons.add(stop_reason or "parameter_resolution_exhausted")
    relationships = aggregate_dynamic_seam_relationships(inventory, maxima)
    maximum = max(
        value for row in maxima for value in row
    )
    return BodySwayDynamicSeamIntervalProof(
        left.tick, right.tick,
        "continuous_anchor_proximity_certified"
        if indeterminate == 0 else "indeterminate",
        tuple(sorted(reasons)), relationships, json_upper(maximum),
        MAX_SQUARED_ANCHOR_GAP_PX2,
        evaluated, certified, indeterminate, maximum_depth,
        len(inventory), sum(len(row[1]) for row in inventory),
    )


def _assess(locator_set, context, left, right, admitted, box):
    pose = prepare_body_sway_interval_pose(
        context,
        left_base_rotation_deg=admitted["left_base"],
        right_base_rotation_deg=admitted["right_base"],
        left_overlay_rotation_deg=admitted["left_overlay"],
        right_overlay_rotation_deg=admitted["right_overlay"],
        left_root_translation_xy=left.root_translation_xy,
        right_root_translation_xy=right.root_translation_xy,
        time_fraction=box.time_fraction, gain=box.gain,
    )
    return assess_body_sway_dynamic_seam_interval_box(locator_set, pose)


def _stop_reason(box, pending, evaluated, limits):
    if box.depth >= limits.max_depth:
        return "subdivision_depth_exhausted"
    if evaluated + len(pending) + 2 > limits.max_boxes:
        return "subdivision_box_budget_exhausted"
    return None


def _split(box):
    primary = box.time_fraction if box.depth % 2 == 0 else box.gain
    secondary = box.gain if box.depth % 2 == 0 else box.time_fraction
    halves = primary.bisect()
    primary_is_time = box.depth % 2 == 0
    if halves is None:
        halves = secondary.bisect()
        primary_is_time = not primary_is_time
    if halves is None:
        return None
    if primary_is_time:
        return tuple(_Box(half, box.gain, box.depth + 1)
                     for half in halves)
    return tuple(_Box(box.time_fraction, half, box.depth + 1)
                 for half in halves)
