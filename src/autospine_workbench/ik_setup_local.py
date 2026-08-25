"""Convert absolute analytic IK solutions into RigIR setup-local deltas."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math
from typing import Literal

from .two_bone_ik import TwoBoneIkSolution, solve_two_bone_ik


@dataclass(frozen=True, slots=True)
class SetupLocalIkSolution:
    """One finite IK solution plus rotations relative to the authored setup."""

    world: TwoBoneIkSolution
    distal_local_rotation_deg: float
    proximal_rotation_delta_deg: float
    distal_rotation_delta_deg: float


def solve_setup_local_ik(
    root_xy: Sequence[int | float],
    *,
    proximal_length: int | float,
    distal_length: int | float,
    target_xy: Sequence[int | float],
    bend_direction: Literal["positive", "negative"],
    fallback_direction_xy: Sequence[int | float],
    setup_proximal_world_rotation_deg: int | float,
    setup_distal_local_rotation_deg: int | float,
) -> SetupLocalIkSolution:
    """Solve a direct two-bone chain and return additive setup-local rotations."""

    setup_proximal = _angle(
        setup_proximal_world_rotation_deg,
        "setup_proximal_world_rotation_deg",
    )
    setup_distal = _angle(
        setup_distal_local_rotation_deg,
        "setup_distal_local_rotation_deg",
    )
    world = solve_two_bone_ik(
        root_xy,
        proximal_length=proximal_length,
        distal_length=distal_length,
        target_xy=target_xy,
        bend_direction=bend_direction,
        fallback_direction_xy=fallback_direction_xy,
    )
    distal_local = _normalize(
        world.distal_rotation_deg - world.proximal_rotation_deg
    )
    result = SetupLocalIkSolution(
        world=world,
        distal_local_rotation_deg=distal_local,
        proximal_rotation_delta_deg=_normalize(
            world.proximal_rotation_deg - setup_proximal
        ),
        distal_rotation_delta_deg=_normalize(distal_local - setup_distal),
    )
    if not all(math.isfinite(value) for value in (
        result.distal_local_rotation_deg,
        result.proximal_rotation_delta_deg,
        result.distal_rotation_delta_deg,
    )):
        raise ValueError("setup-local IK rotations must be finite")
    return result


def _angle(value: int | float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return _normalize(result)


def _normalize(value: float) -> float:
    normalized = (value + 180.0) % 360.0 - 180.0
    return 0.0 if abs(normalized) <= 1e-12 else normalized
