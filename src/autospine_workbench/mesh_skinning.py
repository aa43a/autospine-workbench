"""Deterministic two-bone linear-blend skinning in canvas coordinates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import heapq
import math
import re
from typing import Any, TypeAlias


QUANTIZATION_PER_PIXEL = 4096
_WEIGHT_SUM_TOLERANCE = 1e-9
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

Matrix: TypeAlias = tuple[float, float, float, float, float, float]
Point: TypeAlias = tuple[float, float]


class MeshSkinningError(ValueError):
    """Raised when a rig, pose, vertex, or influence cannot be skinned safely."""


@dataclass(frozen=True)
class _Bone:
    parent: str | None
    x: float
    y: float
    rotation_deg: float
    scale_x: float
    scale_y: float


def skin_vertices_lbs(
    rig_bones: Sequence[Mapping[str, Any]],
    vertices_xy: Sequence[Sequence[int | float]],
    weights: Sequence[Sequence[Mapping[str, Any]]],
    pose_rotation_deltas_deg: Mapping[str, int | float],
) -> tuple[Point, ...]:
    """Skin canvas-space bind vertices with one or two positive influences.

    For every influence this evaluates ``M_pose * inverse(M_setup) * bind``.
    The weighted result is quantized to 1/4096 px using decimal ROUND_HALF_UP.
    """

    bones, setup_world, pose_world = _compile_world_matrices(
        rig_bones, pose_rotation_deltas_deg
    )
    skin_matrices = {
        bone_id: _finite_matrix(
            _compose(pose_world[bone_id], _inverse(setup_world[bone_id], bone_id)),
            bone_id,
            "skinning",
        )
        for bone_id in bones
    }
    vertices = _vertices(vertices_xy)
    if not _sequence(weights) or len(weights) != len(vertices):
        raise MeshSkinningError("weights must match the vertex count")
    result: list[Point] = []
    for index, bind in enumerate(vertices):
        influences = _influences(weights[index], bones, index)
        x, y = 0.0, 0.0
        for bone_id, weight in influences:
            posed = _apply(skin_matrices[bone_id], bind)
            x += weight * posed[0]
            y += weight * posed[1]
        if not math.isfinite(x) or not math.isfinite(y):
            raise MeshSkinningError(f"vertex {index} produced a non-finite result")
        result.append((_quantize(x), _quantize(y)))
    return tuple(result)


def _compile_world_matrices(
    rig_bones: Sequence[Mapping[str, Any]],
    pose_rotation_deltas_deg: Mapping[str, int | float],
) -> tuple[dict[str, _Bone], dict[str, Matrix], dict[str, Matrix]]:
    bones = _bones(rig_bones)
    deltas = _pose_deltas(pose_rotation_deltas_deg, bones)
    parents = {bone_id: bone.parent for bone_id, bone in bones.items()}
    order = _topological_ids(parents)
    setup_world: dict[str, Matrix] = {}
    pose_world: dict[str, Matrix] = {}
    for bone_id in order:
        bone = bones[bone_id]
        setup = _matrix(bone, 0.0)
        pose = _matrix(bone, deltas.get(bone_id, 0.0))
        if bone.parent is not None:
            setup = _compose(setup_world[bone.parent], setup)
            pose = _compose(pose_world[bone.parent], pose)
        setup_world[bone_id] = _finite_matrix(setup, bone_id, "setup")
        pose_world[bone_id] = _finite_matrix(pose, bone_id, "pose")
    return bones, setup_world, pose_world


def _bones(value: Sequence[Mapping[str, Any]]) -> dict[str, _Bone]:
    if not _sequence(value) or not value:
        raise MeshSkinningError("rig_bones must be a non-empty array")
    result: dict[str, _Bone] = {}
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise MeshSkinningError(f"bone {index} must be an object")
        bone_id = _safe_id(item.get("id"), f"bone {index}.id")
        if bone_id in result:
            raise MeshSkinningError(f"bone {index} has an invalid or duplicate id")
        parent = item.get("parent")
        if parent is not None:
            parent = _safe_id(parent, f"bone {bone_id}.parent")
        setup = item.get("setup")
        if not isinstance(setup, Mapping):
            raise MeshSkinningError(f"bone {bone_id}.setup must be an object")
        length = _number(setup.get("length"), f"bone {bone_id}.setup.length")
        scale_x = _number(setup.get("scale_x"), f"bone {bone_id}.setup.scale_x")
        scale_y = _number(setup.get("scale_y"), f"bone {bone_id}.setup.scale_y")
        if length <= 1e-9:
            raise MeshSkinningError(f"bone {bone_id} has zero length")
        if scale_x <= 1e-12 or scale_y <= 1e-12:
            raise MeshSkinningError(f"bone {bone_id} scale must be positive")
        result[bone_id] = _Bone(
            parent=parent,
            x=_number(setup.get("x"), f"bone {bone_id}.setup.x"),
            y=_number(setup.get("y"), f"bone {bone_id}.setup.y"),
            rotation_deg=_number(
                setup.get("rotation_deg"), f"bone {bone_id}.setup.rotation_deg"
            ),
            scale_x=scale_x,
            scale_y=scale_y,
        )
    return result


def _pose_deltas(
    value: Mapping[str, int | float], bones: Mapping[str, _Bone]
) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise MeshSkinningError("pose_rotation_deltas_deg must be an object")
    result: dict[str, float] = {}
    for bone_id, delta in value.items():
        bone_id = _safe_id(bone_id, "pose bone id")
        if bone_id not in bones:
            raise MeshSkinningError(f"pose references unknown bone: {bone_id}")
        result[bone_id] = _number(delta, f"pose delta for bone {bone_id}")
    return result


def _vertices(value: Sequence[Sequence[int | float]]) -> tuple[Point, ...]:
    if not _sequence(value) or not value:
        raise MeshSkinningError("vertices_xy must be a non-empty array")
    result: list[Point] = []
    for index, point in enumerate(value):
        if not _sequence(point) or len(point) != 2:
            raise MeshSkinningError(f"vertex {index} must contain two coordinates")
        result.append(
            (_number(point[0], f"vertex {index}.x"), _number(point[1], f"vertex {index}.y"))
        )
    return tuple(result)


def _influences(
    value: Sequence[Mapping[str, Any]], bones: Mapping[str, _Bone], vertex: int
) -> tuple[tuple[str, float], ...]:
    if not _sequence(value) or len(value) not in (1, 2):
        raise MeshSkinningError(f"vertex {vertex} must have one or two influences")
    result: list[tuple[str, float]] = []
    for influence in value:
        if not isinstance(influence, Mapping) or set(influence) != {"bone", "weight"}:
            raise MeshSkinningError(f"vertex {vertex} influence fields are invalid")
        bone_id = _safe_id(influence.get("bone"), f"vertex {vertex} bone id")
        if bone_id not in bones:
            raise MeshSkinningError(f"vertex {vertex} references unknown bone: {bone_id}")
        weight = _number(influence.get("weight"), f"vertex {vertex} weight")
        if weight <= 0.0:
            raise MeshSkinningError(f"vertex {vertex} weight must be positive")
        result.append((bone_id, weight))
    if len({bone_id for bone_id, _weight in result}) != len(result):
        raise MeshSkinningError(f"vertex {vertex} repeats a bone influence")
    if not math.isclose(
        math.fsum(weight for _bone, weight in result),
        1.0,
        rel_tol=0.0,
        abs_tol=_WEIGHT_SUM_TOLERANCE,
    ):
        raise MeshSkinningError(f"vertex {vertex} weights must sum to one")
    return tuple(sorted(result))


def _topological_ids(parents: Mapping[str, str | None]) -> tuple[str, ...]:
    children = {bone_id: [] for bone_id in parents}
    indegree = {bone_id: 0 for bone_id in parents}
    for bone_id, parent in parents.items():
        if parent is not None:
            if parent not in parents:
                raise MeshSkinningError(f"bone {bone_id} references missing parent: {parent}")
            children[parent].append(bone_id)
            indegree[bone_id] += 1
    ready = [bone_id for bone_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
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


def _matrix(bone: _Bone, rotation_delta: float) -> Matrix:
    angle = math.radians((bone.rotation_deg + rotation_delta) % 360.0)
    cosine, sine = math.cos(angle), math.sin(angle)
    return (
        cosine * bone.scale_x,
        sine * bone.scale_x,
        -sine * bone.scale_y,
        cosine * bone.scale_y,
        bone.x,
        bone.y,
    )


def _compose(parent: Matrix, local: Matrix) -> Matrix:
    pa, pb, pc, pd, ptx, pty = parent
    la, lb, lc, ld, ltx, lty = local
    return (
        pa * la + pc * lb,
        pb * la + pd * lb,
        pa * lc + pc * ld,
        pb * lc + pd * ld,
        pa * ltx + pc * lty + ptx,
        pb * ltx + pd * lty + pty,
    )


def _inverse(matrix: Matrix, bone_id: str) -> Matrix:
    a, b, c, d, tx, ty = matrix
    determinant = a * d - b * c
    if not math.isfinite(determinant) or abs(determinant) <= 1e-18:
        raise MeshSkinningError(f"bone {bone_id} setup matrix is not invertible")
    inverse = (d / determinant, -b / determinant, -c / determinant, a / determinant)
    ia, ib, ic, id_ = inverse
    return ia, ib, ic, id_, -(ia * tx + ic * ty), -(ib * tx + id_ * ty)


def _apply(matrix: Matrix, point: Point) -> Point:
    a, b, c, d, tx, ty = matrix
    return a * point[0] + c * point[1] + tx, b * point[0] + d * point[1] + ty


def _finite_matrix(matrix: Matrix, bone_id: str, label: str) -> Matrix:
    if any(not math.isfinite(value) for value in matrix):
        raise MeshSkinningError(f"bone {bone_id} {label} matrix is non-finite")
    return matrix


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MeshSkinningError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise MeshSkinningError(f"{label} must be a finite number")
    return result


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise MeshSkinningError(f"{label} is not a safe RigIR id")
    return value


def _quantize(value: float) -> float:
    scaled = Decimal(str(value)) * QUANTIZATION_PER_PIXEL
    result = float(
        scaled.to_integral_value(rounding=ROUND_HALF_UP) / QUANTIZATION_PER_PIXEL
    )
    if not math.isfinite(result):
        raise MeshSkinningError("quantized vertex is non-finite")
    return 0.0 if result == 0.0 else result


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
