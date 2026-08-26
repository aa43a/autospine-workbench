"""Prepared deformation metrics for repeated body-sway samples."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math
from typing import TypeAlias

from .mesh_deformation_metrics import (
    SETUP_AREA_EPSILON,
    DeformationAssessment,
    DeformationMetrics,
    measure_deformation,
)


Point: TypeAlias = tuple[float, float]
Triangle: TypeAlias = tuple[int, int, int]
Edge: TypeAlias = tuple[int, int]


@dataclass(frozen=True, slots=True)
class PreparedBodySwayDeformation:
    """Immutable setup terms shared by every pose of one exact mesh."""

    setup_vertices_xy: tuple[Point, ...]
    triangles: tuple[Triangle, ...]
    edges: tuple[Edge, ...]
    setup_areas: tuple[float, ...]
    setup_edge_lengths: tuple[float, ...]
    min_area_ratio: float
    max_area_ratio: float
    max_edge_stretch: float


def prepare_body_sway_deformation(
    setup_vertices_xy: tuple[Point, ...],
    triangles: tuple[Triangle, ...],
    *,
    min_area_ratio: float,
    max_area_ratio: float,
    max_edge_stretch: float,
) -> PreparedBodySwayDeformation:
    """Validate setup once, then retain its exact comparison terms."""

    assessment = measure_deformation(
        setup_vertices_xy, setup_vertices_xy, triangles,
        min_area_ratio=min_area_ratio,
        max_area_ratio=max_area_ratio,
        max_edge_stretch=max_edge_stretch,
    )
    if assessment.status != "passed":
        raise ValueError("Mesh setup topology is rejected")
    edges = tuple(sorted({
        edge
        for triangle in triangles
        for edge in _edges(triangle)
    }))
    return PreparedBodySwayDeformation(
        setup_vertices_xy=setup_vertices_xy,
        triangles=triangles,
        edges=edges,
        setup_areas=tuple(
            _signed_area(setup_vertices_xy, triangle)
            for triangle in triangles
        ),
        setup_edge_lengths=tuple(
            _edge_length(setup_vertices_xy, edge) for edge in edges
        ),
        min_area_ratio=float(min_area_ratio),
        max_area_ratio=float(max_area_ratio),
        max_edge_stretch=float(max_edge_stretch),
    )


def assess_prepared_body_sway_deformation(
    prepared: PreparedBodySwayDeformation,
    posed_vertices_xy: Sequence[Sequence[float]],
) -> DeformationAssessment:
    """Measure one pose without reparsing immutable setup topology."""

    if type(prepared) is not PreparedBodySwayDeformation:
        raise ValueError("Prepared body-sway deformation input is invalid")
    posed = _posed_vertices(posed_vertices_xy, len(prepared.setup_vertices_xy))
    non_finite = sum(
        not math.isfinite(coordinate)
        for point in posed for coordinate in point
    )
    if non_finite:
        return _non_finite(len(posed), len(prepared.triangles), non_finite)
    posed_areas = tuple(
        _signed_area(posed, triangle) for triangle in prepared.triangles
    )
    posed_lengths = tuple(
        _edge_length(posed, edge) for edge in prepared.edges
    )
    if any(not math.isfinite(value)
           for value in (*posed_areas, *posed_lengths)):
        return _non_finite(len(posed), len(prepared.triangles), 1)
    ratios = tuple(
        posed_area / setup_area
        for posed_area, setup_area in zip(
            posed_areas, prepared.setup_areas, strict=True
        )
    )
    edge_ratios = tuple(
        posed_length / setup_length
        for posed_length, setup_length in zip(
            posed_lengths, prepared.setup_edge_lengths, strict=True
        )
    )
    if any(not math.isfinite(value) for value in (*ratios, *edge_ratios)):
        return _non_finite(len(posed), len(prepared.triangles), 1)
    metrics = DeformationMetrics(
        vertex_count=len(posed), triangle_count=len(prepared.triangles),
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
    reasons = _reasons(prepared, metrics)
    return DeformationAssessment(
        metrics=metrics,
        status="rejected" if reasons else "passed",
        reasons=reasons,
    )


def _posed_vertices(value, expected_count: int) -> tuple[Point, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) \
            or len(value) != expected_count:
        raise ValueError("Posed mesh vertices differ from prepared setup")
    result = []
    for point in value:
        if not isinstance(point, Sequence) or isinstance(point, (str, bytes)) \
                or len(point) != 2:
            raise ValueError("Posed mesh vertex must contain two coordinates")
        coordinates = []
        for coordinate in point:
            if isinstance(coordinate, bool) \
                    or not isinstance(coordinate, (int, float)):
                raise ValueError("Posed mesh coordinates must be numeric")
            coordinates.append(float(coordinate))
        result.append((coordinates[0], coordinates[1]))
    return tuple(result)


def _reasons(prepared, metrics) -> tuple[str, ...]:
    reasons = set()
    if metrics.flipped_count:
        reasons.add("flipped_triangles")
    if metrics.degenerate_count:
        reasons.add("degenerate_triangles")
    if metrics.min_signed_area_ratio <= prepared.min_area_ratio:
        reasons.add("minimum_area_ratio")
    if metrics.max_signed_area_ratio >= prepared.max_area_ratio:
        reasons.add("maximum_area_ratio")
    if metrics.max_edge_stretch_ratio >= prepared.max_edge_stretch:
        reasons.add("maximum_edge_stretch")
    return tuple(sorted(reasons))


def _non_finite(vertices: int, triangles: int, count: int):
    return DeformationAssessment(
        metrics=DeformationMetrics(
            vertex_count=vertices, triangle_count=triangles,
            non_finite_count=count, flipped_count=0, degenerate_count=0,
            min_signed_area_ratio=None, max_signed_area_ratio=None,
            max_edge_stretch_ratio=None, interior_crack_gap_px=0.0,
        ),
        status="rejected", reasons=("non_finite",),
    )


def _signed_area(vertices, triangle) -> float:
    first, second, third = (vertices[index] for index in triangle)
    return 0.5 * (
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )


def _edge_length(vertices, edge) -> float:
    left, right = (vertices[index] for index in edge)
    return math.hypot(right[0] - left[0], right[1] - left[1])


def _edges(triangle) -> tuple[Edge, Edge, Edge]:
    first, second, third = triangle
    return tuple(
        (min(left, right), max(left, right))
        for left, right in ((first, second), (second, third), (third, first))
    )  # type: ignore[return-value]
