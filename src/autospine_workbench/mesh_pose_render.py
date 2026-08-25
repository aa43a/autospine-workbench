"""Deterministic full-canvas texture rendering for one posed mesh attachment."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

from .mesh_deformation_metrics import DeformationMetricsError, measure_deformation
from .mesh_skinning import MeshSkinningError, skin_vertices_lbs
from .mesh_topology import MeshTopologyError, validate_mesh_topology
from .png_rgba import MAX_RGBA_DIMENSION, MAX_RGBA_PIXELS, RgbaImage


SETUP_ALPHA_THRESHOLD = 8
_BARYCENTRIC_TOLERANCE = 1e-10
_MAX_SAMPLE_FACTOR = 16


class MeshPoseRenderError(ValueError):
    """Raised when a posed texture render would conceal invalid mesh evidence."""


def render_mesh_pose(
    source: RgbaImage,
    rig_bones: Sequence[Mapping[str, Any]],
    mesh_attachment: Mapping[str, Any],
    pose_rotation_deltas_deg: Mapping[str, int | float],
    *,
    canvas_width: int,
    canvas_height: int,
) -> RgbaImage:
    """Skin one source-local mesh and nearest-sample it onto a clear canvas."""

    try:
        source_width, source_height = _image_size(source)
        canvas = _canvas_size(canvas_width, canvas_height)
        attachment = _object(mesh_attachment, "mesh attachment")
        if attachment.get("type") != "mesh":
            raise MeshPoseRenderError("attachment must be a mesh")
        offset = _integer_pair(
            attachment.get("canvas_offset_xy"), "mesh canvas offset"
        )
        if (
            offset[0] < 0 or offset[1] < 0
            or offset[0] + source_width > canvas[0]
            or offset[1] + source_height > canvas[1]
        ):
            raise MeshPoseRenderError("source raster is outside the output canvas")
        local_vertices = _pairs(attachment.get("vertices"), "mesh vertices")
        uvs = _pairs(attachment.get("uvs"), "mesh UVs")
        triangles = _triangles(attachment.get("triangles"))
        validate_mesh_topology(
            vertices_xy=local_vertices,
            uvs=uvs,
            triangles=triangles,
            width_px=source_width,
            height_px=source_height,
        )
        _require_local_uvs(local_vertices, uvs, source_width, source_height)
        bind_vertices = tuple(
            (x + offset[0], y + offset[1]) for x, y in local_vertices
        )
        _require_inside(bind_vertices, canvas, "setup")
        posed_vertices = skin_vertices_lbs(
            rig_bones,
            bind_vertices,
            attachment.get("weights"),
            pose_rotation_deltas_deg,
        )
        _require_inside(posed_vertices, canvas, "posed")
        assessment = measure_deformation(
            bind_vertices, posed_vertices, triangles
        )
        if assessment.status != "passed":
            reasons = ", ".join(assessment.reasons) or "unknown deformation"
            raise MeshPoseRenderError(f"posed mesh deformation is rejected: {reasons}")
        setup = _rasterize(
            source, bind_vertices, uvs, triangles, canvas
        )
        _require_setup_reconstruction(source, setup, offset)
        return _rasterize(source, posed_vertices, uvs, triangles, canvas)
    except MeshPoseRenderError:
        raise
    except (
        MeshSkinningError,
        MeshTopologyError,
        DeformationMetricsError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise MeshPoseRenderError(f"mesh pose render input is invalid: {exc}") from exc


def _rasterize(source, vertices, uvs, triangles, canvas) -> RgbaImage:
    ordered = tuple(sorted(_canonical_triangle(item) for item in triangles))
    bounds = tuple(
        _pixel_bounds(item, vertices, canvas[0], canvas[1])
        for item in ordered
    )
    sample_count = sum(
        (right - left + 1) * (bottom - top + 1)
        for left, top, right, bottom in bounds
    )
    if sample_count > max(1024, canvas[0] * canvas[1] * _MAX_SAMPLE_FACTOR):
        raise MeshPoseRenderError("mesh rasterization sample budget is exceeded")
    output = bytearray(canvas[0] * canvas[1] * 4)
    coverage = bytearray(canvas[0] * canvas[1])
    for triangle, bounds_xyxy in zip(ordered, bounds):
        _raster_triangle(
            triangle, bounds_xyxy, vertices, uvs, source,
            canvas[0], output, coverage,
        )
    return RgbaImage(canvas[0], canvas[1], bytes(output))


def _raster_triangle(
    triangle, bounds, vertices, uvs, source, canvas_width, output, coverage
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
            if min(barycentric) < -_BARYCENTRIC_TOLERANCE:
                continue
            uv = tuple(sum(
                barycentric[index] * uvs[vertex][axis]
                for index, vertex in enumerate(triangle)
            ) for axis in (0, 1))
            source_x = _texel(uv[0] * source.width, source.width)
            source_y = _texel(uv[1] * source.height, source.height)
            source_index = (source_y * source.width + source_x) * 4
            rgba = bytes(source.pixels[source_index:source_index + 4])
            if rgba[3] == 0:
                rgba = b"\0\0\0\0"
            pixel_index = y * canvas_width + x
            output_index = pixel_index * 4
            if coverage[pixel_index]:
                if bytes(output[output_index:output_index + 4]) != rgba:
                    raise MeshPoseRenderError(
                        "overlapping triangles produce inconsistent RGBA"
                    )
                continue
            coverage[pixel_index] = 1
            output[output_index:output_index + 4] = rgba


def _require_setup_reconstruction(source, setup, offset) -> None:
    for y in range(source.height):
        for x in range(source.width):
            source_index = (y * source.width + x) * 4
            if source.pixels[source_index + 3] < SETUP_ALPHA_THRESHOLD:
                continue
            canvas_index = (
                (offset[1] + y) * setup.width + offset[0] + x
            ) * 4
            if (
                setup.pixels[canvas_index:canvas_index + 4]
                != source.pixels[source_index:source_index + 4]
            ):
                raise MeshPoseRenderError(
                    "setup mesh does not byte-exactly reconstruct alpha >= 8 source"
                )


def _require_local_uvs(vertices, uvs, width, height) -> None:
    for index, (vertex, uv) in enumerate(zip(vertices, uvs)):
        expected = (vertex[0] / width, vertex[1] / height)
        if not all(
            math.isclose(actual, wanted, rel_tol=0.0, abs_tol=1e-12)
            for actual, wanted in zip(uv, expected)
        ):
            raise MeshPoseRenderError(
                f"mesh UV {index} does not match its source-local vertex"
            )


def _require_inside(vertices, canvas, label) -> None:
    for index, (x, y) in enumerate(vertices):
        if not 0.0 <= x <= canvas[0] or not 0.0 <= y <= canvas[1]:
            raise MeshPoseRenderError(
                f"{label} vertex {index} is outside the output canvas"
            )


def _triangles(value: Any) -> tuple[tuple[int, int, int], ...]:
    items = _array(value, "mesh triangles")
    if not items or len(items) % 3:
        raise MeshPoseRenderError("mesh triangle index array must contain triples")
    if any(not isinstance(item, int) or isinstance(item, bool) for item in items):
        raise MeshPoseRenderError("mesh triangle indices must be integers")
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


def _texel(value: float, extent: int) -> int:
    nearest = round(value)
    stable = float(nearest) if abs(value - nearest) <= 1e-10 else value
    return min(extent - 1, max(0, math.floor(stable)))


def _image_size(value: Any) -> tuple[int, int]:
    if not isinstance(value, RgbaImage):
        raise MeshPoseRenderError("source must be an RgbaImage")
    width, height = value.width, value.height
    if (
        not _positive_int(width) or not _positive_int(height)
        or width > MAX_RGBA_DIMENSION or height > MAX_RGBA_DIMENSION
        or width * height > MAX_RGBA_PIXELS or not isinstance(value.pixels, bytes)
        or len(value.pixels) != width * height * 4
    ):
        raise MeshPoseRenderError("source RGBA image is invalid")
    return width, height


def _canvas_size(width: Any, height: Any) -> tuple[int, int]:
    if (
        not _positive_int(width) or not _positive_int(height)
        or width > MAX_RGBA_DIMENSION or height > MAX_RGBA_DIMENSION
        or width * height > MAX_RGBA_PIXELS
    ):
        raise MeshPoseRenderError("output canvas size is invalid")
    return width, height


def _pairs(value: Any, label: str) -> tuple[tuple[float, float], ...]:
    return tuple(_pair(item, f"{label} {index}") for index, item in enumerate(_array(value, label)))


def _integer_pair(value: Any, label: str) -> tuple[int, int]:
    if (
        not isinstance(value, (list, tuple)) or len(value) != 2
        or any(not isinstance(item, int) or isinstance(item, bool) for item in value)
    ):
        raise MeshPoseRenderError(f"{label} must contain two integers")
    return value[0], value[1]


def _pair(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise MeshPoseRenderError(f"{label} must contain two finite numbers")
    return _number(value[0], label), _number(value[1], label)


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MeshPoseRenderError(f"{label} must contain finite numbers")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise MeshPoseRenderError(f"{label} must contain finite numbers") from exc
    if not math.isfinite(result):
        raise MeshPoseRenderError(f"{label} must contain finite numbers")
    return result


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MeshPoseRenderError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        raise MeshPoseRenderError(f"{label} must be an array")
    return list(value)


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _cross(first, second, third) -> float:
    return ((second[0] - first[0]) * (third[1] - first[1])
            - (second[1] - first[1]) * (third[0] - first[0]))
