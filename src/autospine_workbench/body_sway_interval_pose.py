"""Reusable interval pose, FK, and LBS for sampled-linear body sway.

Endpoint values retain Q9 error, skin output retains the Q4096 half-step, and
root translation follows setup-local LBS.  This preview model makes no runtime,
visual, seam, or release claim.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
from typing import Any, TypeAlias

from .body_sway_interval_arithmetic import (
    OutwardInterval,
    ZERO,
    cosine_interval,
    radians_interval,
    round_up,
    sine_interval,
)
from .body_sway_probe_geometry_context import PreparedBodySwayGeometryContext
from .body_sway_probe_profile import NUMERIC_PRECISION_DECIMALS
from .mesh_skinning_prepared import (
    PreparedSkinningBinding,
    PreparedSkinningRig,
)


IntervalPoint: TypeAlias = tuple[OutwardInterval, OutwardInterval]
IntervalMatrix: TypeAlias = tuple[
    OutwardInterval, OutwardInterval, OutwardInterval,
    OutwardInterval, OutwardInterval, OutwardInterval,
]
_Q9_HALF_UNIT = round_up(0.5e-9)
_Q4096_HALF_UNIT = 1.0 / 8192.0


class BodySwayIntervalPoseError(ValueError):
    """Raised when an interval pose cannot be evaluated without guessing."""


@dataclass(frozen=True, slots=True)
class PreparedBodySwayIntervalPose:
    """Immutable interval rotations, skin matrices, and post-LBS root motion."""

    rotation_deltas_deg: tuple[tuple[str, OutwardInterval], ...]
    skin_matrices: tuple[IntervalMatrix, ...]
    root_translation_xy: IntervalPoint
    _rig: PreparedSkinningRig = field(repr=False)


def prepare_body_sway_interval_pose(
    context: PreparedBodySwayGeometryContext,
    *,
    left_base_rotation_deg: Mapping[str, int | float],
    right_base_rotation_deg: Mapping[str, int | float],
    left_overlay_rotation_deg: Mapping[str, int | float],
    right_overlay_rotation_deg: Mapping[str, int | float],
    left_root_translation_xy: Sequence[int | float],
    right_root_translation_xy: Sequence[int | float],
    time_fraction: OutwardInterval,
    gain: OutwardInterval,
) -> PreparedBodySwayIntervalPose:
    """Prepare one conservative FK/LBS pose over a closed parameter box."""

    if type(context) is not PreparedBodySwayGeometryContext \
            or type(context.skinning_rig) is not PreparedSkinningRig:
        raise BodySwayIntervalPoseError("Body-sway interval context is invalid")
    time = _unit_interval(time_fraction, "time fraction")
    coupled_gain = _unit_interval(gain, "gain")
    rig = context.skinning_rig
    left_root = _point(left_root_translation_xy, "left root", q9=True)
    right_root = _point(right_root_translation_xy, "right root", q9=True)
    rotations = body_sway_interval_rotation_deltas(
        rig,
        left_base_rotation_deg, right_base_rotation_deg,
        left_overlay_rotation_deg, right_overlay_rotation_deg,
        time_fraction=time, gain=coupled_gain,
    )
    matrices = _skin_matrices(rig, dict(rotations))
    root = (
        _q9_linear_interval(left_root[0], right_root[0], time),
        _q9_linear_interval(left_root[1], right_root[1], time),
    )
    return PreparedBodySwayIntervalPose(rotations, matrices, root, rig)


def body_sway_interval_rotation_deltas(
    rig: PreparedSkinningRig,
    left_base_rotation_deg: Mapping[str, float],
    right_base_rotation_deg: Mapping[str, float],
    left_overlay_rotation_deg: Mapping[str, float],
    right_overlay_rotation_deg: Mapping[str, float],
    *,
    time_fraction: OutwardInterval,
    gain: OutwardInterval,
) -> tuple[tuple[str, OutwardInterval], ...]:
    """Enclose Q9 base plus the coupled Q9 overlay rotation for every bone."""

    if type(rig) is not PreparedSkinningRig:
        raise BodySwayIntervalPoseError("Body-sway interval rig is invalid")
    time = _unit_interval(time_fraction, "time fraction")
    coupled_gain = _unit_interval(gain, "gain")
    left_base = _rotation_map(left_base_rotation_deg, rig, "left base")
    right_base = _rotation_map(right_base_rotation_deg, rig, "right base")
    left_overlay = _rotation_map(
        left_overlay_rotation_deg, rig, "left overlay"
    )
    right_overlay = _rotation_map(
        right_overlay_rotation_deg, rig, "right overlay"
    )
    result = []
    for bone_id in rig.bone_ids:
        base = _q9_linear_interval(
            left_base.get(bone_id, 0.0),
            right_base.get(bone_id, 0.0), time,
        )
        overlay = _q9_linear_interval(
            left_overlay.get(bone_id, 0.0),
            right_overlay.get(bone_id, 0.0), time,
        )
        result.append((bone_id, base + coupled_gain * overlay + _q9_error()))
    return tuple(result)


def skin_body_sway_interval_binding(
    pose: PreparedBodySwayIntervalPose,
    binding: PreparedSkinningBinding,
) -> tuple[IntervalPoint, ...]:
    """Skin a binding from the exact prepared rig and add root/Q4096 bounds."""

    if type(pose) is not PreparedBodySwayIntervalPose \
            or type(binding) is not PreparedSkinningBinding \
            or pose._rig is not binding._rig:
        raise BodySwayIntervalPoseError(
            "Body-sway interval pose and binding are incompatible"
        )
    result = []
    for bind, influences in zip(
        binding._vertices, binding._influences, strict=True,
    ):
        x, y = ZERO, ZERO
        for bone_index, weight in influences:
            posed = _apply(pose.skin_matrices[bone_index], bind)
            scalar = OutwardInterval.point(weight)
            x, y = x + posed[0] * scalar, y + posed[1] * scalar
        quantization = OutwardInterval(-_Q4096_HALF_UNIT, _Q4096_HALF_UNIT)
        result.append((
            x + pose.root_translation_xy[0] + quantization,
            y + pose.root_translation_xy[1] + quantization,
        ))
    return tuple(result)


def apply_body_sway_interval_matrix(
    matrix: IntervalMatrix,
    point: Sequence[int | float],
) -> IntervalPoint:
    """Apply one interval affine matrix to one exact finite point."""

    if type(matrix) is not tuple or len(matrix) != 6 \
            or any(type(value) is not OutwardInterval or not value.finite
                   for value in matrix):
        raise BodySwayIntervalPoseError("Body-sway interval matrix is invalid")
    x_value, y_value = _point(point, "matrix point")
    return _apply(matrix, (x_value, y_value))


def _apply(matrix: IntervalMatrix, point: tuple[float, float]) -> IntervalPoint:
    a, b, c, d, tx, ty = matrix
    x, y = OutwardInterval.point(point[0]), OutwardInterval.point(point[1])
    return a * x + c * y + tx, b * x + d * y + ty


def _skin_matrices(
    rig: PreparedSkinningRig,
    deltas: Mapping[str, OutwardInterval],
) -> tuple[IntervalMatrix, ...]:
    world: dict[str, IntervalMatrix] = {}
    for bone_id in rig._order:
        bone = rig._bones[rig._bone_index[bone_id]]
        local = _local_matrix(bone, deltas[bone_id])
        world[bone_id] = local if bone.parent is None else _compose(
            world[bone.parent], local
        )
    return tuple(
        _compose(
            world[bone.identifier],
            tuple(OutwardInterval.point(value)
                  for value in rig._setup_inverse[index]),
        )
        for index, bone in enumerate(rig._bones)
    )


def _local_matrix(bone: Any, delta: OutwardInterval) -> IntervalMatrix:
    angle = radians_interval(OutwardInterval.point(bone.rotation_deg) + delta)
    cosine, sine = cosine_interval(angle), sine_interval(angle)
    scale_x, scale_y = (
        OutwardInterval.point(bone.scale_x),
        OutwardInterval.point(bone.scale_y),
    )
    return (
        cosine * scale_x, sine * scale_x,
        (ZERO - sine) * scale_y, cosine * scale_y,
        OutwardInterval.point(bone.x), OutwardInterval.point(bone.y),
    )


def _compose(parent: IntervalMatrix, local: IntervalMatrix) -> IntervalMatrix:
    pa, pb, pc, pd, ptx, pty = parent
    la, lb, lc, ld, ltx, lty = local
    return (
        pa * la + pc * lb, pb * la + pd * lb,
        pa * lc + pc * ld, pb * lc + pd * ld,
        pa * ltx + pc * lty + ptx,
        pb * ltx + pd * lty + pty,
    )


def _q9_linear_interval(
    left: float, right: float, fraction: OutwardInterval,
) -> OutwardInterval:
    left_value = OutwardInterval.point(left) + _q9_error()
    right_value = OutwardInterval.point(right) + _q9_error()
    return left_value + (right_value - left_value) * fraction


def _q9_error() -> OutwardInterval:
    return OutwardInterval(-_Q9_HALF_UNIT, _Q9_HALF_UNIT)


def _unit_interval(value: Any, label: str) -> OutwardInterval:
    if type(value) is not OutwardInterval or not value.finite \
            or value.lower < 0.0 or value.upper > 1.0:
        raise BodySwayIntervalPoseError(
            f"Body-sway interval {label} is invalid"
        )
    return value


def _rotation_map(value: Any, rig: PreparedSkinningRig, label: str):
    if not isinstance(value, Mapping):
        raise BodySwayIntervalPoseError(
            f"Body-sway interval {label} rotations are invalid"
        )
    known = frozenset(rig.bone_ids)
    if any(type(key) is not str or key not in known for key in value):
        raise BodySwayIntervalPoseError(
            f"Body-sway interval {label} rotation inventory is invalid"
        )
    return {key: _q9_number(item, f"{label} rotation")
            for key, item in value.items()}


def _point(value: Any, label: str, *, q9: bool = False) -> tuple[float, float]:
    if type(value) not in (list, tuple) or len(value) != 2:
        raise BodySwayIntervalPoseError(f"Body-sway interval {label} is invalid")
    normalize = _q9_number if q9 else _number
    return normalize(value[0], label), normalize(value[1], label)


def _q9_number(value: Any, label: str) -> float:
    numeric = _number(value, label)
    if round(numeric, NUMERIC_PRECISION_DECIMALS) != numeric \
            or numeric == 0.0 and math.copysign(1.0, numeric) < 0.0:
        raise BodySwayIntervalPoseError(
            f"Body-sway interval {label} is not canonical Q9 input"
        )
    return numeric


def _number(value: Any, label: str) -> float:
    if type(value) not in (int, float):
        raise BodySwayIntervalPoseError(f"Body-sway interval {label} is invalid")
    try:
        numeric = float(value)
    except OverflowError as exc:
        raise BodySwayIntervalPoseError(
            f"Body-sway interval {label} is invalid"
        ) from exc
    if not math.isfinite(numeric):
        raise BodySwayIntervalPoseError(f"Body-sway interval {label} is invalid")
    return numeric
