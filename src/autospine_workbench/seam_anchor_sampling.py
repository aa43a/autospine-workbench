"""Bounded, deterministic seam-pair sampling from common canvas alpha."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .contact_geometry import CanvasRun, intersect_canvas_runs
from .seam_anchor_locators import make_attachment_locator
from .seam_anchor_pair_validation import (
    MAX_ANCHOR_PAIRS,
    MIN_ANCHOR_PAIRS,
    ResolvedAnchorPair,
    SeamAnchorUnsupportedError,
    validate_anchor_pairs,
)


DEFAULT_ANCHOR_PAIRS = 4
MAX_RUNS_PER_MASK = 8192
MAX_INTERSECTION_RUNS = 16384
MAX_COMMON_ALPHA_PIXELS = 262144
MAX_ABS_CANVAS_COORDINATE = 1_000_000
SAMPLING_PROFILE = "bbox-major-axis-common-alpha-quantiles-v1"


class SeamAnchorSamplingError(ValueError):
    """Raised when sampling inputs violate the pinned contract."""


@dataclass(frozen=True, slots=True)
class SeamAnchorSampling:
    status: str
    reason_code: str | None
    principal_axis: str
    requested_pair_count: int
    canvas_point_pairs_xy: tuple[
        tuple[tuple[float, float], tuple[float, float]], ...
    ]
    sampling_profile: str = SAMPLING_PROFILE


def sample_common_alpha_pairs(
    runs_a: Sequence[CanvasRun],
    runs_b: Sequence[CanvasRun],
    overlap_lobe_bbox_xywh: Sequence[int], *,
    requested_pair_count: int = DEFAULT_ANCHOR_PAIRS,
) -> SeamAnchorSampling:
    """Select common pixel centers at equal quantiles of the bbox major axis.

    Too few major coordinates or an exhausted scan budget returns an explicit,
    fail-closed unavailable reason.
    """

    requested = _pair_count(requested_pair_count)
    bbox = _bbox(overlap_lobe_bbox_xywh)
    axis = "x" if bbox[2] >= bbox[3] else "y"
    if _sequence_size(runs_a, "runs_a") > MAX_RUNS_PER_MASK \
            or _sequence_size(runs_b, "runs_b") > MAX_RUNS_PER_MASK:
        return _unavailable("sampling_budget_exceeded", axis, requested)
    try:
        common = intersect_canvas_runs(runs_a, runs_b)
    except ValueError as exc:
        raise SeamAnchorSamplingError(str(exc)) from exc
    if not common:
        return _unavailable("common_alpha_gap", axis, requested)
    cropped = _crop_runs(common, bbox)
    if not cropped:
        return _unavailable("common_alpha_gap", axis, requested)
    if len(cropped) > MAX_INTERSECTION_RUNS:
        return _unavailable("sampling_budget_exceeded", axis, requested)
    area = sum(x1 - x0 + 1 for _, x0, x1 in cropped)
    if area > MAX_COMMON_ALPHA_PIXELS:
        return _unavailable("sampling_budget_exceeded", axis, requested)
    groups = _major_axis_groups(cropped, axis)
    if len(groups) < MIN_ANCHOR_PAIRS:
        return _unavailable(
            "insufficient_common_alpha_points", axis, requested
        )
    count = min(requested, len(groups), MAX_ANCHOR_PAIRS)
    indices = _equal_quantile_indices(len(groups), count)
    points = tuple(_representative(groups[index], axis) for index in indices)
    return SeamAnchorSampling(
        status="available", reason_code=None, principal_axis=axis,
        requested_pair_count=requested,
        canvas_point_pairs_xy=tuple((point, point) for point in points),
    )


def materialize_sampled_locator_pairs(
    sampling: SeamAnchorSampling,
    attachment_a: Mapping[str, Any],
    attachment_b: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Convert available canvas samples to strict attachment-local locators."""

    if not isinstance(sampling, SeamAnchorSampling) \
            or sampling.status != "available" or sampling.reason_code is not None:
        raise SeamAnchorSamplingError("sampling result is unavailable")
    documents = tuple({
        "pair_id": f"anchor.{index:03d}",
        "a": make_attachment_locator(attachment_a, point_a),
        "b": make_attachment_locator(attachment_b, point_b),
    } for index, (point_a, point_b) in enumerate(
        sampling.canvas_point_pairs_xy
    ))
    validate_anchor_pairs(
        documents, attachment_a, attachment_b,
        principal_axis=sampling.principal_axis,
    )
    return documents


def _crop_runs(
    runs: Sequence[CanvasRun], bbox: tuple[int, int, int, int]
) -> tuple[CanvasRun, ...]:
    left, top, width, height = bbox
    right, bottom = left + width - 1, top + height - 1
    result = []
    for y, x0, x1 in runs:
        if y < top:
            continue
        if y > bottom:
            break
        start, end = max(left, x0), min(right, x1)
        if start <= end:
            result.append((y, start, end))
    return tuple(result)


def _major_axis_groups(
    runs: Sequence[CanvasRun], axis: str
) -> tuple[tuple[int, tuple[int, ...]], ...]:
    values: dict[int, list[int]] = {}
    for y, x0, x1 in runs:
        for x in range(x0, x1 + 1):
            primary, secondary = (x, y) if axis == "x" else (y, x)
            values.setdefault(primary, []).append(secondary)
    return tuple(
        (primary, tuple(sorted(secondary)))
        for primary, secondary in sorted(values.items())
    )


def _representative(
    group: tuple[int, tuple[int, ...]], axis: str
) -> tuple[float, float]:
    primary, secondary = group
    middle = secondary[(len(secondary) - 1) // 2]
    if axis == "x":
        return primary + 0.5, middle + 0.5
    return middle + 0.5, primary + 0.5


def _equal_quantile_indices(population: int, count: int) -> tuple[int, ...]:
    return tuple(
        index * (population - 1) // (count - 1)
        for index in range(count)
    )


def _unavailable(reason, axis, requested):
    return SeamAnchorSampling(
        status="unavailable", reason_code=reason, principal_axis=axis,
        requested_pair_count=requested, canvas_point_pairs_xy=(),
    )


def _bbox(value: Sequence[int]) -> tuple[int, int, int, int]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) \
            or len(value) != 4:
        raise SeamAnchorSamplingError("overlap lobe bbox must be integer xywh")
    if any(not isinstance(item, int) or isinstance(item, bool) for item in value):
        raise SeamAnchorSamplingError("overlap lobe bbox must be integer xywh")
    x, y, width, height = value
    if width < 1 or height < 1:
        raise SeamAnchorSamplingError("overlap lobe bbox extents must be positive")
    if any(abs(item) > MAX_ABS_CANVAS_COORDINATE
           for item in (x, y, x + width - 1, y + height - 1)):
        raise SeamAnchorSamplingError("overlap lobe bbox exceeds coordinate budget")
    return x, y, width, height


def _pair_count(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) \
            or not MIN_ANCHOR_PAIRS <= value <= MAX_ANCHOR_PAIRS:
        raise SeamAnchorSamplingError("requested pair count must lie in [2, 8]")
    return value


def _sequence_size(value: Sequence[CanvasRun], label: str) -> int:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise SeamAnchorSamplingError(f"{label} must be a sequence")
    return len(value)

