"""Exact linear sampling helpers for MotionInstance v2 overlay compilation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any


DECIMALS = 9


class MotionInstanceV2SamplingError(ValueError):
    """Raised when an overlay source track cannot be sampled exactly."""


def sample_vector_keys(
    keys: Sequence[Mapping[str, Any]], tick: int, *, value_field: str,
) -> tuple[float, float]:
    """Linearly sample a complete two-component key track at ``tick``."""

    if not keys:
        raise MotionInstanceV2SamplingError("Vector key track is empty")
    if type(tick) is not int:
        raise MotionInstanceV2SamplingError("Sample tick must be an integer")
    first_tick, last_tick = keys[0].get("tick"), keys[-1].get("tick")
    if type(first_tick) is not int or type(last_tick) is not int \
            or not first_tick <= tick <= last_tick:
        raise MotionInstanceV2SamplingError("Sample tick is outside the key span")
    previous_tick = -1
    for index, row in enumerate(keys):
        right_tick = row.get("tick")
        if type(right_tick) is not int or right_tick <= previous_tick:
            raise MotionInstanceV2SamplingError(
                "Vector key ticks must be strictly increasing"
            )
        right = _vector(row.get(value_field), value_field)
        if right_tick == tick:
            return right
        if right_tick > tick:
            left_row = keys[index - 1]
            left_tick = left_row["tick"]
            left = _vector(left_row.get(value_field), value_field)
            ratio = (tick - left_tick) / (right_tick - left_tick)
            return (
                left[0] + (right[0] - left[0]) * ratio,
                left[1] + (right[1] - left[1]) * ratio,
            )
        previous_tick = right_tick
    raise MotionInstanceV2SamplingError("Sample tick is outside the key span")


def quantize_vector(value: tuple[float, float]) -> list[float]:
    """Round a finite vector to the v2 overlay's nine-decimal contract."""

    return [_quantize(value[0]), _quantize(value[1])]


def _vector(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise MotionInstanceV2SamplingError(f"{label} must contain two numbers")
    return _number(value[0], label), _number(value[1], label)


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise MotionInstanceV2SamplingError(f"{label} must be finite")
    return float(value)


def _quantize(value: float) -> float:
    if not math.isfinite(value):
        raise MotionInstanceV2SamplingError("Overlay result must be finite")
    result = round(float(value), DECIMALS)
    return 0.0 if result == 0 else result
