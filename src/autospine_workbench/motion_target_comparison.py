"""Exact-structure, tolerant-number comparison for derived motion geometry."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from .motion_target_geometry import GEOMETRY_TOLERANCE_PX


def geometry_equivalent(left: Any, right: Any) -> bool:
    """Require identical JSON structure while tolerating bounded FK roundoff."""

    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is bool and type(right) is bool and left == right
    if isinstance(left, (int, float)) or isinstance(right, (int, float)):
        return (
            _finite_number(left) and _finite_number(right)
            and abs(float(left) - float(right)) <= GEOMETRY_TOLERANCE_PX
        )
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        return (
            isinstance(left, Mapping) and isinstance(right, Mapping)
            and set(left) == set(right)
            and all(geometry_equivalent(left[key], right[key]) for key in left)
        )
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list) and isinstance(right, list)
            and len(left) == len(right)
            and all(geometry_equivalent(a, b) for a, b in zip(left, right))
        )
    return type(left) is type(right) and left == right


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )
