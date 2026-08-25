"""Deterministic fail-closed metrics for indexed mesh deformation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math
from typing import Any, TypeAlias


SETUP_AREA_EPSILON = 1e-12

Point: TypeAlias = tuple[float, float]
Triangle: TypeAlias = tuple[int, int, int]
Edge: TypeAlias = tuple[int, int]


class DeformationMetricsError(ValueError):
    """Raised when inputs do not describe a measurable indexed mesh."""


@dataclass(frozen=True, slots=True)
class DeformationMetrics:
    """Finite metrics, or ``None`` where non-finite input stops measurement."""

    vertex_count: int
    triangle_count: int
    non_finite_count: int
    flipped_count: int
    degenerate_count: int
    min_signed_area_ratio: float | None
    max_signed_area_ratio: float | None
    max_edge_stretch_ratio: float | None
    interior_crack_gap_px: float


@dataclass(frozen=True, slots=True)
class DeformationAssessment:
    """Immutable metrics plus a stable pass/reject decision."""

    metrics: DeformationMetrics
    status: str
    reasons: tuple[str, ...]


def measure_deformation(
    setup_vertices_xy: Sequence[Sequence[int | float]],
    posed_vertices_xy: Sequence[Sequence[int | float]],
    triangles: Sequence[Sequence[int]],
    *,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 20.0,
    max_edge_stretch: float = 3.0,
) -> DeformationAssessment:
    """Measure one shared-index pose against setup geometry.
    Structural contract errors raise :class:`DeformationMetricsError`. Non-finite
    coordinates instead produce a rejected assessment: derived values are ``None``
    and never NaN. Thresholds are strict and conservative: area ratios must lie in
    ``(min_area_ratio, max_area_ratio)`` and edge stretch must be below its limit.
    """

    minimum, maximum, stretch_limit = _thresholds(
        min_area_ratio, max_area_ratio, max_edge_stretch
    )
    setup = _vertices(setup_vertices_xy, "setup")
    posed = _vertices(posed_vertices_xy, "posed")
    if len(setup) != len(posed):
        raise DeformationMetricsError("setup and posed vertex cardinality must match")
    topology, edges = _topology(triangles, len(setup))
    non_finite = _non_finite_coordinates(setup, posed)
    if non_finite:
        return _non_finite_assessment(len(setup), len(topology), non_finite)

    setup_areas = tuple(_signed_area(setup, item) for item in topology)
    setup_edge_lengths = tuple(_edge_length(setup, edge) for edge in edges)
    derived_non_finite = sum(
        not math.isfinite(value)
        for value in (*setup_areas, *setup_edge_lengths)
    )
    if derived_non_finite:
        return _non_finite_assessment(len(setup), len(topology), derived_non_finite)
    for index, area in enumerate(setup_areas):
        if area <= SETUP_AREA_EPSILON:
            raise DeformationMetricsError(
                f"setup triangle {index} must have positive area above epsilon"
            )

    posed_areas = tuple(_signed_area(posed, item) for item in topology)
    posed_edge_lengths = tuple(_edge_length(posed, edge) for edge in edges)
    derived_non_finite = sum(
        not math.isfinite(value)
        for value in (*posed_areas, *posed_edge_lengths)
    )
    if derived_non_finite:
        return _non_finite_assessment(len(setup), len(topology), derived_non_finite)

    ratios = tuple(
        posed_area / setup_area
        for posed_area, setup_area in zip(posed_areas, setup_areas)
    )
    edge_ratios = tuple(
        posed_length / setup_length
        for posed_length, setup_length in zip(
            posed_edge_lengths, setup_edge_lengths
        )
    )
    if any(not math.isfinite(value) for value in (*ratios, *edge_ratios)):
        return _non_finite_assessment(len(setup), len(topology), 1)

    metrics = DeformationMetrics(
        vertex_count=len(setup),
        triangle_count=len(topology),
        non_finite_count=0,
        flipped_count=sum(area <= 0.0 for area in posed_areas),
        degenerate_count=sum(
            abs(area) <= SETUP_AREA_EPSILON for area in posed_areas
        ),
        min_signed_area_ratio=min(ratios),
        max_signed_area_ratio=max(ratios),
        max_edge_stretch_ratio=max(edge_ratios),
        interior_crack_gap_px=0.0,
    )
    reasons = _reasons(metrics, minimum, maximum, stretch_limit)
    return DeformationAssessment(
        metrics=metrics,
        status="rejected" if reasons else "passed",
        reasons=reasons,
    )


def _reasons(metrics, minimum, maximum, stretch_limit) -> tuple[str, ...]:
    reasons: set[str] = set()
    if metrics.flipped_count:
        reasons.add("flipped_triangles")
    if metrics.degenerate_count:
        reasons.add("degenerate_triangles")
    if metrics.min_signed_area_ratio <= minimum:
        reasons.add("minimum_area_ratio")
    if metrics.max_signed_area_ratio >= maximum:
        reasons.add("maximum_area_ratio")
    if metrics.max_edge_stretch_ratio >= stretch_limit:
        reasons.add("maximum_edge_stretch")
    return tuple(sorted(reasons))


def _non_finite_assessment(
    vertex_count: int, triangle_count: int, count: int
) -> DeformationAssessment:
    metrics = DeformationMetrics(
        vertex_count=vertex_count,
        triangle_count=triangle_count,
        non_finite_count=count,
        flipped_count=0,
        degenerate_count=0,
        min_signed_area_ratio=None,
        max_signed_area_ratio=None,
        max_edge_stretch_ratio=None,
        interior_crack_gap_px=0.0,
    )
    return DeformationAssessment(
        metrics=metrics,
        status="rejected",
        reasons=("non_finite",),
    )


def _vertices(value: Any, label: str) -> tuple[Point, ...]:
    if not _sequence(value) or not value:
        raise DeformationMetricsError(f"{label} vertices must be a non-empty array")
    result: list[Point] = []
    for index, point in enumerate(value):
        if not _sequence(point) or len(point) != 2:
            raise DeformationMetricsError(
                f"{label} vertex {index} must contain two coordinates"
            )
        result.append(
            (
                _coordinate(point[0], label, index),
                _coordinate(point[1], label, index),
            )
        )
    return tuple(result)


def _coordinate(value: Any, label: str, index: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DeformationMetricsError(
            f"{label} vertex {index} coordinates must be numeric"
        )
    try:
        return float(value)
    except OverflowError:
        return math.inf


def _topology(
    value: Any, vertex_count: int
) -> tuple[tuple[Triangle, ...], tuple[Edge, ...]]:
    if not _sequence(value) or not value:
        raise DeformationMetricsError("triangles must be a non-empty array")
    result: list[Triangle] = []
    seen: set[tuple[int, int, int]] = set()
    edge_counts: dict[Edge, int] = {}
    for position, raw in enumerate(value):
        if not _sequence(raw) or len(raw) != 3:
            raise DeformationMetricsError(
                f"triangle {position} must contain three indices"
            )
        if any(
            not isinstance(index, int) or isinstance(index, bool)
            for index in raw
        ):
            raise DeformationMetricsError(
                f"triangle {position} indices must be integers"
            )
        triangle = (raw[0], raw[1], raw[2])
        if len(set(triangle)) != 3:
            raise DeformationMetricsError(
                f"triangle {position} indices must be distinct"
            )
        if any(index < 0 or index >= vertex_count for index in triangle):
            raise DeformationMetricsError(
                f"triangle {position} index is outside vertex range"
            )
        canonical = tuple(sorted(triangle))
        if canonical in seen:
            raise DeformationMetricsError(f"duplicate triangle at index {position}")
        seen.add(canonical)
        result.append(triangle)
        for edge in _edges(triangle):
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
            if edge_counts[edge] > 2:
                raise DeformationMetricsError(
                    f"edge {edge} belongs to more than two triangles"
                )
    return tuple(result), tuple(sorted(edge_counts))


def _thresholds(minimum: Any, maximum: Any, stretch: Any) -> tuple[float, ...]:
    values = tuple(_finite_threshold(value) for value in (minimum, maximum, stretch))
    if values[0] < 0.0 or values[1] <= values[0]:
        raise DeformationMetricsError(
            "area ratio thresholds must satisfy 0 <= minimum < maximum"
        )
    if values[2] <= 0.0:
        raise DeformationMetricsError("edge stretch threshold must be positive")
    return values


def _finite_threshold(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DeformationMetricsError("thresholds must be finite numbers")
    try:
        result = float(value)
    except OverflowError as exc:
        raise DeformationMetricsError("thresholds must be finite numbers") from exc
    if not math.isfinite(result):
        raise DeformationMetricsError("thresholds must be finite numbers")
    return result


def _signed_area(vertices: tuple[Point, ...], triangle: Triangle) -> float:
    first, second, third = (vertices[index] for index in triangle)
    return 0.5 * (
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )


def _edge_length(vertices: tuple[Point, ...], edge: Edge) -> float:
    left, right = (vertices[index] for index in edge)
    return math.hypot(right[0] - left[0], right[1] - left[1])


def _edges(triangle: Triangle) -> tuple[Edge, Edge, Edge]:
    first, second, third = triangle
    return tuple(
        (min(left, right), max(left, right))
        for left, right in ((first, second), (second, third), (third, first))
    )  # type: ignore[return-value]


def _non_finite_coordinates(*groups: tuple[Point, ...]) -> int:
    return sum(
        not math.isfinite(coordinate)
        for group in groups
        for point in group
        for coordinate in point
    )


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    )
