"""Version-one attachment-local seam locators and pair geometry."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction
import math
import re
from typing import Any


REGION_QUANTIZATION = 4096
MESH_QUANTIZATION = 65535
MAX_MESH_VERTICES = 4096
MAX_MESH_TRIANGLES = 8192
MAX_ABS_ATTACHMENT_COORDINATE = 1_000_000_000


class SeamAnchorLocatorError(ValueError):
    """Raised when a locator or locator pair is not canonical and valid."""


def make_attachment_locator(
    attachment: Mapping[str, Any], setup_canvas_xy: Sequence[int | float]
) -> dict[str, Any]:
    """Create the canonical locator for a setup-canvas point.

    Mesh points must lie in a triangle. Shared-edge points use the smallest
    containing flat-triangle index; they are never snapped to a vertex.
    """

    kind, identifier, offset = _attachment_header(attachment)
    point = _point(setup_canvas_xy, "setup canvas point")
    local = point[0] - offset[0], point[1] - offset[1]
    if kind == "region":
        width, height = _region_size(attachment)
        local = _require_region_point(local, width, height)
        quantized = tuple(min(
            _round_half_up(value * REGION_QUANTIZATION),
            extent * REGION_QUANTIZATION // 1,
        ) for value, extent in zip(local, (width, height), strict=True))
        result = {
            "attachment_id": identifier, "attachment_type": "region",
            "locator_type": "region-local-q4096",
            "local_xy_q4096": list(quantized),
        }
    else:
        vertices, triangles = _mesh_geometry(attachment)
        triangle_index, quantized = _canonical_mesh_locator(
            local, vertices, triangles
        )
        result = {
            "attachment_id": identifier, "attachment_type": "mesh",
            "locator_type": "mesh-barycentric-q65535",
            "triangle_index": triangle_index,
            "vertex_indices": list(triangles[triangle_index]),
            "weights_q65535": list(quantized),
        }
    resolve_attachment_locator(result, attachment)
    return result


def resolve_attachment_locator(
    locator: Mapping[str, Any], attachment: Mapping[str, Any]
) -> tuple[float, float]:
    """Strictly validate a locator and reconstruct its setup-canvas point."""

    point = resolve_attachment_locator_exact(locator, attachment)
    return float(point[0]), float(point[1])


def resolve_attachment_locator_exact(
    locator: Mapping[str, Any], attachment: Mapping[str, Any]
) -> tuple[Fraction, Fraction]:
    """Validate and resolve a locator without discarding rational identity."""

    return _resolve_fraction(locator, attachment)


def _resolve_fraction(locator, attachment):
    kind, identifier, offset = _attachment_header(attachment)
    if not isinstance(locator, Mapping):
        raise SeamAnchorLocatorError("locator must be an object")
    common = {"attachment_id", "attachment_type", "locator_type"}
    if locator.get("attachment_id") != identifier \
            or locator.get("attachment_type") != kind:
        raise SeamAnchorLocatorError("locator attachment identity is invalid")
    if kind == "region":
        if set(locator) != common | {"local_xy_q4096"} \
                or locator.get("locator_type") != "region-local-q4096":
            raise SeamAnchorLocatorError("region locator fields are invalid")
        qx, qy = _integer_pair(locator["local_xy_q4096"], "region locator")
        width, height = _region_size(attachment)
        if qx < 0 or qy < 0 \
                or Fraction(qx, REGION_QUANTIZATION) > width \
                or Fraction(qy, REGION_QUANTIZATION) > height:
            raise SeamAnchorLocatorError("region locator is outside attachment bounds")
        return (offset[0] + Fraction(qx, REGION_QUANTIZATION),
                offset[1] + Fraction(qy, REGION_QUANTIZATION))
    fields = common | {"triangle_index", "vertex_indices", "weights_q65535"}
    if set(locator) != fields \
            or locator.get("locator_type") != "mesh-barycentric-q65535":
        raise SeamAnchorLocatorError("mesh locator fields are invalid")
    vertices, triangles = _mesh_geometry(attachment)
    triangle_index = _integer(locator["triangle_index"], "triangle index")
    if not 0 <= triangle_index < len(triangles):
        raise SeamAnchorLocatorError("mesh locator triangle index is out of bounds")
    indices = _integer_triplet(locator["vertex_indices"], "vertex indices")
    if indices != triangles[triangle_index]:
        raise SeamAnchorLocatorError("mesh locator triangle topology changed")
    weights = _integer_triplet(locator["weights_q65535"], "mesh weights")
    if min(weights) < 0 or sum(weights) != MESH_QUANTIZATION:
        raise SeamAnchorLocatorError("mesh locator weights must be nonnegative and sum to 65535")
    local = tuple(sum(Fraction(weights[i], MESH_QUANTIZATION)
                      * vertices[indices[i]][axis] for i in range(3))
                  for axis in range(2))
    selected = _smallest_containing_triangle(local, vertices, triangles)
    if selected is None or selected[0] != triangle_index:
        raise SeamAnchorLocatorError("mesh locator does not use the first containing triangle")
    return offset[0] + local[0], offset[1] + local[1]


def _attachment_header(attachment):
    if not isinstance(attachment, Mapping):
        raise SeamAnchorLocatorError("attachment must be an object")
    identifier = _identifier(attachment.get("id"), "attachment id")
    kind = attachment.get("type")
    if kind not in ("region", "mesh"):
        raise SeamAnchorLocatorError("attachment type must be region or mesh")
    return kind, identifier, _point(attachment.get("canvas_offset_xy"), "canvas offset")


def _region_size(attachment):
    size = _point(attachment.get("size"), "region size")
    if size[0] <= 0 or size[1] <= 0:
        raise SeamAnchorLocatorError("region size must be positive")
    return size


def _mesh_geometry(attachment):
    raw_vertices, raw_triangles = attachment.get("vertices"), attachment.get("triangles")
    if not isinstance(raw_vertices, Sequence) or isinstance(raw_vertices, (str, bytes)) \
            or not 3 <= len(raw_vertices) <= MAX_MESH_VERTICES:
        raise SeamAnchorLocatorError("mesh vertex inventory is invalid")
    vertices = tuple(_point(value, "mesh vertex") for value in raw_vertices)
    if any(coordinate < 0 for point in vertices for coordinate in point):
        raise SeamAnchorLocatorError("mesh vertex is outside local bounds")
    if not isinstance(raw_triangles, Sequence) or isinstance(raw_triangles, (str, bytes)) \
            or len(raw_triangles) % 3 or not 3 <= len(raw_triangles) <= MAX_MESH_TRIANGLES * 3:
        raise SeamAnchorLocatorError("flat mesh triangle inventory is invalid")
    flat = tuple(_integer(value, "triangle vertex") for value in raw_triangles)
    triangles = tuple(tuple(flat[index:index + 3])
                      for index in range(0, len(flat), 3))
    seen: set[tuple[int, int, int]] = set()
    referenced: set[int] = set()
    edge_counts: dict[tuple[int, int], int] = {}
    for triangle in triangles:
        if len(set(triangle)) != 3 or min(triangle) < 0 or max(triangle) >= len(vertices):
            raise SeamAnchorLocatorError("mesh triangle topology is invalid")
        canonical = tuple(sorted(triangle))
        if canonical in seen:
            raise SeamAnchorLocatorError("mesh triangle topology has a duplicate")
        seen.add(canonical)
        referenced.update(triangle)
        if _orientation(*(vertices[index] for index in triangle)) <= 0:
            raise SeamAnchorLocatorError("mesh triangle winding is invalid")
        for left, right in zip(triangle, (*triangle[1:], triangle[0])):
            edge = min(left, right), max(left, right)
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
            if edge_counts[edge] > 2:
                raise SeamAnchorLocatorError("mesh edge topology is nonmanifold")
    if referenced != set(range(len(vertices))):
        raise SeamAnchorLocatorError("mesh topology has unreferenced vertices")
    return vertices, triangles


def _smallest_containing_triangle(point, vertices, triangles):
    for index, triangle in enumerate(triangles):
        barycentric = _barycentric(point, *(vertices[item] for item in triangle))
        if barycentric is not None:
            return index, barycentric
    return None


def _canonical_mesh_locator(point, vertices, triangles):
    selected = _smallest_containing_triangle(point, vertices, triangles)
    if selected is None:
        raise SeamAnchorLocatorError(
            "mesh locator point is outside every triangle"
        )
    while True:
        index, barycentric = selected
        quantized = _quantize_barycentric(barycentric)
        indices = triangles[index]
        snapped = tuple(sum(
            Fraction(quantized[item], MESH_QUANTIZATION)
            * vertices[indices[item]][axis] for item in range(3)
        ) for axis in range(2))
        canonical = _smallest_containing_triangle(
            snapped, vertices, triangles
        )
        if canonical is None or canonical[0] > index:
            raise SeamAnchorLocatorError(
                "mesh locator quantization is inconsistent"
            )
        if canonical[0] == index:
            return index, quantized
        selected = canonical


def _barycentric(point, a, b, c):
    denominator = _orientation(a, b, c)
    if denominator == 0:
        return None
    values = (_orientation(point, b, c) / denominator,
              _orientation(a, point, c) / denominator,
              _orientation(a, b, point) / denominator)
    if any(value < 0 or value > 1 for value in values):
        return None
    total = sum(values)
    return tuple(value / total for value in values)


def _quantize_barycentric(values):
    scaled = tuple(value * MESH_QUANTIZATION for value in values)
    floors = [value.numerator // value.denominator for value in scaled]
    remaining = MESH_QUANTIZATION - sum(floors)
    ranking = sorted(range(3), key=lambda i: (-(scaled[i] - floors[i]), i))
    for index in ranking[:remaining]:
        floors[index] += 1
    return tuple(floors)


def _require_region_point(point, width, height):
    for value, extent in zip(point, (width, height), strict=True):
        if value < 0 or value > extent:
            raise SeamAnchorLocatorError("region locator point is outside attachment bounds")
    return point


def _orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _point(value, label):
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 2:
        raise SeamAnchorLocatorError(f"{label} must be a finite point")
    return tuple(_number(item, label) for item in value)


def _number(value, label):
    if not isinstance(value, (int, float)) or isinstance(value, bool) \
            or (isinstance(value, float) and not math.isfinite(value)) \
            or abs(value) > MAX_ABS_ATTACHMENT_COORDINATE:
        raise SeamAnchorLocatorError(f"{label} must contain finite numbers")
    return Fraction(str(value))


def _integer(value, label):
    if not isinstance(value, int) or isinstance(value, bool):
        raise SeamAnchorLocatorError(f"{label} must be an integer")
    return value


def _integer_pair(value, label):
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 2:
        raise SeamAnchorLocatorError(f"{label} must contain two integers")
    return tuple(_integer(item, label) for item in value)


def _integer_triplet(value, label):
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 3:
        raise SeamAnchorLocatorError(f"{label} must contain three integers")
    return tuple(_integer(item, label) for item in value)


def _identifier(value, label):
    if not isinstance(value, str) or not value or len(value) > 128 \
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) is None:
        raise SeamAnchorLocatorError(f"{label} is invalid")
    return value


def _round_half_up(value: Fraction) -> int:
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)
