"""Canonical geometry derivation for P4 two-bone IK target handles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

from .ik_setup_local import solve_setup_local_ik
from .rig_fk import RigFkError, evaluate_world_setup


PROFILE_FORMAT = "autospine-ik-target-profile"
PROFILE_VERSION = 1
SOLVER_ID = "autospine-two-bone-analytic"
SOLVER_VERSION = "1.0.0"
SOURCE_IDENTITY_FIELDS = (
    "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
    "resolved_project_sha256", "rig_sha256", "run_sha256",
    "probes_sha256", "visuals_sha256", "bundle_sha256",
)
HANDLE_SPECS = (
    ("arm.left", "arm", "left", "upper-arm.left", "forearm.left"),
    ("arm.right", "arm", "right", "upper-arm.right", "forearm.right"),
    ("leg.left", "leg", "left", "thigh.left", "calf.left"),
    ("leg.right", "leg", "right", "thigh.right", "calf.right"),
)
NUMERIC_PRECISION_DECIMALS = 12
POSITION_TOLERANCE_PX = 1e-8
ROTATION_TOLERANCE_DEG = 1e-8
COLLINEAR_SINE_EPSILON = 1e-8
BEND_SOURCE = "setup.aim_cross_elbow"
FALLBACK_SOURCE = "setup.root_to_effector"


class IkTargetGeometryError(ValueError):
    """Raised when a RigIR setup cannot define an unambiguous rigid IK chain."""


def solver_config() -> dict[str, Any]:
    """Return a fresh pinned analytic rigid-chain solver configuration."""

    return {
        "rigid_chain_scale": "positive-unit-only",
        "reach_policy": "clamp-to-kinematic-range",
        "kinematic_reach_semantics": "bone-length-only-not-mesh-visual-safe-range",
        "bend_rule": "sign(aim_cross_elbow)",
        "collinear_setup_policy": "reject",
        "setup_roundtrip_policy": "hinge-and-zero-local-delta",
        "numeric_precision_decimals": NUMERIC_PRECISION_DECIMALS,
        "position_tolerance_px": POSITION_TOLERANCE_PX,
        "rotation_tolerance_deg": ROTATION_TOLERANCE_DEG,
        "collinear_sine_epsilon": COLLINEAR_SINE_EPSILON,
    }


def derive_ik_handles(rig: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Derive the four canonical handles from one already verified P3 RigIR."""

    if not isinstance(rig, Mapping):
        raise IkTargetGeometryError("P3 RigIR must be an object")
    bones = _bone_index(rig.get("bones"))
    try:
        world = evaluate_world_setup(list(bones.values()))
    except (RigFkError, KeyError, TypeError, ValueError) as exc:
        raise IkTargetGeometryError(f"P3 RigIR setup FK is invalid: {exc}") from exc
    result = []
    for handle_id, limb, side, proximal_id, distal_id in HANDLE_SPECS:
        result.append(_derive_handle(
            handle_id, limb, side, proximal_id, distal_id, bones, world
        ))
    return result


def _derive_handle(handle_id, limb, side, proximal_id, distal_id, bones, world):
    proximal = bones.get(proximal_id)
    distal = bones.get(distal_id)
    if proximal is None or distal is None:
        raise IkTargetGeometryError(f"Canonical IK chain is missing: {handle_id}")
    if distal.get("parent") != proximal_id:
        raise IkTargetGeometryError(f"Canonical IK chain is not direct: {handle_id}")
    _require_unit_scale_ancestry(proximal_id, bones, handle_id)
    _require_unit_scale_ancestry(distal_id, bones, handle_id)

    root = _world_point(world, proximal_id, "origin_xy")
    proximal_end = _world_point(world, proximal_id, "endpoint_xy")
    hinge = _world_point(world, distal_id, "origin_xy")
    effector = _world_point(world, distal_id, "endpoint_xy")
    if _distance(proximal_end, hinge) > POSITION_TOLERANCE_PX:
        raise IkTargetGeometryError(f"Canonical IK hinge is disconnected: {handle_id}")
    proximal_length = _distance(root, hinge)
    distal_length = _distance(hinge, effector)
    if min(proximal_length, distal_length) <= POSITION_TOLERANCE_PX:
        raise IkTargetGeometryError(f"Canonical IK chain has zero length: {handle_id}")
    aim = (effector[0] - root[0], effector[1] - root[1])
    aim_length = math.hypot(*aim)
    if aim_length <= POSITION_TOLERANCE_PX:
        raise IkTargetGeometryError(f"Canonical IK setup aim is degenerate: {handle_id}")
    elbow = (hinge[0] - root[0], hinge[1] - root[1])
    cross = aim[0] * elbow[1] - aim[1] * elbow[0]
    sine = cross / (aim_length * proximal_length)
    if abs(sine) <= COLLINEAR_SINE_EPSILON:
        raise IkTargetGeometryError(f"Canonical IK setup is collinear: {handle_id}")
    bend = "positive" if cross > 0 else "negative"
    fallback = (aim[0] / aim_length, aim[1] / aim_length)
    proximal_setup = _setup(proximal, proximal_id)
    distal_setup = _setup(distal, distal_id)
    proximal_parent_id = proximal.get("parent")
    if not isinstance(proximal_parent_id, str) or proximal_parent_id not in world:
        raise IkTargetGeometryError(
            f"Canonical IK proximal parent is missing: {handle_id}"
        )
    angles = {
        "proximal_parent_world": _q(_world_angle(world, proximal_parent_id)),
        "proximal_world": _q(_world_angle(world, proximal_id)),
        "distal_world": _q(_world_angle(world, distal_id)),
        "proximal_local": _q(_number(proximal_setup.get("rotation_deg"), proximal_id)),
        "distal_local": _q(_number(distal_setup.get("rotation_deg"), distal_id)),
    }
    handle = {
        "id": handle_id, "limb": limb, "side": side,
        "proximal_bone_id": proximal_id, "distal_bone_id": distal_id,
        "root_xy": _q_point(root), "hinge_xy": _q_point(hinge),
        "setup_effector_xy": _q_point(effector),
        "proximal_length_px": _q(proximal_length),
        "distal_length_px": _q(distal_length),
        "kinematic_reach": {
            "minimum_px": _q(abs(proximal_length - distal_length)),
            "maximum_px": _q(proximal_length + distal_length),
        },
        "setup_angles_deg": angles,
        "bend_direction": bend, "bend_source": BEND_SOURCE,
        "fallback_direction": {
            "source": FALLBACK_SOURCE, "xy": _q_point(fallback),
        },
    }
    _require_setup_roundtrip(handle)
    return handle


def _require_setup_roundtrip(handle: Mapping[str, Any]) -> None:
    angles = handle["setup_angles_deg"]
    fallback = handle["fallback_direction"]["xy"]
    solved = solve_setup_local_ik(
        handle["root_xy"],
        proximal_length=handle["proximal_length_px"],
        distal_length=handle["distal_length_px"],
        target_xy=handle["setup_effector_xy"],
        bend_direction=handle["bend_direction"],
        fallback_direction_xy=fallback,
        setup_proximal_world_rotation_deg=angles["proximal_world"],
        setup_distal_local_rotation_deg=angles["distal_local"],
    )
    if solved.world.reach_state != "reachable" or \
            _distance(solved.world.elbow_xy, handle["hinge_xy"]) > POSITION_TOLERANCE_PX or \
            _distance(solved.world.resolved_target_xy, handle["setup_effector_xy"]) > POSITION_TOLERANCE_PX or \
            abs(solved.proximal_rotation_delta_deg) > ROTATION_TOLERANCE_DEG or \
            abs(solved.distal_rotation_delta_deg) > ROTATION_TOLERANCE_DEG:
        raise IkTargetGeometryError(
            f"Canonical IK setup roundtrip failed: {handle.get('id')}"
        )


def _require_unit_scale_ancestry(bone_id, bones, handle_id):
    seen = set()
    current = bone_id
    while current is not None:
        if current in seen or current not in bones:
            raise IkTargetGeometryError(f"Canonical IK ancestry is invalid: {handle_id}")
        seen.add(current)
        bone = bones[current]
        setup = _setup(bone, current)
        for field in ("scale_x", "scale_y"):
            if _number(setup.get(field), f"{current}.{field}") != 1.0:
                raise IkTargetGeometryError(
                    f"Canonical IK chain requires +1 setup scales: {handle_id}"
                )
        parent = bone.get("parent")
        if parent is not None and not isinstance(parent, str):
            raise IkTargetGeometryError(f"Canonical IK ancestry is invalid: {handle_id}")
        current = parent


def _bone_index(value: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise IkTargetGeometryError("P3 RigIR bones must be an array")
    result = {}
    for bone in value:
        if not isinstance(bone, Mapping) or not isinstance(bone.get("id"), str):
            raise IkTargetGeometryError("P3 RigIR bone inventory is invalid")
        if bone["id"] in result:
            raise IkTargetGeometryError("P3 RigIR bone ids are duplicated")
        result[bone["id"]] = bone
    return result


def _setup(bone, bone_id):
    setup = bone.get("setup")
    if not isinstance(setup, Mapping):
        raise IkTargetGeometryError(f"P3 RigIR bone setup is invalid: {bone_id}")
    return setup


def _world_point(world, bone_id, field):
    return tuple(_number(value, f"{bone_id}.{field}") for value in world[bone_id][field])


def _world_angle(world, bone_id):
    return _number(world[bone_id]["rotation_deg"], f"{bone_id}.rotation_deg")


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise IkTargetGeometryError(f"P3 IK number is invalid: {label}")
    return float(value)


def _distance(left, right): return math.hypot(left[0] - right[0], left[1] - right[1])
def _q(value): return 0.0 if abs(value) <= 10 ** -NUMERIC_PRECISION_DECIMALS else float(round(value, NUMERIC_PRECISION_DECIMALS))
def _q_point(value): return [_q(value[0]), _q(value[1])]
