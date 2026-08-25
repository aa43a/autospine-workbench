"""Deterministic contact evidence from inclusive canvas-space alpha RLE."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Sequence

from .alpha_geometry import AlphaGeometry
from .contact_statistics import ContactEvidence, gap_evidence, overlap_evidence, round6


CanvasRun = tuple[int, int, int]
MAX_GAP_PX = 256.0


@dataclass(frozen=True, slots=True)
class ContactAnalysis:
    contacts: tuple[ContactEvidence, ...]
    qa_flags: tuple[str, ...]
    min_lobe_area: int


@dataclass(frozen=True, slots=True)
class _Segment:
    y: int
    x0: int
    x1: int
    label: int


def contact_between_alpha(
    alpha_a: AlphaGeometry, alpha_b: AlphaGeometry, *,
    component_id_a: int | None = None,
    component_id_b: int | None = None,
    max_gap: float = 0.0,
) -> ContactAnalysis:
    """Analyze contact between two alpha masks without exposing private runs."""
    return contact_between_runs(
        alpha_a.canvas_runs(component_id_a), alpha_b.canvas_runs(component_id_b), max_gap=max_gap
    )


def intersect_canvas_runs(runs_a: Sequence[CanvasRun], runs_b: Sequence[CanvasRun]) -> tuple[CanvasRun, ...]:
    """Return the exact intersection of canonical y-sorted inclusive runs."""
    return _intersect(_validate_runs(runs_a), _validate_runs(runs_b))


def contact_between_runs(
    runs_a: Sequence[CanvasRun], runs_b: Sequence[CanvasRun], *, max_gap: float = 0.0
) -> ContactAnalysis:
    """Build significant 8-connected contact lobes or one bounded gap contact.

    Overlap is O(Ra + Rb + K alpha(K)). Gap search is bounded to at most
    ``2 * MAX_GAP_PX + 1`` opposing rows per source row.
    """
    if (
        not isinstance(max_gap, (int, float)) or isinstance(max_gap, bool)
        or not math.isfinite(max_gap)
        or not 0 <= max_gap <= MAX_GAP_PX
    ):
        raise ValueError(f"max_gap must be finite and lie in [0, {MAX_GAP_PX:g}]")
    left, right = _validate_runs(runs_a), _validate_runs(runs_b)
    area_a, area_b = _run_area(left), _run_area(right)
    threshold = max(16, math.ceil(min(area_a, area_b) * 0.001))
    overlap = _intersect(left, right)
    if overlap:
        contacts = _overlap_contacts(overlap, area_a, area_b, threshold)
        flags = () if contacts else ("CONTACT_OVERLAP_BELOW_THRESHOLD",)
        return ContactAnalysis(contacts, flags, threshold)
    if not left or not right:
        return ContactAnalysis((), ("CONTACT_MASK_EMPTY",), threshold)
    nearest = _nearest_points(left, right, float(max_gap))
    if nearest is None:
        return ContactAnalysis((), ("CONTACT_GAP_TOO_LARGE",), threshold)
    point_a, point_b, distance = nearest
    return ContactAnalysis((gap_evidence(point_a, point_b, distance),), (), threshold)


def _validate_runs(value: Sequence[CanvasRun]) -> tuple[CanvasRun, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("runs must be a sequence")
    result: list[CanvasRun] = []
    previous: CanvasRun | None = None
    for raw in value:
        if (
            not isinstance(raw, (tuple, list)) or len(raw) != 3
            or any(not isinstance(item, int) or isinstance(item, bool) for item in raw)
        ):
            raise ValueError("each run must be integer (y, x0, x1)")
        run = (raw[0], raw[1], raw[2])
        if run[1] > run[2]:
            raise ValueError("run x0 must not exceed x1")
        if previous is not None:
            if run[0] < previous[0] or (run[0] == previous[0] and run[1] <= previous[2] + 1):
                raise ValueError("runs must be y-sorted, disjoint, and maximally merged")
        result.append(run)
        previous = run
    return tuple(result)


def _intersect(left: tuple[CanvasRun, ...], right: tuple[CanvasRun, ...]) -> tuple[CanvasRun, ...]:
    result: list[CanvasRun] = []
    i = j = 0
    while i < len(left) and j < len(right):
        ay, a0, a1 = left[i]
        by, b0, b1 = right[j]
        if ay < by or (ay == by and a1 < b0):
            i += 1
        elif by < ay or b1 < a0:
            j += 1
        else:
            result.append((ay, max(a0, b0), min(a1, b1)))
            if a1 <= b1:
                i += 1
            if b1 <= a1:
                j += 1
    return tuple(result)


def _overlap_contacts(
    runs: tuple[CanvasRun, ...], area_a: int, area_b: int, threshold: int
) -> tuple[ContactEvidence, ...]:
    segments = tuple(_Segment(y, x0, x1, index) for index, (y, x0, x1) in enumerate(runs))
    parents = list(range(len(segments)))
    previous: list[_Segment] = []
    cursor = 0
    while cursor < len(segments):
        y = segments[cursor].y
        end = cursor + 1
        while end < len(segments) and segments[end].y == y:
            end += 1
        current = list(segments[cursor:end])
        if previous and previous[0].y == y - 1:
            prior_index = 0
            for item in current:
                while prior_index < len(previous) and previous[prior_index].x1 < item.x0 - 1:
                    prior_index += 1
                scan = prior_index
                while scan < len(previous) and previous[scan].x0 <= item.x1 + 1:
                    _union(parents, item.label, previous[scan].label)
                    scan += 1
        previous = current
        cursor = end
    members: dict[int, list[_Segment]] = {}
    for item in segments:
        members.setdefault(_root(parents, item.label), []).append(item)
    contacts = [
        overlap_evidence(tuple((item.y, item.x0, item.x1) for item in items), area_a, area_b)
        for items in members.values()
    ]
    contacts = [item for item in contacts if item.area >= threshold]
    contacts.sort(key=lambda item: (-item.area, item.bbox_xywh, item.representative_xy))
    return tuple(replace(item, id=f"overlap.{index:03d}") for index, item in enumerate(contacts))


def _nearest_points(
    left: tuple[CanvasRun, ...], right: tuple[CanvasRun, ...], max_gap: float
) -> tuple[tuple[float, float], tuple[float, float], float] | None:
    best: tuple[float, int, int, int, int] | None = None
    right_rows = _group_rows(right)
    first_right = 0
    for ay, intervals_a in _group_rows(left):
        while first_right < len(right_rows) and right_rows[first_right][0] < ay - max_gap:
            first_right += 1
        row_index = first_right
        while row_index < len(right_rows) and right_rows[row_index][0] <= ay + max_gap:
            by, intervals_b = right_rows[row_index]
            ax, bx, distance_x = _closest_intervals(intervals_a, intervals_b)
            distance_sq = distance_x * distance_x + (ay - by) ** 2
            ranking = (distance_sq, ay, ax, by, bx)
            if distance_sq <= max_gap * max_gap and (best is None or ranking < best):
                best = ranking
            row_index += 1
    if best is None:
        return None
    distance_sq, ay, ax, by, bx = best
    return (float(ax), float(ay)), (float(bx), float(by)), round6(math.sqrt(distance_sq))


def _group_rows(runs: tuple[CanvasRun, ...]) -> list[tuple[int, tuple[tuple[int, int], ...]]]:
    rows: list[tuple[int, tuple[tuple[int, int], ...]]] = []
    start = 0
    while start < len(runs):
        y, _, _ = runs[start]
        end = start + 1
        while end < len(runs) and runs[end][0] == y:
            end += 1
        rows.append((y, tuple((x0, x1) for _, x0, x1 in runs[start:end])))
        start = end
    return rows


def _closest_intervals(
    left: tuple[tuple[int, int], ...], right: tuple[tuple[int, int], ...]
) -> tuple[int, int, int]:
    best: tuple[int, int, int] | None = None
    i = j = 0
    while i < len(left) and j < len(right):
        a0, a1 = left[i]
        b0, b1 = right[j]
        if a1 < b0:
            candidate = (b0 - a1, a1, b0)
            i += 1
        elif b1 < a0:
            candidate = (a0 - b1, a0, b1)
            j += 1
        else:
            x = max(a0, b0)
            return x, x, 0
        if best is None or candidate < best:
            best = candidate
    assert best is not None
    return best[1], best[2], best[0]


def _run_area(runs: tuple[CanvasRun, ...]) -> int:
    return sum(x1 - x0 + 1 for _, x0, x1 in runs)


def _root(parents: list[int], label: int) -> int:
    while parents[label] != label:
        parents[label] = parents[parents[label]]
        label = parents[label]
    return label


def _union(parents: list[int], left: int, right: int) -> None:
    a, b = _root(parents, left), _root(parents, right)
    if a != b:
        parents[max(a, b)] = min(a, b)
