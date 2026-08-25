"""Deterministic alpha-supported regular grids for one mesh attachment."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .alpha_geometry import AlphaGeometry, analyze_alpha_image
from .mesh_topology import (
    MAX_ATTACHMENT_TRIANGLES,
    MAX_ATTACHMENT_VERTICES,
    MeshTopologyError,
    validate_mesh_topology,
)
from .png_rgba import RgbaImage


DEFAULT_ALPHA_THRESHOLD = 8
MIN_FOREGROUND_PIXELS = 64
MIN_SIGNIFICANT_COMPONENT_PIXELS = 16
SIGNIFICANT_COMPONENT_RATIO = 0.001
MIN_SIGNIFICANT_COVERAGE = 0.99


class AlphaGridMeshError(ValueError):
    """Raised when alpha evidence cannot safely produce a bounded mesh."""


@dataclass(frozen=True, slots=True)
class AlphaGridMesh:
    """One attachment mesh in source-raster-edge pixel coordinates."""

    width_px: int
    height_px: int
    grid_step_px: int
    alpha_threshold: int
    foreground_pixels: int
    significant_component_pixels: int
    significant_threshold_pixels: int
    component_areas: tuple[int, ...]
    vertices_xy: tuple[tuple[int, int], ...]
    uvs: tuple[tuple[float, float], ...]
    triangles: tuple[tuple[int, int, int], ...]
    active_cells_xyxy: tuple[tuple[int, int, int, int], ...]


def build_alpha_grid_mesh(
    image: RgbaImage,
    *,
    grid_step_px: int,
    alpha_threshold: int = DEFAULT_ALPHA_THRESHOLD,
) -> AlphaGridMesh:
    """Build a non-adaptive grid over cells supported by perceptible alpha."""

    step = _positive_integer(grid_step_px, "grid step")
    threshold = _alpha_threshold(alpha_threshold)
    geometry = _alpha_geometry(image, threshold)
    significant, significant_threshold = _require_single_component(geometry)
    x_edges = _grid_edges(image.width, step)
    y_edges = _grid_edges(image.height, step)
    active = _active_cells(image, threshold, x_edges, y_edges)
    vertices = _vertices(active)
    triangles = _triangles(active, vertices)
    uvs = tuple((x / image.width, y / image.height) for x, y in vertices)
    try:
        validate_mesh_topology(
            vertices_xy=vertices,
            uvs=uvs,
            triangles=triangles,
            width_px=image.width,
            height_px=image.height,
            max_vertices=MAX_ATTACHMENT_VERTICES,
            max_triangles=MAX_ATTACHMENT_TRIANGLES,
        )
    except MeshTopologyError as exc:
        raise AlphaGridMeshError(str(exc)) from exc
    return AlphaGridMesh(
        width_px=image.width,
        height_px=image.height,
        grid_step_px=step,
        alpha_threshold=threshold,
        foreground_pixels=geometry.foreground_area,
        significant_component_pixels=significant,
        significant_threshold_pixels=significant_threshold,
        component_areas=tuple(item.area for item in geometry.components),
        vertices_xy=vertices,
        uvs=uvs,
        triangles=triangles,
        active_cells_xyxy=tuple(cell[2] for cell in active),
    )


def _alpha_geometry(image: RgbaImage, threshold: int) -> AlphaGeometry:
    if (
        not isinstance(image, RgbaImage)
        or not isinstance(image.width, int)
        or isinstance(image.width, bool)
        or not isinstance(image.height, int)
        or isinstance(image.height, bool)
        or image.width < 1
        or image.height < 1
        or not isinstance(image.pixels, bytes)
        or len(image.pixels) != image.width * image.height * 4
    ):
        raise AlphaGridMeshError("RGBA image is invalid")
    try:
        geometry = analyze_alpha_image(image, threshold=threshold)
    except ValueError as exc:
        raise AlphaGridMeshError(str(exc)) from exc
    if geometry.foreground_area == 0:
        raise AlphaGridMeshError(
            f"alpha mesh has no foreground at threshold {threshold}"
        )
    if geometry.foreground_area < MIN_FOREGROUND_PIXELS:
        raise AlphaGridMeshError(
            f"alpha mesh needs at least {MIN_FOREGROUND_PIXELS} foreground pixels"
        )
    return geometry


def _require_single_component(geometry) -> tuple[int, int]:
    foreground = geometry.foreground_area
    significant_threshold = max(
        MIN_SIGNIFICANT_COMPONENT_PIXELS,
        math.ceil(foreground * SIGNIFICANT_COMPONENT_RATIO),
    )
    significant = [
        item.area for item in geometry.components
        if item.area >= significant_threshold
    ]
    if len(significant) != 1:
        raise AlphaGridMeshError(
            "alpha mesh needs exactly one significant 8-connected component"
        )
    area = significant[0]
    if area * 100 < foreground * 99:
        raise AlphaGridMeshError(
            "significant alpha component must cover at least 99 percent of foreground"
        )
    return area, significant_threshold


def _grid_edges(extent: int, step: int) -> tuple[int, ...]:
    edges = list(range(0, extent, step))
    if not edges or edges[-1] != extent:
        edges.append(extent)
    return tuple(edges)


def _active_cells(
    image: RgbaImage,
    threshold: int,
    x_edges: tuple[int, ...],
    y_edges: tuple[int, ...],
) -> tuple[tuple[int, int, tuple[int, int, int, int]], ...]:
    result: list[tuple[int, int, tuple[int, int, int, int]]] = []
    vertices: set[tuple[int, int]] = set()
    for row, (top, bottom) in enumerate(zip(y_edges, y_edges[1:])):
        for column, (left, right) in enumerate(zip(x_edges, x_edges[1:])):
            if not _cell_has_foreground(
                image, threshold, left, top, right, bottom
            ):
                continue
            result.append((row, column, (left, top, right, bottom)))
            if len(result) * 2 > MAX_ATTACHMENT_TRIANGLES:
                raise AlphaGridMeshError(
                    f"alpha grid exceeds the {MAX_ATTACHMENT_TRIANGLES} triangle limit"
                )
            vertices.update(
                ((left, top), (right, top), (left, bottom), (right, bottom))
            )
            if len(vertices) > MAX_ATTACHMENT_VERTICES:
                raise AlphaGridMeshError(
                    f"alpha grid exceeds the {MAX_ATTACHMENT_VERTICES} vertex limit"
                )
    return tuple(result)


def _cell_has_foreground(
    image: RgbaImage, threshold: int,
    left: int, top: int, right: int, bottom: int
) -> bool:
    stride = image.width * 4
    for y in range(top, bottom):
        alpha_start = y * stride + left * 4 + 3
        for offset in range(alpha_start, y * stride + right * 4, 4):
            if image.pixels[offset] >= threshold:
                return True
    return False


def _vertices(
    active: tuple[tuple[int, int, tuple[int, int, int, int]], ...]
) -> tuple[tuple[int, int], ...]:
    values = {
        point
        for _, _, (left, top, right, bottom) in active
        for point in ((left, top), (right, top), (left, bottom), (right, bottom))
    }
    return tuple(sorted(values, key=lambda point: (point[1], point[0])))


def _triangles(
    active: tuple[tuple[int, int, tuple[int, int, int, int]], ...],
    vertices: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int, int], ...]:
    index = {point: position for position, point in enumerate(vertices)}
    result: list[tuple[int, int, int]] = []
    for row, column, (left, top, right, bottom) in active:
        tl, tr = index[(left, top)], index[(right, top)]
        bl, br = index[(left, bottom)], index[(right, bottom)]
        if (row + column) % 2 == 0:
            result.extend(((tl, tr, br), (tl, br, bl)))
        else:
            result.extend(((tl, tr, bl), (tr, br, bl)))
    return tuple(result)


def _positive_integer(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise AlphaGridMeshError(f"{label} must be a positive integer")
    return value


def _alpha_threshold(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 255:
        raise AlphaGridMeshError("alpha threshold must be an integer in [1, 255]")
    return value
