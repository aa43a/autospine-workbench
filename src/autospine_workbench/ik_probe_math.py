"""Finite scalar and point helpers shared by P4 IK numerical probes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any


NUMERIC_PRECISION_DECIMALS = 12


class IkProbeMathError(ValueError):
    """Raised when probe arithmetic receives an invalid finite value."""


def mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise IkProbeMathError(f"{label} must be an object")
    return value


def point(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) \
            or len(value) != 2:
        raise IkProbeMathError(f"{label} must contain two finite numbers")
    return _number(value[0], label), _number(value[1], label)


def positive(value: Any, label: str) -> float:
    result = _number(value, label)
    if result <= 0.0:
        raise IkProbeMathError(f"{label} must be positive")
    return result


def nonnegative(value: Any, label: str) -> float:
    result = _number(value, label)
    if result < 0.0:
        raise IkProbeMathError(f"{label} must be non-negative")
    return result


def unit(value: tuple[float, float]) -> tuple[float, float]:
    length = math.hypot(*value)
    if not math.isfinite(length) or length == 0.0:
        raise IkProbeMathError("fallback direction must be non-zero")
    return value[0] / length, value[1] / length


def radial(root, direction, radius) -> tuple[float, float]:
    return root[0] + direction[0] * radius, root[1] + direction[1] * radius


def distance(left, right) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def quantize(value: float) -> float:
    threshold = 10 ** -NUMERIC_PRECISION_DECIMALS
    return 0.0 if abs(value) <= threshold else float(
        round(value, NUMERIC_PRECISION_DECIMALS)
    )


def quantize_point(value) -> list[float]:
    return [quantize(value[0]), quantize(value[1])]


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise IkProbeMathError(f"{label} must be finite")
    return float(value)
