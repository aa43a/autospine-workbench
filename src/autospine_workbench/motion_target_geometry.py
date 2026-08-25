"""Shared canonical setup geometry for P5 target compilation and validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import math
from typing import Any

from .ik_target_geometry import derive_ik_handles
from .motion_roles import CANONICAL_BONE_ROLE_ITEMS
from .resolved_project import canonical_sha256
from .rig_fk import RigFkError, evaluate_world_setup


NUMERIC_PRECISION_DECIMALS = 12
GEOMETRY_TOLERANCE_PX = 1e-8


class MotionTargetGeometryError(ValueError):
    """Raised when canonical humanoid setup geometry is incomplete or ambiguous."""

@dataclass(frozen=True, slots=True)
class MotionSetupGeometry:
    """Frozen isolated projections rebuilt from one canonical 17-bone setup."""

    _bones_json: str
    _handles_json: str
    _body_frame_json: str

    @property
    def bones(self) -> list[dict[str, Any]]:
        return json.loads(self._bones_json)

    @property
    def ik_handles(self) -> list[dict[str, Any]]:
        return json.loads(self._handles_json)

    @property
    def body_frame(self) -> dict[str, Any]:
        return json.loads(self._body_frame_json)


def expected_parent_id(bone_id: str) -> str | None:
    """Return the fixed humanoid-v1 parent without duplicating its role map."""

    fixed = {
        "root-pelvis": None,
        "pelvis-spine": "root-pelvis",
        "spine-chest": "pelvis-spine",
        "chest-neck": "spine-chest",
        "neck-head": "chest-neck",
    }
    if bone_id in fixed:
        return fixed[bone_id]
    try:
        prefix, side = bone_id.rsplit(".", 1)
    except ValueError as exc:
        raise MotionTargetGeometryError(
            f"Unsupported canonical bone id: {bone_id}"
        ) from exc
    parents = {
        "chest-shoulder": "spine-chest",
        "upper-arm": f"chest-shoulder.{side}",
        "forearm": f"upper-arm.{side}",
        "pelvis-hip": "root-pelvis",
        "thigh": f"pelvis-hip.{side}",
        "calf": f"thigh.{side}",
    }
    if side not in {"left", "right"} or prefix not in parents:
        raise MotionTargetGeometryError(f"Unsupported canonical bone id: {bone_id}")
    return parents[prefix]


def derive_motion_setup_from_rig_bones(value: Any) -> MotionSetupGeometry:
    """Project P3 RigIR bones and reproduce P4 handles plus the P5 body frame."""

    try:
        indexed = _index_bones(value)
        world = evaluate_world_setup(list(indexed.values()))
        rows = []
        for role, bone_id in CANONICAL_BONE_ROLE_ITEMS:
            bone = indexed[bone_id]
            parent = expected_parent_id(bone_id)
            if bone.get("parent") != parent:
                raise MotionTargetGeometryError(
                    f"Canonical P3 parent differs: {bone_id}"
                )
            setup = _setup(bone, bone_id)
            values = {
                field: _number(setup.get(field), f"{bone_id}.{field}")
                for field in (
                    "x", "y", "rotation_deg", "scale_x", "scale_y", "length"
                )
            }
            if values["scale_x"] != 1.0 or values["scale_y"] != 1.0 \
                    or values["length"] <= 0:
                raise MotionTargetGeometryError(
                    "Canonical P3 bones require positive unit scale"
                )
            if parent is not None and _distance(
                world[bone_id]["origin_xy"], world[parent]["endpoint_xy"]
            ) > GEOMETRY_TOLERANCE_PX:
                raise MotionTargetGeometryError(
                    f"Canonical P3 hierarchy is disconnected: {bone_id}"
                )
            rows.append({
                "role": role,
                "bone_id": bone_id,
                "parent_bone_id": parent,
                "setup_local": {
                    "x": quantize(values["x"]),
                    "y": quantize(values["y"]),
                    "rotation_deg": quantize(values["rotation_deg"]),
                    "scale_x": 1.0,
                    "scale_y": 1.0,
                    "length_px": quantize(values["length"]),
                },
            })
        handles = derive_ik_handles({"bones": list(indexed.values())})
        body_frame = _derive_body_frame(world)
        return MotionSetupGeometry(
            _encode(rows), _encode(handles), _encode(body_frame)
        )
    except MotionTargetGeometryError:
        raise
    except (RigFkError, KeyError, TypeError, ValueError) as exc:
        raise MotionTargetGeometryError(
            f"Canonical motion setup geometry failed: {exc}"
        ) from exc


def derive_motion_setup_from_projection(value: Any) -> MotionSetupGeometry:
    """Rebuild world geometry from the standalone 17-row local projection."""

    if not isinstance(value, list) or len(value) != len(CANONICAL_BONE_ROLE_ITEMS):
        raise MotionTargetGeometryError("Motion target bones must contain 17 entries")
    rig_bones = []
    for index, ((role, bone_id), raw) in enumerate(
        zip(CANONICAL_BONE_ROLE_ITEMS, value)
    ):
        if not isinstance(raw, Mapping) or set(raw) != {
            "role", "bone_id", "parent_bone_id", "setup_local",
        }:
            raise MotionTargetGeometryError(f"Motion target bone {index} is invalid")
        parent = expected_parent_id(bone_id)
        if (raw.get("role"), raw.get("bone_id"), raw.get("parent_bone_id")) != \
                (role, bone_id, parent):
            raise MotionTargetGeometryError(
                "Motion target bone role, id, order, or parent is invalid"
            )
        setup = raw.get("setup_local")
        if not isinstance(setup, Mapping) or set(setup) != {
            "x", "y", "rotation_deg", "scale_x", "scale_y", "length_px",
        }:
            raise MotionTargetGeometryError(
                f"Motion target bone setup is invalid: {bone_id}"
            )
        rig_bones.append({
            "id": bone_id,
            "parent": parent,
            "setup": {
                "x": setup.get("x"), "y": setup.get("y"),
                "rotation_deg": setup.get("rotation_deg"),
                "scale_x": setup.get("scale_x"),
                "scale_y": setup.get("scale_y"),
                "length": setup.get("length_px"),
            },
        })
    result = derive_motion_setup_from_rig_bones(rig_bones)
    if canonical_sha256(value) != canonical_sha256(result.bones):
        raise MotionTargetGeometryError(
            "Motion target bone projection is not canonical"
        )
    return result


def _index_bones(value: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise MotionTargetGeometryError("Verified P3 bone inventory is invalid")
    result = {}
    for bone in value:
        if not isinstance(bone, Mapping) or not isinstance(bone.get("id"), str) \
                or bone["id"] in result:
            raise MotionTargetGeometryError("Verified P3 bone inventory is invalid")
        result[bone["id"]] = bone
    expected = {bone_id for _role, bone_id in CANONICAL_BONE_ROLE_ITEMS}
    if set(result) != expected:
        raise MotionTargetGeometryError(
            "Verified P3 must contain exactly 17 humanoid-v1 bones"
        )
    return result


def _derive_body_frame(world):
    pelvis = _world_point(world, "pelvis-spine", "origin_xy")
    chest = _world_point(world, "spine-chest", "endpoint_xy")
    shoulders = {
        side: _world_point(world, f"chest-shoulder.{side}", "endpoint_xy")
        for side in ("left", "right")
    }
    up = _unit((chest[0] - pelvis[0], chest[1] - pelvis[1]), "pelvis-chest")
    outward = {
        side: _outward(chest, shoulders[side], up, side) for side in shoulders
    }
    if _dot(outward["left"], outward["right"]) > -0.5:
        raise MotionTargetGeometryError("Character-side shoulder axes are not opposed")
    return {
        "method": "pelvis-chest-shoulder-gram-schmidt-v1",
        "side_source": "canonical-character-side",
        "screen_x_inference": False,
        "pelvis_xy": _q_point(pelvis),
        "chest_xy": _q_point(chest),
        "shoulder_xy_by_side": {
            side: _q_point(shoulders[side]) for side in ("left", "right")
        },
        "up_xy": _q_point(up),
        "left_outward_xy": _q_point(outward["left"]),
        "right_outward_xy": _q_point(outward["right"]),
    }


def _outward(chest, shoulder, up, label):
    raw = shoulder[0] - chest[0], shoulder[1] - chest[1]
    along = _dot(raw, up)
    return _unit((raw[0] - along * up[0], raw[1] - along * up[1]), label)


def _unit(value, label):
    length = math.hypot(*value)
    if length <= GEOMETRY_TOLERANCE_PX:
        raise MotionTargetGeometryError(f"Body frame axis is degenerate: {label}")
    return value[0] / length, value[1] / length


def _setup(bone, bone_id):
    setup = bone.get("setup")
    if not isinstance(setup, Mapping):
        raise MotionTargetGeometryError(f"Canonical P3 setup is invalid: {bone_id}")
    return setup


def _world_point(world, bone_id, field):
    return tuple(_number(value, f"{bone_id}.{field}") for value in world[bone_id][field])


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise MotionTargetGeometryError(f"Canonical P3 number is invalid: {label}")
    return float(value)


def quantize(value):
    threshold = 10 ** -NUMERIC_PRECISION_DECIMALS
    return 0.0 if abs(value) <= threshold else float(
        round(value, NUMERIC_PRECISION_DECIMALS)
    )


def _q_point(value): return [quantize(value[0]), quantize(value[1])]
def _distance(left, right): return math.hypot(left[0] - right[0], left[1] - right[1])
def _dot(left, right): return left[0] * right[0] + left[1] * right[1]
def _encode(value): return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))
