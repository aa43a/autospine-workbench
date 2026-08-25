"""Deterministic analytic IK for a planar two-bone chain."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math
from typing import Any, Literal


BendDirection = Literal["positive", "negative"]
ReachState = Literal["reachable", "unreachable_too_far", "unreachable_too_near"]


class TwoBoneIkError(ValueError):
    """Raised when an IK request cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class TwoBoneIkSolution:
    """Finite world-space result and reach evidence for one IK request."""

    root_xy: tuple[float, float]
    requested_target_xy: tuple[float, float]
    resolved_target_xy: tuple[float, float]
    elbow_xy: tuple[float, float]
    aim_direction_xy: tuple[float, float]
    proximal_length: float
    distal_length: float
    requested_distance: float
    resolved_distance: float
    minimum_reach: float
    maximum_reach: float
    proximal_rotation_deg: float
    distal_rotation_deg: float
    elbow_rotation_deg: float
    bend_direction: BendDirection
    reach_state: ReachState
    used_fallback_direction: bool


def solve_two_bone_ik(
    root_xy: Sequence[int | float],
    *,
    proximal_length: int | float,
    distal_length: int | float,
    target_xy: Sequence[int | float],
    bend_direction: BendDirection,
    fallback_direction_xy: Sequence[int | float] = (1.0, 0.0),
) -> TwoBoneIkSolution:
    """Solve one two-bone chain without iteration or mutable solver state.

    ``positive`` places the elbow on the positive signed-cross-product side
    of the aim direction; ``negative`` places it on the opposite side. The
    fallback direction resolves the otherwise ambiguous coincident target.
    Zero-length bones are supported as finite degenerate chains.
    """

    root = _point(root_xy, "root_xy")
    target = _point(target_xy, "target_xy")
    proximal = _length(proximal_length, "proximal_length")
    distal = _length(distal_length, "distal_length")
    bend = _bend_direction(bend_direction)
    fallback = _unit(_point(fallback_direction_xy, "fallback_direction_xy"))

    delta = (target[0] - root[0], target[1] - root[1])
    requested_distance = _finite_hypot(delta, "target distance")
    used_fallback = requested_distance == 0.0
    direction = fallback if used_fallback else (
        delta[0] / requested_distance,
        delta[1] / requested_distance,
    )

    minimum_reach = abs(proximal - distal)
    maximum_reach = _finite_sum(proximal, distal, "maximum reach")
    reach_state, resolved_distance = _resolve_distance(
        requested_distance, minimum_reach, maximum_reach
    )
    resolved_offset = _scale(direction, resolved_distance)
    elbow_offset = _elbow_offset(
        direction,
        resolved_distance,
        proximal,
        distal,
        1.0 if bend == "positive" else -1.0,
    )
    resolved_target = _translated(root, resolved_offset, "resolved target")
    elbow = _translated(root, elbow_offset, "elbow")

    distal_vector = (
        resolved_offset[0] - elbow_offset[0],
        resolved_offset[1] - elbow_offset[1],
    )
    proximal_angle = _vector_angle(elbow_offset, direction)
    distal_angle = _vector_angle(distal_vector, direction)
    elbow_angle = _normalize_angle(distal_angle - proximal_angle)
    result = TwoBoneIkSolution(
        root_xy=root,
        requested_target_xy=target,
        resolved_target_xy=resolved_target,
        elbow_xy=elbow,
        aim_direction_xy=(_clean(direction[0]), _clean(direction[1])),
        proximal_length=proximal,
        distal_length=distal,
        requested_distance=requested_distance,
        resolved_distance=resolved_distance,
        minimum_reach=minimum_reach,
        maximum_reach=maximum_reach,
        proximal_rotation_deg=proximal_angle,
        distal_rotation_deg=distal_angle,
        elbow_rotation_deg=elbow_angle,
        bend_direction=bend,
        reach_state=reach_state,
        used_fallback_direction=used_fallback,
    )
    _require_finite_solution(result)
    return result


def _resolve_distance(distance, minimum, maximum):
    if distance > maximum:
        return "unreachable_too_far", maximum
    if distance < minimum:
        return "unreachable_too_near", minimum
    return "reachable", distance


def _elbow_offset(direction, distance, proximal, distal, bend_sign):
    if proximal == 0.0:
        return 0.0, 0.0
    if distal == 0.0:
        return _scale(direction, distance)
    perpendicular = (-direction[1], direction[0])
    if distance == 0.0:
        return _scale(perpendicular, bend_sign * proximal)
    # This rearrangement avoids squaring lengths and remains stable when the
    # two lengths are nearly equal and the target is close to the root.
    along = 0.5 * distance + 0.5 * ((proximal - distal) / distance) * (
        proximal + distal
    )
    ratio = min(1.0, max(-1.0, along / proximal))
    height = proximal * math.sqrt(max(0.0, 1.0 - ratio * ratio))
    return (
        direction[0] * along + perpendicular[0] * bend_sign * height,
        direction[1] * along + perpendicular[1] * bend_sign * height,
    )


def _point(value: Any, label: str) -> tuple[float, float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or len(value) != 2
    ):
        raise TwoBoneIkError(f"{label} must contain two finite numbers")
    return _number(value[0], label), _number(value[1], label)


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TwoBoneIkError(f"{label} must contain finite numbers")
    result = float(value)
    if not math.isfinite(result):
        raise TwoBoneIkError(f"{label} must contain finite numbers")
    return _clean(result)


def _length(value: Any, label: str) -> float:
    result = _number(value, label)
    if result < 0.0:
        raise TwoBoneIkError(f"{label} must be non-negative")
    return result


def _bend_direction(value: Any) -> BendDirection:
    if value not in ("positive", "negative"):
        raise TwoBoneIkError("bend_direction must be 'positive' or 'negative'")
    return value


def _unit(vector):
    length = _finite_hypot(vector, "fallback direction length")
    if length == 0.0:
        raise TwoBoneIkError("fallback_direction_xy must be non-zero")
    return vector[0] / length, vector[1] / length


def _finite_hypot(vector, label):
    value = math.hypot(vector[0], vector[1])
    if not math.isfinite(value):
        raise TwoBoneIkError(f"{label} is outside the supported finite range")
    return _clean(value)


def _finite_sum(left, right, label):
    value = left + right
    if not math.isfinite(value):
        raise TwoBoneIkError(f"{label} is outside the supported finite range")
    return _clean(value)


def _scale(vector, scalar):
    return vector[0] * scalar, vector[1] * scalar


def _translated(origin, offset, label):
    result = origin[0] + offset[0], origin[1] + offset[1]
    if not all(math.isfinite(value) for value in result):
        raise TwoBoneIkError(f"{label} is outside the supported finite range")
    return _clean(result[0]), _clean(result[1])


def _vector_angle(vector, fallback):
    source = fallback if vector == (0.0, 0.0) else vector
    return _clean(_normalize_angle(math.degrees(math.atan2(source[1], source[0]))))


def _normalize_angle(value):
    return (value + 180.0) % 360.0 - 180.0


def _clean(value):
    return 0.0 if value == 0.0 else float(value)


def _require_finite_solution(solution):
    for field in solution.__dataclass_fields__:
        value = getattr(solution, field)
        values = value if isinstance(value, tuple) else (value,)
        for item in values:
            if isinstance(item, float) and not math.isfinite(item):
                raise TwoBoneIkError("IK solution contains a non-finite value")
