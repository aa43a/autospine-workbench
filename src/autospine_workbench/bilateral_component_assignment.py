"""Reliable component-level assignment for bilateral alpha split v1.2."""

from __future__ import annotations

from array import array
from dataclasses import dataclass
import math
from typing import Iterator, Mapping

from .alpha_geometry import AlphaComponent, AlphaGeometry, analyze_alpha_image
from .png_rgba import RgbaImage
from .polyline_distance import Segment, squared_distance_to_polyline


class ComponentAssignmentError(ValueError):
    """Raised when component evidence cannot support a safe bilateral split."""


MAX_COMPONENT_PROPAGATION_PIXELS = 4_194_304
"""Maximum crop area for the two bounded residual distance transforms."""


@dataclass(frozen=True, slots=True)
class ComponentAssignment:
    """One side code per source pixel: 1 is left and 2 is right."""

    sides: bytearray | None
    guide_tie_pixels: int
    analysis: dict[str, object]


@dataclass(frozen=True, slots=True)
class _Stats:
    left_cost: float
    right_cost: float
    left_pixels: int
    right_pixels: int


def assign_component_sides(
    image: RgbaImage,
    *,
    canvas_offset_xy: tuple[int, int],
    left_points: tuple[tuple[float, float], ...],
    right_points: tuple[tuple[float, float], ...],
    left_segments: tuple[Segment, ...],
    right_segments: tuple[Segment, ...],
    policy: Mapping[str, int | float],
) -> ComponentAssignment:
    """Return a cohesive pair assignment or an audited verified-fusion plan."""

    try:
        geometry = analyze_alpha_image(
            image,
            canvas_offset_xy=canvas_offset_xy,
            threshold=int(policy["perceptible_alpha_threshold"]),
        )
    except ValueError as exc:
        raise ComponentAssignmentError(str(exc)) from exc
    significant_ids = sorted(
        geometry.significant_component_ids(
            min_area=int(policy["significant_min_area"]),
            min_area_ratio=float(policy["significant_min_area_ratio"]),
        )
    )
    if not significant_ids:
        raise ComponentAssignmentError("split has no significant perceptible component")
    stats = _component_stats(
        geometry, frozenset(significant_ids), left_segments, right_segments
    )
    if len(significant_ids) == 1:
        _require_verified_fusion(
            geometry,
            significant_ids[0],
            stats[significant_ids[0]],
            left_points[-1],
            right_points[-1],
            policy,
        )
        component = next(
            item for item in geometry.components if item.component_id == significant_ids[0]
        )
        return ComponentAssignment(
            None,
            0,
            _analysis(geometry, [component], mode="verified_fused_pixel_fallback"),
        )
    if len(significant_ids) != 2:
        raise ComponentAssignmentError("split needs one fused core or two significant cores")
    components = {item.component_id: item for item in geometry.components}
    _require_reliable_pair(geometry, significant_ids, components, policy)
    side_by_component, costs = _assign_pair(significant_ids, stats, policy)
    analysis = _analysis(
        geometry,
        [components[item] for item in significant_ids],
        mode="component_pair",
        costs=costs,
    )
    return _materialize_sides(
        image,
        geometry,
        side_by_component,
        left_segments,
        right_segments,
        analysis,
    )


def _component_stats(
    geometry: AlphaGeometry,
    significant_ids: frozenset[int],
    left_segments: tuple[Segment, ...],
    right_segments: tuple[Segment, ...],
) -> dict[int, _Stats]:
    areas = {item.component_id: item.area for item in geometry.components}
    result: dict[int, _Stats] = {}
    for component_id in significant_ids:
        left_pixels = right_pixels = 0
        for left, right in _paired_distances(
            geometry, component_id, left_segments, right_segments
        ):
            if left <= right:
                left_pixels += 1
            else:
                right_pixels += 1
        area = areas[component_id]
        result[component_id] = _Stats(
            left_cost=math.fsum(
                _distances(geometry, component_id, left_segments)
            ) / area,
            right_cost=math.fsum(
                _distances(geometry, component_id, right_segments)
            ) / area,
            left_pixels=left_pixels,
            right_pixels=right_pixels,
        )
    return result


def _distances(
    geometry: AlphaGeometry,
    component_id: int,
    segments: tuple[Segment, ...],
) -> Iterator[float]:
    for current_id, y, start, end in geometry.iter_labeled_canvas_runs():
        if current_id == component_id:
            for x in range(start, end + 1):
                yield squared_distance_to_polyline(x, y, segments)


def _paired_distances(
    geometry: AlphaGeometry,
    component_id: int,
    left_segments: tuple[Segment, ...],
    right_segments: tuple[Segment, ...],
) -> Iterator[tuple[float, float]]:
    for current_id, y, start, end in geometry.iter_labeled_canvas_runs():
        if current_id == component_id:
            for x in range(start, end + 1):
                yield (
                    squared_distance_to_polyline(x, y, left_segments),
                    squared_distance_to_polyline(x, y, right_segments),
                )


def _require_verified_fusion(
    geometry: AlphaGeometry,
    component_id: int,
    stats: _Stats,
    left_endpoint: tuple[float, float],
    right_endpoint: tuple[float, float],
    policy: Mapping[str, int | float],
) -> None:
    component = next(item for item in geometry.components if item.component_id == component_id)
    _, _, width, height = component.bbox_xywh
    limit = max(
        float(policy["fused_endpoint_min_px"]),
        math.hypot(width, height) * float(policy["fused_endpoint_bbox_ratio"]),
    )
    allowed = frozenset({component_id})
    distances = (
        geometry.nearest_foreground(*left_endpoint, component_ids=allowed),
        geometry.nearest_foreground(*right_endpoint, component_ids=allowed),
    )
    if any(hit is None or hit.distance_px > limit for hit in distances):
        raise ComponentAssignmentError("single core is not reached by both distal guides")
    minimum = float(policy["fused_min_side_pixel_ratio"])
    if min(stats.left_pixels, stats.right_pixels) / component.area < minimum:
        raise ComponentAssignmentError("single core has no reliable bilateral pixel coverage")


def _require_reliable_pair(
    geometry: AlphaGeometry,
    component_ids: list[int],
    components: Mapping[int, AlphaComponent],
    policy: Mapping[str, int | float],
) -> None:
    total = geometry.foreground_area
    areas = [components[component_id].area for component_id in component_ids]
    if any(area / total < float(policy["pair_min_component_ratio"]) for area in areas):
        raise ComponentAssignmentError("significant core is too small for a bilateral pair")
    if sum(areas) / total < float(policy["pair_min_coverage_ratio"]):
        raise ComponentAssignmentError("bilateral core pair has insufficient coverage")


def _assign_pair(
    component_ids: list[int],
    stats: Mapping[int, _Stats],
    policy: Mapping[str, int | float],
) -> tuple[dict[int, int], tuple[float, float]]:
    first, second = component_ids
    candidates = [
        (stats[first].left_cost + stats[second].right_cost, first, second),
        (stats[second].left_cost + stats[first].right_cost, second, first),
    ]
    candidates.sort()
    best, alternative = candidates
    margin = (alternative[0] - best[0]) / max(alternative[0], 1.0)
    if alternative[0] <= best[0] or margin < float(
        policy["assignment_min_relative_margin"]
    ):
        raise ComponentAssignmentError("bilateral component assignment is ambiguous")
    return {best[1]: 1, best[2]: 2}, (best[0], alternative[0])


def _analysis(
    geometry: AlphaGeometry,
    components: list[AlphaComponent],
    *,
    mode: str,
    costs: tuple[float, float] | None = None,
) -> dict[str, object]:
    selected = round(costs[0], 12) if costs else None
    alternative = round(costs[1], 12) if costs else None
    margin = (
        round((alternative - selected) / max(alternative, 1.0), 12)
        if selected is not None and alternative is not None
        else None
    )
    return {
        "mode": mode,
        "perceptible_foreground_pixels": geometry.foreground_area,
        "significant_component_areas": [item.area for item in components],
        "selected_assignment_cost": selected,
        "alternative_assignment_cost": alternative,
        "assignment_relative_margin": margin,
    }


def _materialize_sides(
    image: RgbaImage,
    geometry: AlphaGeometry,
    side_by_component: Mapping[int, int],
    left_segments: tuple[Segment, ...],
    right_segments: tuple[Segment, ...],
    analysis: dict[str, object],
) -> ComponentAssignment:
    if image.width * image.height > MAX_COMPONENT_PROPAGATION_PIXELS:
        raise ComponentAssignmentError(
            f"component propagation exceeds {MAX_COMPONENT_PROPAGATION_PIXELS} pixels"
        )
    sides = bytearray(image.width * image.height)
    offset_x, offset_y = geometry.offset_xy
    for component_id, y, start, end in geometry.iter_labeled_canvas_runs():
        side = side_by_component.get(component_id)
        if side is None:
            continue
        row = (y - offset_y) * image.width
        for x in range(start, end + 1):
            sides[row + x - offset_x] = side
    left_core_distance = _chessboard_distances(image.width, image.height, sides, 1)
    right_core_distance = _chessboard_distances(image.width, image.height, sides, 2)
    _attach_minor_components(
        geometry,
        side_by_component,
        sides,
        left_core_distance,
        right_core_distance,
        left_segments,
        right_segments,
    )
    ties = 0
    for index in range(image.width * image.height):
        if image.pixels[index * 4 + 3] == 0:
            continue
        x, y = offset_x + index % image.width, offset_y + index // image.width
        left_guide = squared_distance_to_polyline(x, y, left_segments)
        right_guide = squared_distance_to_polyline(x, y, right_segments)
        ties += left_guide == right_guide
        if sides[index]:
            continue
        left_core = left_core_distance[index]
        right_core = right_core_distance[index]
        if left_core == right_core:
            sides[index] = 1 if left_guide <= right_guide else 2
        else:
            sides[index] = 1 if left_core < right_core else 2
    return ComponentAssignment(sides, ties, analysis)


def _attach_minor_components(
    geometry: AlphaGeometry,
    primary: Mapping[int, int],
    sides: bytearray,
    left_core_distance: array,
    right_core_distance: array,
    left_segments: tuple[Segment, ...],
    right_segments: tuple[Segment, ...],
) -> None:
    """Attach every non-primary perceptible component as one indivisible unit."""

    width = geometry.width
    offset_x, offset_y = geometry.offset_xy
    stats: dict[int, list[float]] = {}
    for component_id, y, start, end in geometry.iter_labeled_canvas_runs():
        if component_id in primary:
            continue
        values = stats.setdefault(component_id, [math.inf, math.inf, 0, 0, 0.0, 0.0])
        row = (y - offset_y) * width
        for x in range(start, end + 1):
            index = row + x - offset_x
            left = left_core_distance[index]
            right = right_core_distance[index]
            values[0] = min(values[0], left)
            values[1] = min(values[1], right)
            values[2] += left
            values[3] += right
            values[4] += squared_distance_to_polyline(x, y, left_segments)
            values[5] += squared_distance_to_polyline(x, y, right_segments)
    attached: dict[int, int] = {}
    for component_id, values in stats.items():
        if values[0] != values[1]:
            attached[component_id] = 1 if values[0] < values[1] else 2
        elif values[2] != values[3]:
            attached[component_id] = 1 if values[2] < values[3] else 2
        else:
            attached[component_id] = 1 if values[4] <= values[5] else 2
    for component_id, y, start, end in geometry.iter_labeled_canvas_runs():
        side = attached.get(component_id)
        if side is None:
            continue
        row = (y - offset_y) * width
        for x in range(start, end + 1):
            sides[row + x - offset_x] = side


def _chessboard_distances(
    width: int, height: int, seeds: bytearray, side: int
) -> array:
    """Exact 8-neighbour grid distance via bounded forward/backward passes."""

    infinity = max(width, height) + 1
    distances = array("I", [infinity]) * (width * height)
    for index, value in enumerate(seeds):
        if value == side:
            distances[index] = 0
    for y in range(height):
        row = y * width
        for x in range(width):
            index = row + x
            best = distances[index]
            if x:
                best = min(best, distances[index - 1] + 1)
            if y:
                best = min(best, distances[index - width] + 1)
                if x:
                    best = min(best, distances[index - width - 1] + 1)
                if x + 1 < width:
                    best = min(best, distances[index - width + 1] + 1)
            distances[index] = best
    for y in range(height - 1, -1, -1):
        row = y * width
        for x in range(width - 1, -1, -1):
            index = row + x
            best = distances[index]
            if x + 1 < width:
                best = min(best, distances[index + 1] + 1)
            if y + 1 < height:
                best = min(best, distances[index + width] + 1)
                if x:
                    best = min(best, distances[index + width - 1] + 1)
                if x + 1 < width:
                    best = min(best, distances[index + width + 1] + 1)
            distances[index] = best
    return distances
