"""Deterministic sampling and target-space IK for MotionIR retargeting."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any

from .ik_probe_math import quantize, quantize_point
from .ik_setup_local import solve_setup_local_ik
from .motion_roles import CANONICAL_BONE_ID_BY_ROLE
from .motion_target_validation import require_motion_target_profile
from .motion_validation import require_motion_ir
from .rig_fk import evaluate_world_setup


class MotionRetargetKinematicsError(ValueError):
    """Raised when a validated motion cannot be sampled on a target setup."""


@dataclass(frozen=True, slots=True)
class RetargetIkSample:
    """One target request and its finite setup-local analytic solution."""

    tick: int
    source_value: str | tuple[float, float]
    root_xy: tuple[float, float]
    requested_target_xy: tuple[float, float]
    resolved_target_xy: tuple[float, float]
    proximal_rotation_delta_deg: float
    distal_rotation_delta_deg: float
    reach_state: str
    requested_distance_px: float
    minimum_reach_px: float
    maximum_reach_px: float


@dataclass(frozen=True, slots=True)
class RetargetIkTrack:
    """The two concrete target-bone tracks derived from one IK handle track."""

    handle_id: str
    proximal_bone_id: str
    distal_bone_id: str
    samples: tuple[RetargetIkSample, ...]


def solve_motion_ik_track(
    motion_ir: Mapping[str, Any],
    target_profile: Mapping[str, Any],
    handle_id: str,
) -> RetargetIkTrack:
    """Solve every key of one exact MotionIR handle against animated ancestors."""

    try:
        require_motion_ir(motion_ir)
        require_motion_target_profile(target_profile)
        source = _handle_track(motion_ir, handle_id)
        handle = _handle(target_profile, handle_id)
        samples = tuple(
            _solve_key(motion_ir, target_profile, handle, key)
            for key in source["keys"]
        )
        return RetargetIkTrack(
            handle_id=handle_id,
            proximal_bone_id=str(handle["proximal_bone_id"]),
            distal_bone_id=str(handle["distal_bone_id"]),
            samples=samples,
        )
    except MotionRetargetKinematicsError:
        raise
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise MotionRetargetKinematicsError(
            f"Motion IK retargeting failed: {exc}"
        ) from exc


def sample_motion_pose(
    motion_ir: Mapping[str, Any],
    target_profile: Mapping[str, Any],
    tick: int,
) -> dict[str, dict[str, Any]]:
    """Evaluate target setup with all non-IK MotionIR tracks at one tick."""

    try:
        require_motion_ir(motion_ir)
        require_motion_target_profile(target_profile)
        return _sample_motion_pose(motion_ir, target_profile, tick)
    except MotionRetargetKinematicsError:
        raise
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise MotionRetargetKinematicsError(
            f"Motion pose sampling failed: {exc}"
        ) from exc


def _sample_motion_pose(motion_ir, target_profile, tick):

    if type(tick) is not int or not 0 <= tick <= motion_ir.get("duration_ticks", -1):
        raise MotionRetargetKinematicsError("Motion sample tick is invalid")
    rotations: dict[str, float] = {}
    translation = (0.0, 0.0)
    reference = _number(
        target_profile["reference_length"]["value_px"], "reference length"
    )
    for track in motion_ir["tracks"]:
        if track["target_kind"] != "bone_role":
            continue
        value = _sample_keys(track["keys"], tick)
        bone_id = CANONICAL_BONE_ID_BY_ROLE[track["target"]]
        if track["property"] == "rotation":
            rotations[bone_id] = _number(value, "sampled rotation")
        elif bone_id == "root-pelvis":
            vector = _vector(value, "sampled root translation")
            translation = vector[0] * reference, vector[1] * reference
    rig_bones = []
    for row in target_profile["bones"]:
        setup = row["setup_local"]
        bone_id = row["bone_id"]
        x, y = _number(setup["x"], "setup x"), _number(setup["y"], "setup y")
        if bone_id == "root-pelvis":
            x, y = x + translation[0], y + translation[1]
        rig_bones.append({
            "id": bone_id,
            "parent": row["parent_bone_id"],
            "setup": {
                "x": x,
                "y": y,
                "rotation_deg": _number(setup["rotation_deg"], "setup rotation")
                + rotations.get(bone_id, 0.0),
                "scale_x": 1.0,
                "scale_y": 1.0,
                "length": _number(setup["length_px"], "setup length"),
            },
        })
    return evaluate_world_setup(rig_bones)


def _solve_key(motion, profile, handle, key) -> RetargetIkSample:
    tick = key["tick"]
    pose = _sample_motion_pose(motion, profile, tick)
    proximal_id, distal_id = handle["proximal_bone_id"], handle["distal_bone_id"]
    root = tuple(pose[proximal_id]["origin_xy"])
    value = key["value"]
    if value == "setup":
        target = tuple(pose[distal_id]["endpoint_xy"])
        source_value: str | tuple[float, float] = "setup"
    else:
        vector = _vector(value, "IK normalized target")
        target = _normalized_target(profile, handle, root, vector)
        source_value = vector
    setup = handle["setup_angles_deg"]
    fallback = _fallback(root, pose[distal_id]["endpoint_xy"])
    solved = solve_setup_local_ik(
        root,
        proximal_length=handle["proximal_length_px"],
        distal_length=handle["distal_length_px"],
        target_xy=target,
        bend_direction=handle["bend_direction"],
        fallback_direction_xy=fallback,
        setup_proximal_world_rotation_deg=pose[proximal_id]["rotation_deg"],
        setup_distal_local_rotation_deg=setup["distal_local"],
    )
    world = solved.world
    return RetargetIkSample(
        tick=tick,
        source_value=source_value,
        root_xy=tuple(quantize_point(root)),
        requested_target_xy=tuple(quantize_point(world.requested_target_xy)),
        resolved_target_xy=tuple(quantize_point(world.resolved_target_xy)),
        proximal_rotation_delta_deg=quantize(solved.proximal_rotation_delta_deg),
        distal_rotation_delta_deg=quantize(solved.distal_rotation_delta_deg),
        reach_state=world.reach_state,
        requested_distance_px=quantize(world.requested_distance),
        minimum_reach_px=quantize(world.minimum_reach),
        maximum_reach_px=quantize(world.maximum_reach),
    )


def _normalized_target(profile, handle, root, value):
    side = handle["side"]
    frame = profile["body_frame"]
    outward = _vector(frame[f"{side}_outward_xy"], "body outward axis")
    up = _vector(frame["up_xy"], "body up axis")
    reach = _number(handle["kinematic_reach"]["maximum_px"], "maximum reach")
    return (
        root[0] + reach * (outward[0] * value[0] + up[0] * value[1]),
        root[1] + reach * (outward[1] * value[0] + up[1] * value[1]),
    )


def _sample_keys(keys, tick):
    for left, right in zip(keys, keys[1:]):
        if tick == left["tick"]:
            return left["value"]
        if left["tick"] < tick < right["tick"]:
            ratio = (tick - left["tick"]) / (right["tick"] - left["tick"])
            return _lerp(left["value"], right["value"], ratio)
    if tick == keys[-1]["tick"]:
        return keys[-1]["value"]
    raise MotionRetargetKinematicsError("Motion sample is outside its key range")


def _lerp(left, right, ratio):
    if isinstance(left, (int, float)) and not isinstance(left, bool):
        return float(left) + (float(right) - float(left)) * ratio
    left_point, right_point = _vector(left, "left key"), _vector(right, "right key")
    return [
        left_point[0] + (right_point[0] - left_point[0]) * ratio,
        left_point[1] + (right_point[1] - left_point[1]) * ratio,
    ]


def _handle_track(motion, handle_id):
    matches = [
        track for track in motion["tracks"]
        if track["target_kind"] == "ik_handle" and track["target"] == handle_id
    ]
    if len(matches) != 1:
        raise MotionRetargetKinematicsError("Motion IK handle track is missing or duplicated")
    return matches[0]


def _handle(profile, handle_id):
    matches = [item for item in profile["ik_handles"] if item["id"] == handle_id]
    if len(matches) != 1:
        raise MotionRetargetKinematicsError("Target IK handle is missing or duplicated")
    return matches[0]


def _fallback(root, endpoint):
    vector = endpoint[0] - root[0], endpoint[1] - root[1]
    length = math.hypot(*vector)
    if not math.isfinite(length) or length <= 1e-12:
        raise MotionRetargetKinematicsError("Animated IK fallback direction is degenerate")
    return vector[0] / length, vector[1] / length


def _vector(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise MotionRetargetKinematicsError(f"{label} must contain two finite numbers")
    return _number(value[0], label), _number(value[1], label)


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise MotionRetargetKinematicsError(f"{label} must be finite")
    return float(value)
