"""Fail-closed invariants for version-neutral triangle meshes."""

from __future__ import annotations

from collections.abc import Sequence
import math
from typing import TypeAlias


MAX_ATTACHMENT_VERTICES = 4096
MAX_ATTACHMENT_TRIANGLES = 8192

Point: TypeAlias = tuple[int | float, int | float]
Triangle: TypeAlias = tuple[int, int, int]


class MeshTopologyError(ValueError):
    """Raised when mesh geometry or topology violates the pinned profile."""


def validate_mesh_topology(
    *,
    vertices_xy: Sequence[Sequence[int | float]],
    uvs: Sequence[Sequence[int | float]],
    triangles: Sequence[Sequence[int]],
    width_px: int,
    height_px: int,
    max_vertices: int = MAX_ATTACHMENT_VERTICES,
    max_triangles: int = MAX_ATTACHMENT_TRIANGLES,
) -> None:
    """Validate bounded clockwise topology in source-raster-edge space."""

    width = _positive_integer(width_px, "source width extent")
    height = _positive_integer(height_px, "source height extent")
    vertex_limit = _resource_limit(
        max_vertices, MAX_ATTACHMENT_VERTICES, "vertex"
    )
    triangle_limit = _resource_limit(
        max_triangles, MAX_ATTACHMENT_TRIANGLES, "triangle"
    )
    if not vertices_xy:
        raise MeshTopologyError("mesh has no vertices")
    if len(vertices_xy) > vertex_limit:
        raise MeshTopologyError(f"mesh exceeds the {vertex_limit} vertex limit")
    if len(uvs) != len(vertices_xy):
        raise MeshTopologyError("UV count must equal vertex count")
    if not triangles:
        raise MeshTopologyError("mesh has no triangles")
    if len(triangles) > triangle_limit:
        raise MeshTopologyError(f"mesh exceeds the {triangle_limit} triangle limit")

    vertices = tuple(
        _bounded_pair(value, width, height, f"vertex {index}")
        for index, value in enumerate(vertices_xy)
    )
    for index, value in enumerate(uvs):
        _bounded_pair(value, 1.0, 1.0, f"UV {index}")
    _validate_triangles(vertices, triangles)


def _validate_triangles(
    vertices: tuple[Point, ...], triangles: Sequence[Sequence[int]]
) -> None:
    seen: set[tuple[int, int, int]] = set()
    referenced: set[int] = set()
    edge_counts: dict[tuple[int, int], int] = {}
    for position, raw in enumerate(triangles):
        triangle = _triangle(raw, len(vertices), position)
        canonical = tuple(sorted(triangle))
        if canonical in seen:
            raise MeshTopologyError(f"duplicate triangle at index {position}")
        seen.add(canonical)
        if _signed_area_twice(vertices, triangle) <= 0:
            raise MeshTopologyError(
                f"triangle {position} must have positive canvas-y-down winding"
            )
        referenced.update(triangle)
        for edge in _edges(triangle):
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
            if edge_counts[edge] > 2:
                raise MeshTopologyError(f"edge {edge} belongs to more than two triangles")
    if len(referenced) != len(vertices):
        missing = sorted(set(range(len(vertices))) - referenced)
        raise MeshTopologyError(f"mesh has unreferenced vertices: {missing[:8]}")


def _triangle(value: Sequence[int], vertex_count: int, position: int) -> Triangle:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise MeshTopologyError(f"triangle {position} must contain three indices")
    if any(not isinstance(index, int) or isinstance(index, bool) for index in value):
        raise MeshTopologyError(f"triangle {position} indices must be integer values")
    result = (value[0], value[1], value[2])
    if len(set(result)) != 3:
        raise MeshTopologyError(f"triangle {position} indices must be distinct")
    if any(index < 0 or index >= vertex_count for index in result):
        raise MeshTopologyError(f"triangle {position} index is outside vertex range")
    return result


def _signed_area_twice(vertices: tuple[Point, ...], triangle: Triangle) -> float:
    first, second, third = (vertices[index] for index in triangle)
    return float(
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )


def _edges(triangle: Triangle) -> tuple[tuple[int, int], ...]:
    first, second, third = triangle
    return tuple(
        (min(left, right), max(left, right))
        for left, right in ((first, second), (second, third), (third, first))
    )


def _bounded_pair(
    value: Sequence[int | float], maximum_x: int | float,
    maximum_y: int | float, label: str
) -> Point:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise MeshTopologyError(f"{label} must be a coordinate pair")
    x = _finite_number(value[0], label)
    y = _finite_number(value[1], label)
    if not 0 <= x <= maximum_x or not 0 <= y <= maximum_y:
        raise MeshTopologyError(f"{label} is outside bounds")
    return x, y


def _finite_number(value: int | float, label: str) -> int | float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise MeshTopologyError(f"{label} coordinates must be finite numbers")
    return value


def _positive_integer(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise MeshTopologyError(f"{label} must be a positive integer")
    return value


def _resource_limit(value: int, ceiling: int, label: str) -> int:
    result = _positive_integer(value, f"{label} limit")
    if result > ceiling:
        raise MeshTopologyError(f"{label} limit cannot exceed {ceiling}")
    return result
