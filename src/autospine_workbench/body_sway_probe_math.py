"""Deterministic periodic sampling math for body-sway structural probes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
import math
from typing import Any

from .body_sway_probe_profile import (
    FIXED_SAMPLE_STEP_TICKS,
    MAX_SAMPLE_COUNT,
    NUMERIC_PRECISION_DECIMALS,
    UNIFORM_SAMPLES_PER_CYCLE,
)
from .body_sway_probe_math_inputs import (
    BodySwayProbeMathError,
    normalize_amplitudes,
    normalize_phases,
    normalize_timing,
    normalize_tracks,
    require_cycles,
)


@dataclass(frozen=True, slots=True)
class BodySwayPoseSample:
    """Immutable sampled base, overlay, combined rotations and root motion."""

    tick: int
    base_rotation_deg: tuple[tuple[str, float], ...]
    overlay_rotation_deg: tuple[tuple[str, float], ...]
    combined_rotation_deg: tuple[tuple[str, float], ...]
    root_translation_xy: tuple[float, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "base_rotation_deg": _rows(self.base_rotation_deg),
            "overlay_rotation_deg": _rows(self.overlay_rotation_deg),
            "combined_rotation_deg": _rows(self.combined_rotation_deg),
            "root_translation_xy": list(self.root_translation_xy),
        }


@dataclass(frozen=True, slots=True)
class BodySwayLoopAudit:
    """Numeric endpoint audit; this never represents visual or safety approval."""

    loop: bool
    status: str
    overlay_closed: bool
    base_rotation_closed: bool
    combined_rotation_closed: bool
    root_translation_closed: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": "numeric-endpoint-only",
            "loop": self.loop,
            "status": self.status,
            "overlay_closed": self.overlay_closed,
            "base_rotation_closed": self.base_rotation_closed,
            "combined_rotation_closed": self.combined_rotation_closed,
            "root_translation_closed": self.root_translation_closed,
            "reason_codes": list(self.reason_codes),
            "visual_safety_claimed": False,
        }


def build_body_sway_sample_ticks(
    timing: Mapping[str, Any],
    tracks: list[Mapping[str, Any]],
    *,
    cycles: int,
    per_bone_phase_fraction: list[Mapping[str, Any]],
) -> tuple[int, ...]:
    """Union authored/20 Hz/uniform ticks and bracket every sine quarter-turn."""

    duration, _loop = normalize_timing(timing)
    normalized = normalize_tracks(tracks, duration)
    count = require_cycles(cycles)
    phases = normalize_phases(per_bone_phase_fraction)
    ticks = {0, duration}
    ticks.update(
        tick for _bone, _prop, keys in normalized for tick, _value in keys
    )
    ticks.update(range(0, duration + 1, FIXED_SAMPLE_STEP_TICKS))
    divisions = count * UNIFORM_SAMPLES_PER_CYCLE
    if duration < divisions:
        raise BodySwayProbeMathError(
            "Body-sway duration cannot represent 32 unique samples per cycle"
        )
    for index in range(divisions + 1):
        _add_neighbors(ticks, Fraction(duration * index, divisions), duration)
    for _bone_id, phase in phases:
        first = _ceil(4 * phase)
        last = _floor(4 * (phase + count))
        for quarter in range(first, last + 1):
            position = Fraction(duration, count) * (
                Fraction(quarter, 4) - phase
            )
            _add_neighbors(ticks, position, duration)
    if len(ticks) > MAX_SAMPLE_COUNT:
        raise BodySwayProbeMathError("Body-sway sample count exceeds the profile")
    return tuple(sorted(ticks))


def sample_body_sway_pose(
    timing: Mapping[str, Any],
    tracks: list[Mapping[str, Any]],
    *,
    tick: int,
    cycles: int,
    per_bone_amplitude_deg: list[Mapping[str, Any]],
    per_bone_phase_fraction: list[Mapping[str, Any]],
) -> BodySwayPoseSample:
    """Add sine sway whose phase zero crosses toward positive clockwise degrees."""

    duration, _loop = normalize_timing(timing)
    if type(tick) is not int or not 0 <= tick <= duration:
        raise BodySwayProbeMathError("Body-sway tick is outside the clip")
    count = require_cycles(cycles)
    amplitudes = normalize_amplitudes(per_bone_amplitude_deg)
    phases = normalize_phases(per_bone_phase_fraction)
    if [item[0] for item in amplitudes] != [item[0] for item in phases]:
        raise BodySwayProbeMathError("Body-sway parameter bone inventories differ")
    base: dict[str, float] = {}
    root = None
    for bone_id, prop, keys in normalize_tracks(tracks, duration):
        value = _sample(keys, tick)
        if prop == "rotation":
            base[bone_id] = _quantize(float(value))
        else:
            vector = value
            root = (_quantize(vector[0]), _quantize(vector[1]))
    if root is None:
        raise BodySwayProbeMathError("MotionInstance v2 root translation is missing")
    overlay: list[tuple[str, float]] = []
    for (bone_id, amplitude), (_phase_bone, phase) in zip(
        amplitudes, phases, strict=True
    ):
        base.setdefault(bone_id, 0.0)
        overlay.append((
            bone_id,
            _overlay(amplitude, phase, tick, duration, count),
        ))
    overlay_map = dict(overlay)
    combined = tuple(
        (bone_id, _quantize(value + overlay_map.get(bone_id, 0.0)))
        for bone_id, value in sorted(base.items())
    )
    return BodySwayPoseSample(
        tick=tick,
        base_rotation_deg=tuple(sorted(base.items())),
        overlay_rotation_deg=tuple(overlay),
        combined_rotation_deg=combined,
        root_translation_xy=root,
    )


def audit_body_sway_loop(
    timing: Mapping[str, Any],
    start: BodySwayPoseSample,
    end: BodySwayPoseSample,
) -> BodySwayLoopAudit:
    """Check exact numeric endpoints, requiring base closure only for loops."""

    duration, loop = normalize_timing(timing)
    if type(start) is not BodySwayPoseSample \
            or type(end) is not BodySwayPoseSample \
            or start.tick != 0 or end.tick != duration:
        raise BodySwayProbeMathError(
            "Body-sway loop audit requires tick-zero and duration samples"
        )
    checks = {
        "overlay_not_closed": start.overlay_rotation_deg
        != end.overlay_rotation_deg,
        "base_rotation_not_closed": start.base_rotation_deg
        != end.base_rotation_deg,
        "combined_rotation_not_closed": start.combined_rotation_deg
        != end.combined_rotation_deg,
        "root_translation_not_closed": start.root_translation_xy
        != end.root_translation_xy,
    }
    required = {"overlay_not_closed"} | (
        set(checks) - {"overlay_not_closed"} if loop else set()
    )
    reasons = tuple(sorted(name for name in required if checks[name]))
    return BodySwayLoopAudit(
        loop=loop,
        status="rejected" if reasons else "closed",
        overlay_closed=not checks["overlay_not_closed"],
        base_rotation_closed=not checks["base_rotation_not_closed"],
        combined_rotation_closed=not checks["combined_rotation_not_closed"],
        root_translation_closed=not checks["root_translation_not_closed"],
        reason_codes=reasons,
    )


def _sample(keys, tick: int):
    for index, (right_tick, right) in enumerate(keys):
        if right_tick == tick:
            return right
        if right_tick > tick:
            left_tick, left = keys[index - 1]
            ratio = float(Fraction(tick - left_tick, right_tick - left_tick))
            if isinstance(left, tuple):
                return tuple(
                    left[axis] + (right[axis] - left[axis]) * ratio
                    for axis in (0, 1)
                )
            return left + (right - left) * ratio
    raise BodySwayProbeMathError("Body-sway sample is outside its key span")


def _overlay(amplitude, phase, tick, duration, cycles):
    position = 0 if tick == duration else tick
    turns = Fraction(cycles * position, duration) + phase
    turns -= _floor(turns)
    return _quantize(amplitude * math.sin(math.tau * float(turns)))


def _add_neighbors(ticks: set[int], value: Fraction, duration: int) -> None:
    for tick in {_floor(value), _ceil(value)}:
        if 0 <= tick <= duration:
            ticks.add(tick)


def _floor(value: Fraction) -> int:
    return value.numerator // value.denominator


def _ceil(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def _quantize(value: float) -> float:
    if not math.isfinite(value):
        raise BodySwayProbeMathError("Body-sway result must be finite")
    result = round(float(value), NUMERIC_PRECISION_DECIMALS)
    return 0.0 if result == 0 else result


def _rows(value: tuple[tuple[str, float], ...]) -> list[dict[str, Any]]:
    return [{"bone_id": bone_id, "value": number}
            for bone_id, number in value]
