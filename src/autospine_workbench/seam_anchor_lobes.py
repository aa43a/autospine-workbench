"""Recover the exact common-alpha lobe sealed by contact evidence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .contact_geometry import CanvasRun, intersect_canvas_runs
from .contact_statistics import ContactEvidence
from .seam_anchor_sampling import (
    MAX_INTERSECTION_RUNS,
    MAX_RUNS_PER_MASK,
)


class SeamAnchorLobeError(ValueError):
    """Raised when overlap evidence cannot be reconciled with exact runs."""


LOBE_CONNECTIVITY = 8
LOBE_IDENTITY_PROFILE = "unique-area-bbox-8-connected-v1"


@dataclass(frozen=True, slots=True)
class _Segment:
    y: int
    x0: int
    x1: int
    label: int


def isolate_overlap_lobe_runs(
    runs_a: Sequence[CanvasRun],
    runs_b: Sequence[CanvasRun],
    evidence: ContactEvidence,
) -> tuple[CanvasRun, ...]:
    """Return only the 8-connected lobe named by one overlap statistic."""

    if LOBE_IDENTITY_PROFILE != "unique-area-bbox-8-connected-v1":
        raise SeamAnchorLobeError("Overlap lobe identity profile is unsupported")

    if not isinstance(evidence, ContactEvidence) \
            or evidence.mode != "overlap" \
            or type(evidence.area) is not int or evidence.area < 1:
        raise SeamAnchorLobeError("Overlap contact evidence is invalid")
    if len(runs_a) > MAX_RUNS_PER_MASK or len(runs_b) > MAX_RUNS_PER_MASK:
        raise SeamAnchorLobeError("Overlap lobe run budget exceeded")
    try:
        common = intersect_canvas_runs(runs_a, runs_b)
    except ValueError as exc:
        raise SeamAnchorLobeError(str(exc)) from exc
    if len(common) > MAX_INTERSECTION_RUNS:
        raise SeamAnchorLobeError("Overlap lobe run budget exceeded")
    cropped = _crop(common, evidence.bbox_xywh)
    matches = [
        rows for rows in _components(cropped)
        if _area(rows) == evidence.area
        and _bbox(rows) == evidence.bbox_xywh
    ]
    if len(matches) != 1:
        raise SeamAnchorLobeError(
            "Overlap contact does not identify exactly one alpha lobe"
        )
    return matches[0]


def _crop(
    runs: Sequence[CanvasRun], bbox: tuple[int, int, int, int]
) -> tuple[CanvasRun, ...]:
    if not isinstance(bbox, tuple) or len(bbox) != 4 \
            or any(type(item) is not int for item in bbox):
        raise SeamAnchorLobeError("Overlap lobe bbox is invalid")
    left, top, width, height = bbox
    if width < 1 or height < 1:
        raise SeamAnchorLobeError("Overlap lobe bbox is invalid")
    right, bottom = left + width - 1, top + height - 1
    result = []
    for y, x0, x1 in runs:
        if top <= y <= bottom and max(left, x0) <= min(right, x1):
            result.append((y, max(left, x0), min(right, x1)))
    return tuple(result)


def _components(runs: tuple[CanvasRun, ...]) -> tuple[tuple[CanvasRun, ...], ...]:
    if LOBE_CONNECTIVITY not in (4, 8):
        raise SeamAnchorLobeError("Overlap lobe connectivity must be 4 or 8")
    margin = 1 if LOBE_CONNECTIVITY == 8 else 0
    segments = tuple(
        _Segment(y, x0, x1, index)
        for index, (y, x0, x1) in enumerate(runs)
    )
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
            prior = 0
            for item in current:
                while prior < len(previous) \
                        and previous[prior].x1 < item.x0 - margin:
                    prior += 1
                scan = prior
                while scan < len(previous) \
                        and previous[scan].x0 <= item.x1 + margin:
                    _union(parents, item.label, previous[scan].label)
                    scan += 1
        previous = current
        cursor = end
    members: dict[int, list[CanvasRun]] = {}
    for item in segments:
        members.setdefault(_root(parents, item.label), []).append(
            (item.y, item.x0, item.x1)
        )
    return tuple(tuple(rows) for _, rows in sorted(
        members.items(), key=lambda item: _component_key(tuple(item[1]))
    ))


def _component_key(runs: tuple[CanvasRun, ...]):
    return -_area(runs), _bbox(runs), runs


def _area(runs: Sequence[CanvasRun]) -> int:
    return sum(x1 - x0 + 1 for _, x0, x1 in runs)


def _bbox(runs: Sequence[CanvasRun]) -> tuple[int, int, int, int]:
    if not runs:
        raise SeamAnchorLobeError("Overlap lobe is empty")
    left, right = min(row[1] for row in runs), max(row[2] for row in runs)
    top, bottom = min(row[0] for row in runs), max(row[0] for row in runs)
    return left, top, right - left + 1, bottom - top + 1


def _root(parents: list[int], label: int) -> int:
    while parents[label] != label:
        parents[label] = parents[parents[label]]
        label = parents[label]
    return label


def _union(parents: list[int], left: int, right: int) -> None:
    a, b = _root(parents, left), _root(parents, right)
    if a != b:
        parents[max(a, b)] = min(a, b)
