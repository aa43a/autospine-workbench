"""Deterministic local-space visualization of two-bone mesh weights."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import re
from typing import Any

from .mesh_topology import MeshTopologyError, validate_mesh_topology
from .png_rgba import MAX_RGBA_DIMENSION, MAX_RGBA_PIXELS, RgbaImage


ALPHA_COVERAGE_THRESHOLD = 8
PROXIMAL_RGB = (0x25, 0x63, 0xEB)
BALANCED_RGB = (0xA8, 0x55, 0xF7)
DISTAL_RGB = (0xEF, 0x44, 0x44)
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WEIGHT_TOLERANCE = 1e-12
_BARYCENTRIC_TOLERANCE = 1e-10
_MAX_SAMPLE_FACTOR = 16


class MeshWeightHeatmapError(ValueError):
    """Raised when a mesh cannot be rasterized without hiding bad evidence."""


def render_mesh_weight_heatmap(
    source: RgbaImage,
    attachment: Mapping[str, Any],
    *,
    proximal_bone_id: str,
    distal_bone_id: str,
) -> RgbaImage:
    """Render distal weight in attachment-local space with source alpha intact."""

    width, height = _image_size(source)
    attachment = _object(attachment, "mesh attachment")
    proximal = _bone_id(proximal_bone_id, "proximal bone")
    distal = _bone_id(distal_bone_id, "distal bone")
    if proximal == distal:
        raise MeshWeightHeatmapError("proximal and distal bones must differ")
    if attachment.get("type") != "mesh":
        raise MeshWeightHeatmapError("attachment must be a mesh")
    _pair(attachment.get("canvas_offset_xy"), "canvas offset")  # local only

    vertices = _pairs(attachment.get("vertices"), "vertices")
    uvs = _pairs(attachment.get("uvs"), "UVs")
    triangles = _triangles(attachment.get("triangles"))
    distal_weights = _distal_weights(
        attachment.get("weights"), len(vertices), proximal, distal
    )
    try:
        validate_mesh_topology(
            vertices_xy=vertices,
            uvs=uvs,
            triangles=triangles,
            width_px=width,
            height_px=height,
        )
    except MeshTopologyError as exc:
        raise MeshWeightHeatmapError(f"mesh topology is invalid: {exc}") from exc
    _require_local_uvs(vertices, uvs, width, height)

    ordered = tuple(sorted(_canonical_triangle(item) for item in triangles))
    bounds = tuple(_pixel_bounds(item, vertices, width, height) for item in ordered)
    sample_count = sum(
        (right - left + 1) * (bottom - top + 1)
        for left, top, right, bottom in bounds
    )
    if sample_count > max(1024, width * height * _MAX_SAMPLE_FACTOR):
        raise MeshWeightHeatmapError("mesh rasterization sample budget is exceeded")

    output = bytearray(width * height * 4)
    output[3::4] = source.pixels[3::4]
    coverage = bytearray(width * height)
    distal_q16 = bytearray(width * height * 2)
    for triangle, bounds_xyxy in zip(ordered, bounds):
        _raster_triangle(
            triangle, bounds_xyxy, vertices, distal_weights,
            source, output, coverage, distal_q16,
        )
    for pixel_index, alpha in enumerate(source.pixels[3::4]):
        if alpha >= ALPHA_COVERAGE_THRESHOLD and not coverage[pixel_index]:
            raise MeshWeightHeatmapError(
                "mesh leaves a source pixel with alpha >= 8 uncovered"
            )
    return RgbaImage(width, height, bytes(output))


def _raster_triangle(
    triangle, bounds, vertices, weights, source, output, coverage, distal_q16
) -> None:
    first, second, third = (vertices[index] for index in triangle)
    denominator = _cross(first, second, third)
    left, top, right, bottom = bounds
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            point = (x + 0.5, y + 0.5)
            barycentric = (
                _cross(point, second, third) / denominator,
                _cross(first, point, third) / denominator,
                _cross(first, second, point) / denominator,
            )
            edges = ((second, third), (third, first), (first, second))
            if any(
                value < -_BARYCENTRIC_TOLERANCE
                or (
                    abs(value) <= _BARYCENTRIC_TOLERANCE
                    and not _owns_shared_edge(*edge)
                )
                for value, edge in zip(barycentric, edges)
            ):
                continue
            value = min(1.0, max(0.0, sum(
                barycentric[index] * weights[vertex]
                for index, vertex in enumerate(triangle)
            )))
            color = _weight_rgb(value)
            quantized = _round_half_up(value * 65535.0)
            pixel_index = y * source.width + x
            byte_index = pixel_index * 4
            q_index = pixel_index * 2
            if coverage[pixel_index]:
                previous_q = distal_q16[q_index] | (distal_q16[q_index + 1] << 8)
                if previous_q != quantized or tuple(output[byte_index:byte_index + 3]) != color:
                    raise MeshWeightHeatmapError(
                        "overlapping triangles produce inconsistent pixel weights"
                    )
                continue
            coverage[pixel_index] = 1
            distal_q16[q_index] = quantized & 0xFF
            distal_q16[q_index + 1] = quantized >> 8
            if source.pixels[byte_index + 3] != 0:
                output[byte_index:byte_index + 3] = bytes(color)


def _distal_weights(value, vertex_count, proximal, distal) -> tuple[float, ...]:
    rows = _array(value, "weights")
    if len(rows) != vertex_count:
        raise MeshWeightHeatmapError("weight count must equal vertex count")
    result: list[float] = []
    for vertex_index, raw in enumerate(rows):
        influences = _array(raw, f"weight {vertex_index}")
        if len(influences) not in (1, 2):
            raise MeshWeightHeatmapError("each vertex needs one or two influences")
        seen: set[str] = set()
        total = distal_weight = 0.0
        for raw_influence in influences:
            influence = _object(raw_influence, "weight influence")
            if set(influence) != {"bone", "weight"}:
                raise MeshWeightHeatmapError("weight influence fields are invalid")
            bone = influence.get("bone")
            weight = _weight(influence.get("weight"))
            if bone not in {proximal, distal}:
                raise MeshWeightHeatmapError("mesh uses a non-designated bone")
            if bone in seen:
                raise MeshWeightHeatmapError("mesh repeats a bone influence")
            seen.add(bone)
            total += weight
            if bone == distal:
                distal_weight = weight
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=_WEIGHT_TOLERANCE):
            raise MeshWeightHeatmapError("vertex weights are not normalized")
        result.append(distal_weight)
    return tuple(result)


def _require_local_uvs(vertices, uvs, width, height) -> None:
    for index, (vertex, uv) in enumerate(zip(vertices, uvs)):
        expected = (vertex[0] / width, vertex[1] / height)
        if not all(
            math.isclose(actual, wanted, rel_tol=0.0, abs_tol=1e-12)
            for actual, wanted in zip(uv, expected)
        ):
            raise MeshWeightHeatmapError(
                f"UV {index} does not match the source image dimensions"
            )


def _triangles(value: Any) -> tuple[tuple[int, int, int], ...]:
    items = _array(value, "triangles")
    if not items or len(items) % 3:
        raise MeshWeightHeatmapError("triangle index array must contain triples")
    if any(not isinstance(item, int) or isinstance(item, bool) for item in items):
        raise MeshWeightHeatmapError("triangle indices must be integers")
    return tuple(tuple(items[index:index + 3]) for index in range(0, len(items), 3))


def _canonical_triangle(value) -> tuple[int, int, int]:
    minimum = min(range(3), key=lambda index: value[index])
    return value[minimum:] + value[:minimum]


def _pixel_bounds(triangle, vertices, width, height) -> tuple[int, int, int, int]:
    points = tuple(vertices[index] for index in triangle)
    left = max(0, math.ceil(min(point[0] for point in points) - 0.5))
    top = max(0, math.ceil(min(point[1] for point in points) - 0.5))
    right = min(width - 1, math.floor(max(point[0] for point in points) - 0.5))
    bottom = min(height - 1, math.floor(max(point[1] for point in points) - 0.5))
    return left, top, right, bottom


def _weight_rgb(distal_weight: float) -> tuple[int, int, int]:
    if distal_weight <= 0.5:
        start, end, fraction = PROXIMAL_RGB, BALANCED_RGB, distal_weight * 2.0
    else:
        start, end, fraction = BALANCED_RGB, DISTAL_RGB, distal_weight * 2.0 - 1.0
    return tuple(
        _round_half_up(left + (right - left) * fraction)
        for left, right in zip(start, end)
    )


def _image_size(value: Any) -> tuple[int, int]:
    if not isinstance(value, RgbaImage):
        raise MeshWeightHeatmapError("source must be an RgbaImage")
    width, height = value.width, value.height
    if (
        not isinstance(width, int) or isinstance(width, bool) or width < 1
        or not isinstance(height, int) or isinstance(height, bool) or height < 1
        or width > MAX_RGBA_DIMENSION or height > MAX_RGBA_DIMENSION
        or width * height > MAX_RGBA_PIXELS or not isinstance(value.pixels, bytes)
        or len(value.pixels) != width * height * 4
    ):
        raise MeshWeightHeatmapError("source RGBA image is invalid")
    return width, height


def _pairs(value: Any, label: str) -> tuple[tuple[float, float], ...]:
    return tuple(_pair(item, f"{label} {index}") for index, item in enumerate(_array(value, label)))


def _pair(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise MeshWeightHeatmapError(f"{label} must be a finite pair")
    return _number(value[0], label), _number(value[1], label)


def _weight(value: Any) -> float:
    result = _number(value, "weight")
    if not 0.0 < result <= 1.0:
        raise MeshWeightHeatmapError("weight must be in (0, 1]")
    return result


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MeshWeightHeatmapError(f"{label} must contain finite numbers")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise MeshWeightHeatmapError(
            f"{label} must contain finite numbers"
        ) from exc
    if not math.isfinite(result):
        raise MeshWeightHeatmapError(f"{label} must contain finite numbers")
    return result


def _bone_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise MeshWeightHeatmapError(f"{label} id is invalid")
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MeshWeightHeatmapError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        raise MeshWeightHeatmapError(f"{label} must be an array")
    return list(value)


def _cross(first, second, third) -> float:
    return ((second[0] - first[0]) * (third[1] - first[1])
            - (second[1] - first[1]) * (third[0] - first[0]))


def _owns_shared_edge(start, end) -> bool:
    dx, dy = end[0] - start[0], end[1] - start[1]
    return dy < 0.0 or (dy == 0.0 and dx > 0.0)


def _round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))
