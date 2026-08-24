"""Run-length alpha masks and deterministic 8-connected component evidence."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

from .png_rgba import read_rgba_png


@dataclass(frozen=True, slots=True)
class AlphaComponent:
    component_id: int
    area: int
    area_ratio: float
    bbox_xywh: tuple[int, int, int, int]
    centroid_xy: tuple[float, float]


@dataclass(frozen=True, slots=True)
class AlphaHit:
    xy: tuple[float, float]
    distance_px: float
    component_id: int
    component_area: int
    component_area_ratio: float


@dataclass(frozen=True, slots=True)
class _Run:
    y: int
    start: int
    end: int
    label: int


class AlphaGeometry:
    def __init__(
        self,
        *,
        width: int,
        height: int,
        offset_xy: tuple[int, int],
        threshold: int,
        runs: tuple[_Run, ...],
        components: tuple[AlphaComponent, ...],
    ) -> None:
        self.width = width
        self.height = height
        self.offset_xy = offset_xy
        self.threshold = threshold
        self._runs = runs
        self.components = components
        self.foreground_area = sum(component.area for component in components)
        self._component_by_id = {item.component_id: item for item in components}

    def significant_component_ids(
        self, *, min_area: int = 16, min_area_ratio: float = 0.001
    ) -> frozenset[int]:
        threshold = max(int(min_area), math.ceil(self.foreground_area * min_area_ratio))
        return frozenset(item.component_id for item in self.components if item.area >= threshold)

    def nearest_foreground(
        self,
        x: float,
        y: float,
        *,
        component_ids: frozenset[int] | None = None,
    ) -> AlphaHit | None:
        allowed = component_ids
        offset_x, offset_y = self.offset_xy
        best: tuple[float, int, int, float, float] | None = None
        for run in self._runs:
            if allowed is not None and run.label not in allowed:
                continue
            canvas_y = run.y + offset_y
            canvas_x = min(max(x, run.start + offset_x), run.end + offset_x)
            distance_sq = (canvas_x - x) ** 2 + (canvas_y - y) ** 2
            component = self._component_by_id[run.label]
            ranking = (distance_sq, -component.area, component.component_id, canvas_x, canvas_y)
            if best is None or ranking < best:
                best = ranking
        if best is None:
            return None
        distance_sq, _, component_id, canvas_x, canvas_y = best
        component = self._component_by_id[component_id]
        return AlphaHit(
            xy=(float(canvas_x), float(canvas_y)),
            distance_px=math.sqrt(distance_sq),
            component_id=component_id,
            component_area=component.area,
            component_area_ratio=component.area_ratio,
        )


def analyze_alpha_png(
    path: Path,
    *,
    canvas_offset_xy: tuple[int, int] = (0, 0),
    threshold: int = 8,
) -> AlphaGeometry:
    if not isinstance(threshold, int) or isinstance(threshold, bool) or not 1 <= threshold <= 255:
        raise ValueError("alpha threshold must be an integer in [1, 255]")
    if (
        not isinstance(canvas_offset_xy, tuple)
        or len(canvas_offset_xy) != 2
        or any(not isinstance(value, int) or isinstance(value, bool) for value in canvas_offset_xy)
    ):
        raise ValueError("canvas offset must be a pair of integers")
    image = read_rgba_png(Path(path))
    raw_runs, parents = _scan_runs(image.width, image.height, image.pixels, threshold)
    return _materialize(
        image.width,
        image.height,
        canvas_offset_xy,
        threshold,
        raw_runs,
        parents,
    )


def _scan_runs(
    width: int, height: int, pixels: bytes, threshold: int
) -> tuple[list[_Run], list[int]]:
    all_runs: list[_Run] = []
    parents: list[int] = []
    previous: list[_Run] = []
    for y in range(height):
        current: list[_Run] = []
        x = 0
        while x < width:
            while x < width and pixels[(y * width + x) * 4 + 3] < threshold:
                x += 1
            if x >= width:
                break
            start = x
            while x + 1 < width and pixels[(y * width + x + 1) * 4 + 3] >= threshold:
                x += 1
            label = len(parents)
            parents.append(label)
            run = _Run(y, start, x, label)
            for prior in previous:
                if prior.end < start - 1:
                    continue
                if prior.start > x + 1:
                    break
                _union(parents, label, prior.label)
            current.append(run)
            all_runs.append(run)
            x += 1
        previous = current
    return all_runs, parents


def _root(parents: list[int], label: int) -> int:
    while parents[label] != label:
        parents[label] = parents[parents[label]]
        label = parents[label]
    return label


def _union(parents: list[int], left: int, right: int) -> None:
    left_root, right_root = _root(parents, left), _root(parents, right)
    if left_root != right_root:
        parents[max(left_root, right_root)] = min(left_root, right_root)


def _materialize(
    width: int,
    height: int,
    offset_xy: tuple[int, int],
    threshold: int,
    raw_runs: list[_Run],
    parents: list[int],
) -> AlphaGeometry:
    stats: dict[int, list[int]] = {}
    for run in raw_runs:
        root = _root(parents, run.label)
        area = run.end - run.start + 1
        sum_x = (run.start + run.end) * area // 2
        values = stats.setdefault(root, [0, 0, 0, run.start, run.y, run.end, run.y])
        values[0] += area
        values[1] += sum_x
        values[2] += run.y * area
        values[3] = min(values[3], run.start)
        values[4] = min(values[4], run.y)
        values[5] = max(values[5], run.end)
        values[6] = max(values[6], run.y)
    ordered = sorted(stats, key=lambda root: (-stats[root][0], stats[root][4], stats[root][3]))
    component_ids = {root: index for index, root in enumerate(ordered)}
    total = sum(values[0] for values in stats.values())
    offset_x, offset_y = offset_xy
    components: list[AlphaComponent] = []
    for root in ordered:
        area, sum_x, sum_y, left, top, right, bottom = stats[root]
        components.append(
            AlphaComponent(
                component_id=component_ids[root],
                area=area,
                area_ratio=round(area / total, 8),
                bbox_xywh=(
                    left + offset_x,
                    top + offset_y,
                    right - left + 1,
                    bottom - top + 1,
                ),
                centroid_xy=(sum_x / area + offset_x, sum_y / area + offset_y),
            )
        )
    runs = tuple(
        _Run(run.y, run.start, run.end, component_ids[_root(parents, run.label)])
        for run in raw_runs
    )
    return AlphaGeometry(
        width=width,
        height=height,
        offset_xy=offset_xy,
        threshold=threshold,
        runs=runs,
        components=tuple(components),
    )
