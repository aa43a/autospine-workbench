"""Deterministic FK sampling for validated target-specific MotionInstance clips."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from .motion_instance_validation import (
    MotionInstanceValidationError,
    require_motion_instance,
)
from .rig_fk import RigFkError, evaluate_world_setup


SAMPLE_STEP_TICKS = 50_000


class MotionInstanceSamplingError(ValueError):
    """Raised when an instance cannot be sampled on its exact target setup."""


def instance_sample_ticks(
    instance: Mapping[str, Any],
    *,
    target_profile: Mapping[str, Any],
) -> tuple[int, ...]:
    """Return pinned 20 Hz audit ticks plus every authored key tick."""

    try:
        require_motion_instance(instance, target_profile=target_profile)
        duration = instance["timing"]["duration_ticks"]
        ticks = set(range(0, duration + 1, SAMPLE_STEP_TICKS))
        ticks.add(duration)
        for track in instance["tracks"]:
            ticks.update(key["tick"] for key in track["keys"])
        return tuple(sorted(ticks))
    except MotionInstanceSamplingError:
        raise
    except (MotionInstanceValidationError, KeyError, TypeError, ValueError) as exc:
        raise MotionInstanceSamplingError(
            f"MotionInstance sample schedule failed: {exc}"
        ) from exc


def sample_instance_deltas(
    instance: Mapping[str, Any],
    *,
    target_profile: Mapping[str, Any],
    tick: int,
) -> tuple[dict[str, float], tuple[float, float]]:
    """Sample additive bone rotations and root translation in target units."""

    try:
        require_motion_instance(instance, target_profile=target_profile)
        _require_tick(instance, tick)
        rotations: dict[str, float] = {}
        translation = (0.0, 0.0)
        for track in instance["tracks"]:
            value = _sample_keys(track["keys"], tick)
            if track["property"] == "rotation":
                rotations[track["bone_id"]] = _number(
                    value, "sampled rotation"
                )
            else:
                translation = _vector(value, "sampled root translation")
        return rotations, translation
    except MotionInstanceSamplingError:
        raise
    except (MotionInstanceValidationError, KeyError, TypeError, ValueError) as exc:
        raise MotionInstanceSamplingError(
            f"MotionInstance delta sampling failed: {exc}"
        ) from exc


def sample_instance_pose(
    instance: Mapping[str, Any],
    *,
    target_profile: Mapping[str, Any],
    tick: int,
) -> dict[str, dict[str, Any]]:
    """Evaluate finite world setup after sampled additive animation deltas."""

    try:
        rotations, translation = sample_instance_deltas(
            instance, target_profile=target_profile, tick=tick
        )
        bones = []
        for row in target_profile["bones"]:
            bone_id, setup = row["bone_id"], row["setup_local"]
            x, y = _number(setup["x"], "setup x"), _number(
                setup["y"], "setup y"
            )
            if bone_id == "root-pelvis":
                x, y = x + translation[0], y + translation[1]
            bones.append({
                "id": bone_id,
                "parent": row["parent_bone_id"],
                "setup": {
                    "x": x,
                    "y": y,
                    "rotation_deg": _number(
                        setup["rotation_deg"], "setup rotation"
                    ) + rotations.get(bone_id, 0.0),
                    "scale_x": 1.0,
                    "scale_y": 1.0,
                    "length": _number(setup["length_px"], "setup length"),
                },
            })
        return evaluate_world_setup(bones)
    except MotionInstanceSamplingError:
        raise
    except (KeyError, RigFkError, TypeError, ValueError) as exc:
        raise MotionInstanceSamplingError(
            f"MotionInstance pose sampling failed: {exc}"
        ) from exc


def _sample_keys(keys, tick):
    for left, right in zip(keys, keys[1:]):
        if tick == left["tick"]:
            return left["value"]
        if left["tick"] < tick < right["tick"]:
            ratio = (tick - left["tick"]) / (right["tick"] - left["tick"])
            return _lerp(left["value"], right["value"], ratio)
    if tick == keys[-1]["tick"]:
        return keys[-1]["value"]
    raise MotionInstanceSamplingError("Sample tick is outside its key range")


def _lerp(left, right, ratio):
    if isinstance(left, (int, float)) and not isinstance(left, bool):
        return float(left) + (float(right) - float(left)) * ratio
    start, end = _vector(left, "left key"), _vector(right, "right key")
    return [
        start[0] + (end[0] - start[0]) * ratio,
        start[1] + (end[1] - start[1]) * ratio,
    ]


def _require_tick(instance, tick):
    duration = instance["timing"]["duration_ticks"]
    if type(tick) is not int or not 0 <= tick <= duration:
        raise MotionInstanceSamplingError("Sample tick is outside the clip")


def _vector(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise MotionInstanceSamplingError(f"{label} must contain x and y")
    return _number(value[0], label), _number(value[1], label)


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise MotionInstanceSamplingError(f"{label} must be finite")
    return float(value)
