"""Bounded, deterministic squared distance to authored polylines."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import math
from typing import Any


MAX_GUIDE_POINTS = 8
"""Maximum anchors per anatomical-side guide at authoring and replay."""


@dataclass(frozen=True, slots=True)
class Segment:
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    delta_x: float
    delta_y: float
    length_squared: float


def normalize_polyline(
    value: Iterable[Sequence[float]], label: str
) -> tuple[tuple[tuple[float, float], ...], tuple[Segment, ...]]:
    if isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} polyline must be an iterable of points")
    try:
        iterator = iter(value)
    except TypeError as exc:
        raise ValueError(f"{label} polyline must be an iterable of points") from exc
    points_list: list[tuple[float, float]] = []
    for index, item in enumerate(iterator):
        if index == MAX_GUIDE_POINTS:
            raise ValueError(f"{label} polyline exceeds {MAX_GUIDE_POINTS} points")
        points_list.append(_point(item, label))
    points = tuple(points_list)
    if len(points) < 2:
        raise ValueError(f"{label} polyline needs at least two points")
    segments: list[Segment] = []
    for start, end in zip(points, points[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length_squared = dx * dx + dy * dy
        if not all(math.isfinite(item) for item in (dx, dy, length_squared)):
            raise ValueError(f"{label} polyline exceeds the finite coordinate range")
        if length_squared == 0:
            raise ValueError(f"{label} polyline has a zero-length segment")
        segments.append(
            Segment(start[0], start[1], end[0], end[1], dx, dy, length_squared)
        )
    return points, tuple(segments)


def squared_distance_to_polyline(
    x: float, y: float, segments: tuple[Segment, ...]
) -> float:
    """Return the nearest squared distance without sqrt or normalized vectors."""

    best = math.inf
    for segment in segments:
        relative_x, relative_y = x - segment.start_x, y - segment.start_y
        projection = relative_x * segment.delta_x + relative_y * segment.delta_y
        if projection <= 0:
            distance = relative_x * relative_x + relative_y * relative_y
        elif projection >= segment.length_squared:
            end_x, end_y = x - segment.end_x, y - segment.end_y
            distance = end_x * end_x + end_y * end_y
        else:
            cross = relative_x * segment.delta_y - relative_y * segment.delta_x
            distance = (cross * cross) / segment.length_squared
        if not math.isfinite(projection) or not math.isfinite(distance):
            raise ValueError("pixel-to-polyline distance is not finite")
        best = min(best, distance)
    return best


def _point(value: Any, label: str) -> tuple[float, float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or len(value) != 2
    ):
        raise ValueError(f"{label} polyline points must contain two numbers")
    numbers: list[float] = []
    for item in value:
        if not isinstance(item, (int, float)) or isinstance(item, bool):
            raise ValueError(f"{label} polyline points must contain two numbers")
        try:
            number = float(item)
        except OverflowError as exc:
            raise ValueError(f"{label} polyline points must be finite") from exc
        if not math.isfinite(number):
            raise ValueError(f"{label} polyline points must be finite")
        numbers.append(number)
    return numbers[0], numbers[1]
