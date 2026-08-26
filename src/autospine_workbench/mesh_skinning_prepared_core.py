"""Private validation and matrix primitives for the sole prepared LBS core."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import heapq
import math
import re
from typing import Any, TypeAlias

from .mesh_skinning import MeshSkinningError, QUANTIZATION_PER_PIXEL


WEIGHT_SUM_TOLERANCE = 1e-9
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
Matrix: TypeAlias = tuple[float, float, float, float, float, float]
Point: TypeAlias = tuple[float, float]


@dataclass(frozen=True, slots=True)
class Bone:
    identifier: str
    parent: str | None
    x: float
    y: float
    rotation_deg: float
    scale_x: float
    scale_y: float


def bones(value) -> tuple[Bone, ...]:
    if not sequence(value) or not value:
        raise MeshSkinningError("rig_bones must be a non-empty array")
    result, seen = [], set()
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise MeshSkinningError(f"bone {index} must be an object")
        bone_id = safe_id(item.get("id"), f"bone {index}.id")
        if bone_id in seen:
            raise MeshSkinningError(
                f"bone {index} has an invalid or duplicate id"
            )
        parent = item.get("parent")
        if parent is not None:
            parent = safe_id(parent, f"bone {bone_id}.parent")
        setup = item.get("setup")
        if not isinstance(setup, Mapping):
            raise MeshSkinningError(f"bone {bone_id}.setup must be an object")
        length = number(setup.get("length"), f"bone {bone_id}.setup.length")
        scale_x = number(setup.get("scale_x"), f"bone {bone_id}.setup.scale_x")
        scale_y = number(setup.get("scale_y"), f"bone {bone_id}.setup.scale_y")
        if length <= 1e-9:
            raise MeshSkinningError(f"bone {bone_id} has zero length")
        if scale_x <= 1e-12 or scale_y <= 1e-12:
            raise MeshSkinningError(f"bone {bone_id} scale must be positive")
        result.append(Bone(
            bone_id, parent,
            number(setup.get("x"), f"bone {bone_id}.setup.x"),
            number(setup.get("y"), f"bone {bone_id}.setup.y"),
            number(setup.get("rotation_deg"),
                   f"bone {bone_id}.setup.rotation_deg"),
            scale_x, scale_y,
        ))
        seen.add(bone_id)
    return tuple(result)


def pose_deltas(value, rig):
    if not isinstance(value, Mapping):
        raise MeshSkinningError("pose_rotation_deltas_deg must be an object")
    result = {}
    for bone_id, delta in value.items():
        bone_id = safe_id(bone_id, "pose bone id")
        if bone_id not in rig._bone_index:
            raise MeshSkinningError(f"pose references unknown bone: {bone_id}")
        result[bone_id] = number(delta, f"pose delta for bone {bone_id}")
    return result


def vertices(value) -> tuple[Point, ...]:
    if not sequence(value) or not value:
        raise MeshSkinningError("vertices_xy must be a non-empty array")
    result = []
    for index, item in enumerate(value):
        if not sequence(item) or len(item) != 2:
            raise MeshSkinningError(f"vertex {index} must contain two coordinates")
        result.append((number(item[0], f"vertex {index}.x"),
                       number(item[1], f"vertex {index}.y")))
    return tuple(result)


def influences(value, rig, vertex):
    if not sequence(value) or len(value) not in (1, 2):
        raise MeshSkinningError(
            f"vertex {vertex} must have one or two influences"
        )
    result = []
    for influence in value:
        if not isinstance(influence, Mapping) \
                or set(influence) != {"bone", "weight"}:
            raise MeshSkinningError(
                f"vertex {vertex} influence fields are invalid"
            )
        bone_id = safe_id(influence.get("bone"), f"vertex {vertex} bone id")
        if bone_id not in rig._bone_index:
            raise MeshSkinningError(
                f"vertex {vertex} references unknown bone: {bone_id}"
            )
        weight = number(influence.get("weight"), f"vertex {vertex} weight")
        if weight <= 0.0:
            raise MeshSkinningError(f"vertex {vertex} weight must be positive")
        result.append((rig._bone_index[bone_id], bone_id, weight))
    if len({item[0] for item in result}) != len(result):
        raise MeshSkinningError(f"vertex {vertex} repeats a bone influence")
    if not math.isclose(math.fsum(item[2] for item in result), 1.0,
                        rel_tol=0.0, abs_tol=WEIGHT_SUM_TOLERANCE):
        raise MeshSkinningError(f"vertex {vertex} weights must sum to one")
    return tuple((index, weight) for index, _bone, weight
                 in sorted(result, key=lambda item: item[1]))


def topological_ids(parents):
    children = {bone_id: [] for bone_id in parents}
    indegree = {bone_id: 0 for bone_id in parents}
    for bone_id, parent in parents.items():
        if parent is not None:
            if parent not in parents:
                raise MeshSkinningError(
                    f"bone {bone_id} references missing parent: {parent}"
                )
            children[parent].append(bone_id)
            indegree[bone_id] += 1
    ready = [bone_id for bone_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        bone_id = heapq.heappop(ready)
        order.append(bone_id)
        for child in sorted(children[bone_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    if len(order) != len(parents):
        raise MeshSkinningError("bone hierarchy contains a cycle")
    return tuple(order)


def matrix(bone, delta):
    angle = math.radians((bone.rotation_deg + delta) % 360.0)
    cosine, sine = math.cos(angle), math.sin(angle)
    return (cosine * bone.scale_x, sine * bone.scale_x,
            -sine * bone.scale_y, cosine * bone.scale_y, bone.x, bone.y)


def compose(parent, local):
    pa, pb, pc, pd, ptx, pty = parent
    la, lb, lc, ld, ltx, lty = local
    return (pa * la + pc * lb, pb * la + pd * lb,
            pa * lc + pc * ld, pb * lc + pd * ld,
            pa * ltx + pc * lty + ptx, pb * ltx + pd * lty + pty)


def inverse(value, bone_id):
    a, b, c, d, tx, ty = value
    determinant = a * d - b * c
    if not math.isfinite(determinant) or abs(determinant) <= 1e-18:
        raise MeshSkinningError(f"bone {bone_id} setup matrix is not invertible")
    ia, ib, ic, id_ = d / determinant, -b / determinant, -c / determinant, a / determinant
    return ia, ib, ic, id_, -(ia * tx + ic * ty), -(ib * tx + id_ * ty)


def apply(value, point):
    a, b, c, d, tx, ty = value
    return a * point[0] + c * point[1] + tx, b * point[0] + d * point[1] + ty


def finite_matrix(value, bone_id, label):
    if any(not math.isfinite(item) for item in value):
        raise MeshSkinningError(f"bone {bone_id} {label} matrix is non-finite")
    return value


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MeshSkinningError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise MeshSkinningError(f"{label} must be a finite number")
    return result


def safe_id(value, label):
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise MeshSkinningError(f"{label} is not a safe RigIR id")
    return value


def quantize(value):
    scaled = Decimal(str(value)) * QUANTIZATION_PER_PIXEL
    result = float(scaled.to_integral_value(
        rounding=ROUND_HALF_UP
    ) / QUANTIZATION_PER_PIXEL)
    if not math.isfinite(result):
        raise MeshSkinningError("quantized vertex is non-finite")
    return 0.0 if result == 0.0 else result


def sequence(value):
    return isinstance(value, Sequence) \
        and not isinstance(value, (str, bytes, bytearray))
