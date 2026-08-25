"""Closed, hashable policy for component-cohesive bilateral split v1.2."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .png_rgba import MAX_RGBA_PIXELS


_FIELDS = frozenset(
    {
        "perceptible_alpha_threshold",
        "significant_min_area",
        "significant_min_area_ratio",
        "pair_min_component_ratio",
        "pair_min_coverage_ratio",
        "assignment_min_relative_margin",
        "fused_endpoint_min_px",
        "fused_endpoint_bbox_ratio",
        "fused_min_side_pixel_ratio",
    }
)
_ANALYSIS_FIELDS = frozenset(
    {
        "mode",
        "perceptible_foreground_pixels",
        "significant_component_areas",
        "selected_assignment_cost",
        "alternative_assignment_cost",
        "assignment_relative_margin",
    }
)


def default_split_component_policy() -> dict[str, int | float]:
    """Return a fresh canonical policy object suitable for provenance JSON."""

    return {
        "perceptible_alpha_threshold": 16,
        "significant_min_area": 16,
        "significant_min_area_ratio": 0.001,
        "pair_min_component_ratio": 0.05,
        "pair_min_coverage_ratio": 0.99,
        "assignment_min_relative_margin": 0.05,
        "fused_endpoint_min_px": 2.0,
        "fused_endpoint_bbox_ratio": 0.05,
        "fused_min_side_pixel_ratio": 0.05,
    }


def normalize_split_component_policy(value: Any) -> dict[str, int | float]:
    """Validate a replay policy without silently filling or coercing fields."""

    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise ValueError("split component policy fields are invalid")
    alpha = _integer(
        value["perceptible_alpha_threshold"], 1, 255, "perceptible alpha threshold"
    )
    area = _integer(
        value["significant_min_area"], 1, MAX_RGBA_PIXELS, "significant minimum area"
    )
    result: dict[str, int | float] = {
        "perceptible_alpha_threshold": alpha,
        "significant_min_area": area,
    }
    for field in (
        "significant_min_area_ratio",
        "pair_min_component_ratio",
        "pair_min_coverage_ratio",
        "assignment_min_relative_margin",
        "fused_endpoint_bbox_ratio",
        "fused_min_side_pixel_ratio",
    ):
        result[field] = _ratio(value[field], field.replace("_", " "))
    result["fused_endpoint_min_px"] = _nonnegative(
        value["fused_endpoint_min_px"], "fused endpoint minimum"
    )
    return result


def normalize_split_component_analysis(value: Any) -> dict[str, object]:
    """Validate the deterministic evidence emitted by one v1.2 run."""

    if not isinstance(value, Mapping) or set(value) != _ANALYSIS_FIELDS:
        raise ValueError("split component analysis fields are invalid")
    mode = value["mode"]
    lengths = {"verified_fused_pixel_fallback": 1, "component_pair": 2}
    if not isinstance(mode, str) or mode not in lengths:
        raise ValueError("split component analysis mode is invalid")
    foreground = _integer(
        value["perceptible_foreground_pixels"],
        1,
        MAX_RGBA_PIXELS,
        "perceptible foreground pixels",
    )
    areas = value["significant_component_areas"]
    if (
        not isinstance(areas, list)
        or len(areas) != lengths[mode]
        or any(
            not isinstance(area, int) or isinstance(area, bool) or area < 1
            for area in areas
        )
        or sum(areas) > foreground
    ):
        raise ValueError("significant component areas are invalid")
    cost_fields = (
        "selected_assignment_cost",
        "alternative_assignment_cost",
        "assignment_relative_margin",
    )
    if mode == "verified_fused_pixel_fallback":
        if any(value[field] is not None for field in cost_fields):
            raise ValueError("fused component analysis cannot claim pair costs")
        costs: tuple[float | None, ...] = (None, None, None)
    else:
        selected = _nonnegative(value[cost_fields[0]], "selected assignment cost")
        alternative = _nonnegative(value[cost_fields[1]], "alternative assignment cost")
        margin = _ratio(value[cost_fields[2]], "assignment relative margin")
        expected = round((alternative - selected) / max(alternative, 1.0), 12)
        if selected > alternative or margin != expected:
            raise ValueError("pair assignment costs and margin are inconsistent")
        costs = (selected, alternative, margin)
    return {
        "mode": mode,
        "perceptible_foreground_pixels": foreground,
        "significant_component_areas": list(areas),
        "selected_assignment_cost": costs[0],
        "alternative_assignment_cost": costs[1],
        "assignment_relative_margin": costs[2],
    }


def _integer(value: Any, minimum: int, maximum: int, label: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _ratio(value: Any, label: str) -> float:
    number = _number(value, label)
    if not 0 <= number <= 1:
        raise ValueError(f"{label} must be in [0, 1]")
    return number


def _nonnegative(value: Any, label: str) -> float:
    number = _number(value, label)
    if number < 0:
        raise ValueError(f"{label} must be nonnegative")
    return number


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be finite")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number
