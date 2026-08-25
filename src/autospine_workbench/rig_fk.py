"""Deterministic setup-pose FK for the version-neutral RigIR contract."""

from __future__ import annotations

import heapq
import math
from typing import Any, Mapping, Sequence


class RigFkError(ValueError):
    """Raised when source skeleton or RigIR setup transforms are not usable."""


def local_to_world_point(
    point_xy: Sequence[float],
    origin_xy: Sequence[float],
    rotation_deg: float,
    scale_xy: Sequence[float] = (1.0, 1.0),
) -> tuple[float, float]:
    """Transform a point from a bone-local frame into its world frame."""

    px, py = _point(point_xy, "point_xy")
    ox, oy = _point(origin_xy, "origin_xy")
    sx, sy = _scale(scale_xy)
    angle = math.radians(_number(rotation_deg, "rotation_deg"))
    cosine, sine = math.cos(angle), math.sin(angle)
    return (
        ox + cosine * px * sx - sine * py * sy,
        oy + sine * px * sx + cosine * py * sy,
    )


def world_to_local_point(
    point_xy: Sequence[float],
    origin_xy: Sequence[float],
    rotation_deg: float,
    scale_xy: Sequence[float] = (1.0, 1.0),
) -> tuple[float, float]:
    """Transform a world point into a bone-local frame."""

    px, py = _point(point_xy, "point_xy")
    ox, oy = _point(origin_xy, "origin_xy")
    sx, sy = _scale(scale_xy)
    angle = math.radians(-_number(rotation_deg, "rotation_deg"))
    cosine, sine = math.cos(angle), math.sin(angle)
    dx, dy = px - ox, py - oy
    return ((cosine * dx - sine * dy) / sx, (sine * dx + cosine * dy) / sy)


def compile_setup_bones(skeleton: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Compile absolute reviewed joints and source bone links to local RigIR setup."""

    if not isinstance(skeleton, Mapping):
        raise RigFkError("skeleton must be an object")
    joints = _indexed_objects(skeleton.get("joints"), "joint")
    sources = _indexed_objects(skeleton.get("bones"), "bone")
    joint_points = {
        item_id: (_number(item.get("x"), f"joint {item_id}.x"), _number(item.get("y"), f"joint {item_id}.y"))
        for item_id, item in joints.items()
    }

    parents: dict[str, str | None] = {}
    endpoints: dict[str, tuple[str, str]] = {}
    for bone_id, bone in sources.items():
        parent = bone.get("parent_id")
        if parent is not None and not isinstance(parent, str):
            raise RigFkError(f"bone {bone_id}.parent_id must be a string or null")
        start, end = bone.get("start_joint_id"), bone.get("end_joint_id")
        if not isinstance(start, str) or not isinstance(end, str):
            raise RigFkError(f"bone {bone_id} must name start and end joints")
        missing = [joint_id for joint_id in (start, end) if joint_id not in joints]
        if missing:
            raise RigFkError(f"bone {bone_id} references missing joint(s): {', '.join(missing)}")
        parents[bone_id] = parent
        endpoints[bone_id] = (start, end)

    order = _topological_ids(parents, "bone")
    result: list[dict[str, Any]] = []
    world_frames: dict[str, tuple[tuple[float, float], float]] = {}
    for bone_id in order:
        start_id, end_id = endpoints[bone_id]
        start, end = joint_points[start_id], joint_points[end_id]
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if not math.isfinite(length) or length <= 1e-9:
            raise RigFkError(f"bone {bone_id} has zero or non-finite length")
        world_rotation = math.degrees(math.atan2(dy, dx))
        parent = parents[bone_id]
        if parent is None:
            local_xy, local_rotation = start, world_rotation
        else:
            parent_origin, parent_rotation = world_frames[parent]
            local_xy = world_to_local_point(start, parent_origin, parent_rotation)
            local_rotation = _normalize_angle(world_rotation - parent_rotation)
        result.append(
            {
                "id": bone_id,
                "parent": parent,
                "setup": {
                    "x": _clean(local_xy[0]),
                    "y": _clean(local_xy[1]),
                    "rotation_deg": _clean(local_rotation),
                    "scale_x": 1.0,
                    "scale_y": 1.0,
                    "length": _clean(length),
                },
                "inference": _bone_inference(joints[start_id], joints[end_id]),
            }
        )
        world_frames[bone_id] = (start, world_rotation)
    return result


def evaluate_world_setup(rig_bones: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Evaluate RigIR setup bones and return world origin, angle, and endpoint by id."""

    bones = _indexed_objects(rig_bones, "bone")
    parents: dict[str, str | None] = {}
    local_matrices: dict[str, tuple[float, float, float, float, float, float]] = {}
    lengths: dict[str, float] = {}
    for bone_id, bone in bones.items():
        parent = bone.get("parent")
        if parent is not None and not isinstance(parent, str):
            raise RigFkError(f"bone {bone_id}.parent must be a string or null")
        setup = bone.get("setup")
        if not isinstance(setup, Mapping):
            raise RigFkError(f"bone {bone_id}.setup must be an object")
        x = _number(setup.get("x"), f"bone {bone_id}.setup.x")
        y = _number(setup.get("y"), f"bone {bone_id}.setup.y")
        rotation = _number(setup.get("rotation_deg"), f"bone {bone_id}.setup.rotation_deg")
        scale_x = _number(setup.get("scale_x"), f"bone {bone_id}.setup.scale_x")
        scale_y = _number(setup.get("scale_y"), f"bone {bone_id}.setup.scale_y")
        if abs(scale_x) <= 1e-12 or abs(scale_y) <= 1e-12:
            raise RigFkError(f"bone {bone_id} has a zero setup scale")
        length = _number(setup.get("length"), f"bone {bone_id}.setup.length")
        if length <= 1e-9:
            raise RigFkError(f"bone {bone_id} has zero length")
        parents[bone_id] = parent
        local_matrices[bone_id] = _matrix(x, y, rotation, scale_x, scale_y)
        lengths[bone_id] = length

    order = _topological_ids(parents, "bone")
    matrices: dict[str, tuple[float, float, float, float, float, float]] = {}
    result: dict[str, dict[str, Any]] = {}
    for bone_id in order:
        parent = parents[bone_id]
        matrix = local_matrices[bone_id]
        if parent is not None:
            matrix = _compose(matrices[parent], matrix)
        a, b, _c, _d, tx, ty = matrix
        endpoint = (tx + a * lengths[bone_id], ty + b * lengths[bone_id])
        result[bone_id] = {
            "origin_xy": [_clean(tx), _clean(ty)],
            "rotation_deg": _clean(_normalize_angle(math.degrees(math.atan2(b, a)))),
            "endpoint_xy": [_clean(endpoint[0]), _clean(endpoint[1])],
        }
        matrices[bone_id] = matrix
    return result


def _indexed_objects(value: Any, label: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise RigFkError(f"{label}s must be an array")
    result: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise RigFkError(f"{label} {index} must be an object")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise RigFkError(f"{label} {index} has an invalid id")
        if item_id in result:
            raise RigFkError(f"duplicate {label} id: {item_id}")
        result[item_id] = item
    return result


def _topological_ids(parents: Mapping[str, str | None], label: str) -> list[str]:
    children = {item_id: [] for item_id in parents}
    indegree = {item_id: 0 for item_id in parents}
    for item_id, parent in parents.items():
        if parent is not None:
            if parent not in parents:
                raise RigFkError(f"{label} {item_id} references missing parent: {parent}")
            if parent == item_id:
                raise RigFkError(f"{label} {item_id} cannot parent itself")
            children[parent].append(item_id)
            indegree[item_id] += 1
    ready = [item_id for item_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        item_id = heapq.heappop(ready)
        order.append(item_id)
        for child in sorted(children[item_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    if len(order) != len(parents):
        raise RigFkError(f"{label} hierarchy contains a cycle")
    return order


def _bone_inference(start: Mapping[str, Any], end: Mapping[str, Any]) -> dict[str, Any]:
    methods = {_joint_method(start), _joint_method(end)}
    if methods == {"manual"}:
        method = "manual"
    elif "template" in methods:
        method = "template"
    elif "overlap" in methods:
        method = "overlap"
    else:
        method = "landmark"
    confidence = min(_confidence(start), _confidence(end))
    return {"method": method, "confidence": _clean(confidence)}


def _joint_method(joint: Mapping[str, Any]) -> str:
    decision = str(joint.get("decision_kind") or "").lower()
    if decision in {"manual_absolute", "candidate_adjust"}:
        return "manual"
    tokens = " ".join(
        str(joint.get(key) or "").lower()
        for key in ("source", "decision_kind", "candidate_source", "provider_id")
    )
    if "overlap" in tokens or "contact" in tokens or "alpha" in tokens:
        return "overlap"
    if any(token in tokens for token in ("pose", "landmark", "detector", "coco")):
        return "landmark"
    return "template"


def _confidence(joint: Mapping[str, Any]) -> float:
    raw = joint.get("model_confidence", joint.get("confidence", 0.0))
    value = _number(raw, f"joint {joint.get('id')}.confidence")
    if not 0.0 <= value <= 1.0:
        raise RigFkError(f"joint {joint.get('id')} confidence is outside [0, 1]")
    return value


def _matrix(x: float, y: float, rotation: float, sx: float, sy: float) -> tuple[float, ...]:
    angle = math.radians(rotation)
    cosine, sine = math.cos(angle), math.sin(angle)
    return cosine * sx, sine * sx, -sine * sy, cosine * sy, x, y


def _compose(parent: tuple[float, ...], local: tuple[float, ...]) -> tuple[float, ...]:
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


def _point(value: Sequence[float], label: str) -> tuple[float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise RigFkError(f"{label} must contain two numbers")
    return _number(value[0], f"{label}[0]"), _number(value[1], f"{label}[1]")


def _scale(value: Sequence[float]) -> tuple[float, float]:
    sx, sy = _point(value, "scale_xy")
    if abs(sx) <= 1e-12 or abs(sy) <= 1e-12:
        raise RigFkError("scale_xy must be non-zero")
    return sx, sy


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RigFkError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise RigFkError(f"{label} must be a finite number")
    return result


def _normalize_angle(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def _clean(value: float) -> float:
    return 0.0 if abs(value) <= 1e-12 else float(value)
