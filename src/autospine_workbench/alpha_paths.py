"""Deterministic pose-conditioned paths through one alpha component."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
from statistics import median
from typing import Any, Iterable, Mapping


_ANCHOR_NAMES = ("proximal", "hinge", "distal")
_NEIGHBORS = (
    (-1, -1, 1414), (0, -1, 1000), (1, -1, 1414),
    (-1, 0, 1000), (1, 0, 1000),
    (-1, 1, 1414), (0, 1, 1000), (1, 1, 1414),
)


@dataclass(frozen=True, slots=True)
class AnchorProjection:
    input_xy: tuple[float, float]
    xy: tuple[int, int]
    residual_px: float


@dataclass(frozen=True, slots=True)
class AlphaPathResult:
    polyline_xy: tuple[tuple[int, int], ...]
    projected_anchors: Mapping[str, AnchorProjection]
    length_px: float | None
    min_clearance_px: float | None
    median_clearance_px: float | None
    hinge_candidate_xy: tuple[int, int] | None
    error_radius_px: float | None
    raster_pixels: int
    search_nodes: int
    flags: tuple[str, ...]


def trace_alpha_clearance_path(
    runs: Iterable[Any],
    anchors: Mapping[str, Any],
    *,
    max_raster_pixels: int = 400_000,
    max_search_nodes: int = 250_000,
) -> AlphaPathResult:
    """Trace proximal→hinge→distal while preferring alpha clearance.

    ``runs`` are canvas-space ``(y, start, end)`` triples, mappings, or objects
    exposing those attributes. This is a chamfer-clearance path, not an exact
    Blum medial-axis computation.
    """

    _positive_budget(max_raster_pixels, "max_raster_pixels")
    _positive_budget(max_search_nodes, "max_search_nodes")
    points = _anchors(anchors)
    normalized = _runs(runs)
    base_flags = {"CHAMFER_CLEARANCE_APPROXIMATION"}
    if not normalized:
        return _failure(base_flags | {"EMPTY_ALPHA_MASK"})
    left = min(item[1] for item in normalized)
    right = max(item[2] for item in normalized)
    top = min(item[0] for item in normalized)
    bottom = max(item[0] for item in normalized)
    width, height = right - left + 1, bottom - top + 1
    stride, raster_pixels = width + 2, (width + 2) * (height + 2)
    if raster_pixels > max_raster_pixels:
        return _failure(base_flags | {"RASTER_BUDGET_EXCEEDED"}, raster_pixels=raster_pixels)

    mask = bytearray(raster_pixels)
    for y, start, end in normalized:
        row = (y - top + 1) * stride
        begin, finish = start - left + 1, end - left + 2
        mask[row + begin : row + finish] = b"\x01" * (finish - begin)
    local, projected = _project_anchors(mask, stride, width, height, left, top, points)
    if any(item.residual_px > 0 for item in projected.values()):
        base_flags.add("ANCHORS_PROJECTED_TO_ALPHA")
    clearance = _chamfer_clearance(mask, stride, width, height)

    first, used_first, failure = _astar(
        mask, clearance, stride, local["proximal"], local["hinge"], max_search_nodes
    )
    if failure:
        return _failure(
            base_flags | {failure}, projected, raster_pixels=raster_pixels,
            search_nodes=used_first,
        )
    second, used_second, failure = _astar(
        mask, clearance, stride, local["hinge"], local["distal"],
        max_search_nodes - used_first,
    )
    searched = used_first + used_second
    if failure:
        return _failure(
            base_flags | {failure}, projected, raster_pixels=raster_pixels,
            search_nodes=searched,
        )
    full_path = first + second[1:]
    hinge_index = len(first) - 1
    sampled = _sample_path(full_path, hinge_index)
    if len(sampled) < len(full_path):
        base_flags.add("POLYLINE_DOWNSAMPLED")
    canvas_path = tuple((x - 1 + left, y - 1 + top) for x, y in sampled)
    path_clearance = [clearance[y * stride + x] / 3.0 for x, y in full_path]
    path_length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(full_path, full_path[1:]))
    hinge_local = full_path[hinge_index]
    hinge_xy = (hinge_local[0] - 1 + left, hinge_local[1] - 1 + top)
    hinge_clearance = clearance[hinge_local[1] * stride + hinge_local[0]] / 3.0
    error_radius = max(0.5, projected["hinge"].residual_px, hinge_clearance / 2.0)
    return AlphaPathResult(
        polyline_xy=canvas_path,
        projected_anchors=projected,
        length_px=round(path_length, 4),
        min_clearance_px=round(min(path_clearance), 4),
        median_clearance_px=round(float(median(path_clearance)), 4),
        hinge_candidate_xy=hinge_xy,
        error_radius_px=round(error_radius, 4),
        raster_pixels=raster_pixels,
        search_nodes=searched,
        flags=tuple(sorted(base_flags)),
    )


def _failure(
    flags: set[str],
    projected: Mapping[str, AnchorProjection] | None = None,
    *,
    raster_pixels: int = 0,
    search_nodes: int = 0,
) -> AlphaPathResult:
    return AlphaPathResult(
        (), projected or {}, None, None, None, None, None,
        raster_pixels, search_nodes, tuple(sorted(flags)),
    )


def _positive_budget(value: Any, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _anchors(value: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    if not isinstance(value, Mapping):
        raise ValueError("anchors must be a mapping")
    result: dict[str, tuple[float, float]] = {}
    for name in _ANCHOR_NAMES:
        point = value.get(name)
        if (
            not isinstance(point, (list, tuple)) or len(point) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in point)
        ):
            raise ValueError(f"anchor {name} must contain two finite numbers")
        result[name] = (float(point[0]), float(point[1]))
    return result


def _runs(values: Iterable[Any]) -> list[tuple[int, int, int]]:
    result: list[tuple[int, int, int]] = []
    for item in values:
        if isinstance(item, Mapping):
            triple = (item.get("y"), item.get("start"), item.get("end"))
        elif all(hasattr(item, field) for field in ("y", "start", "end")):
            triple = (item.y, item.start, item.end)
        elif isinstance(item, (list, tuple)) and len(item) >= 3:
            triple = (item[0], item[1], item[2])
        else:
            raise ValueError("each run must provide y, start, and end")
        if any(not isinstance(v, int) or isinstance(v, bool) for v in triple) or triple[1] > triple[2]:
            raise ValueError("run coordinates must be ordered integers")
        result.append(triple)
    return sorted(result)


def _project_anchors(
    mask: bytearray,
    stride: int,
    width: int,
    height: int,
    left: int,
    top: int,
    anchors: Mapping[str, tuple[float, float]],
) -> tuple[dict[str, tuple[int, int]], dict[str, AnchorProjection]]:
    best: dict[str, tuple[float, int, int] | None] = {name: None for name in _ANCHOR_NAMES}
    for y in range(1, height + 1):
        for x in range(1, width + 1):
            if not mask[y * stride + x]:
                continue
            canvas_x, canvas_y = x - 1 + left, y - 1 + top
            for name, anchor in anchors.items():
                rank = ((canvas_x - anchor[0]) ** 2 + (canvas_y - anchor[1]) ** 2, canvas_y, canvas_x)
                if best[name] is None or rank < best[name]:
                    best[name] = rank
    local: dict[str, tuple[int, int]] = {}
    projected: dict[str, AnchorProjection] = {}
    for name in _ANCHOR_NAMES:
        assert best[name] is not None
        distance_sq, canvas_y, canvas_x = best[name]
        local[name] = (canvas_x - left + 1, canvas_y - top + 1)
        projected[name] = AnchorProjection(anchors[name], (canvas_x, canvas_y), round(math.sqrt(distance_sq), 4))
    return local, projected


def _chamfer_clearance(mask: bytearray, stride: int, width: int, height: int) -> list[int]:
    infinity = 65_535
    distance = [infinity if value else 0 for value in mask]
    for y in range(1, height + 1):
        for x in range(1, width + 1):
            index = y * stride + x
            if mask[index]:
                distance[index] = min(
                    distance[index],
                    distance[index - 1] + 3,
                    distance[index - stride] + 3,
                    distance[index - stride - 1] + 4,
                    distance[index - stride + 1] + 4,
                )
    for y in range(height, 0, -1):
        for x in range(width, 0, -1):
            index = y * stride + x
            if mask[index]:
                distance[index] = min(
                    distance[index],
                    distance[index + 1] + 3,
                    distance[index + stride] + 3,
                    distance[index + stride - 1] + 4,
                    distance[index + stride + 1] + 4,
                )
    return distance


def _astar(
    mask: bytearray,
    clearance: list[int],
    stride: int,
    start: tuple[int, int],
    goal: tuple[int, int],
    budget: int,
) -> tuple[tuple[tuple[int, int], ...], int, str | None]:
    if start == goal:
        return (start,), 0, None
    if budget < 1:
        return (), 0, "SEARCH_BUDGET_EXCEEDED"
    start_index, goal_index = start[1] * stride + start[0], goal[1] * stride + goal[0]
    scores = {start_index: 0}
    parents: dict[int, int] = {}
    closed = bytearray(len(mask))
    heap = [(_heuristic(start, goal), 0, start[1], start[0])]
    expanded = 0
    while heap:
        _, score, y, x = heapq.heappop(heap)
        index = y * stride + x
        if closed[index] or scores.get(index) != score:
            continue
        closed[index] = 1
        expanded += 1
        if index == goal_index:
            return _reconstruct(parents, index, start_index, stride), expanded, None
        if expanded >= budget:
            return (), expanded, "SEARCH_BUDGET_EXCEEDED"
        for dx, dy, base_cost in _NEIGHBORS:
            nx, ny = x + dx, y + dy
            neighbor = ny * stride + nx
            if not mask[neighbor] or closed[neighbor]:
                continue
            candidate = score + base_cost + 18_000 // max(clearance[neighbor], 1)
            if candidate >= scores.get(neighbor, 1 << 60):
                continue
            scores[neighbor] = candidate
            parents[neighbor] = index
            heapq.heappush(heap, (candidate + _heuristic((nx, ny), goal), candidate, ny, nx))
    return (), expanded, "ANCHORS_DISCONNECTED"


def _heuristic(point: tuple[int, int], goal: tuple[int, int]) -> int:
    dx, dy = abs(point[0] - goal[0]), abs(point[1] - goal[1])
    return 1000 * max(dx, dy) + 414 * min(dx, dy)


def _reconstruct(parents: Mapping[int, int], index: int, start: int, stride: int) -> tuple[tuple[int, int], ...]:
    reversed_path: list[tuple[int, int]] = []
    while True:
        reversed_path.append((index % stride, index // stride))
        if index == start:
            return tuple(reversed(reversed_path))
        index = parents[index]


def _sample_path(path: tuple[tuple[int, int], ...], hinge_index: int) -> tuple[tuple[int, int], ...]:
    if len(path) <= 128:
        return path
    indices = {0, hinge_index, len(path) - 1}
    for step in range(1, 126):
        indices.add(round(step * (len(path) - 1) / 126))
        if len(indices) == 128:
            break
    return tuple(path[index] for index in sorted(indices))
