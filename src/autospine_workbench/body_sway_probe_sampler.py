"""Prepared, exact sampling for repeated body-sway pose evaluation."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .body_sway_probe_math import (
    BodySwayPoseSample,
    quantize_body_sway_number,
    sample_body_sway_overlay,
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
class _PreparedTrack:
    bone_id: str
    property: str
    ticks: tuple[int, ...]
    values: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class PreparedBodySwaySampler:
    """Immutable normalized tracks and reviewed overlay parameters."""

    _duration: int
    _cycles: int
    _tracks: tuple[_PreparedTrack, ...]
    _amplitudes: tuple[tuple[str, float], ...]
    _phases: tuple[tuple[str, Fraction], ...]

    @property
    def duration_ticks(self) -> int:
        return self._duration

    def sample(self, tick: int) -> BodySwayPoseSample:
        """Sample one exact tick without revalidating static inputs."""

        if type(tick) is not int or not 0 <= tick <= self._duration:
            raise BodySwayProbeMathError("Body-sway tick is outside the clip")
        base: dict[str, float] = {}
        root = None
        for track in self._tracks:
            value = _sample_track(track, tick)
            if track.property == "rotation":
                base[track.bone_id] = quantize_body_sway_number(float(value))
            else:
                root = (
                    quantize_body_sway_number(value[0]),
                    quantize_body_sway_number(value[1]),
                )
        if root is None:
            raise BodySwayProbeMathError(
                "MotionInstance v2 root translation is missing"
            )
        overlay = tuple(
            (
                bone_id,
                sample_body_sway_overlay(
                    amplitude, phase, tick, self._duration, self._cycles,
                ),
            )
            for (bone_id, amplitude), (_phase_bone, phase) in zip(
                self._amplitudes, self._phases, strict=True,
            )
        )
        for bone_id, _value in overlay:
            base.setdefault(bone_id, 0.0)
        overlay_map = dict(overlay)
        combined = tuple(
            (
                bone_id,
                quantize_body_sway_number(
                    value + overlay_map.get(bone_id, 0.0)
                ),
            )
            for bone_id, value in sorted(base.items())
        )
        return BodySwayPoseSample(
            tick=tick,
            base_rotation_deg=tuple(sorted(base.items())),
            overlay_rotation_deg=overlay,
            combined_rotation_deg=combined,
            root_translation_xy=root,
        )


def prepare_body_sway_sampler(
    timing: Mapping[str, Any],
    tracks: list[Mapping[str, Any]],
    *,
    cycles: int,
    per_bone_amplitude_deg: list[Mapping[str, Any]],
    per_bone_phase_fraction: list[Mapping[str, Any]],
) -> PreparedBodySwaySampler:
    """Validate once and detach all data needed by repeated samples."""

    duration, _loop = normalize_timing(timing)
    count = require_cycles(cycles)
    amplitudes = normalize_amplitudes(per_bone_amplitude_deg)
    phases = normalize_phases(per_bone_phase_fraction)
    if tuple(row[0] for row in amplitudes) != tuple(row[0] for row in phases):
        raise BodySwayProbeMathError(
            "Body-sway parameter bone inventories differ"
        )
    prepared = tuple(
        _PreparedTrack(
            bone_id=bone_id,
            property=prop,
            ticks=tuple(row[0] for row in keys),
            values=tuple(row[1] for row in keys),
        )
        for bone_id, prop, keys in normalize_tracks(tracks, duration)
    )
    return PreparedBodySwaySampler(
        duration, count, prepared, amplitudes, phases,
    )


def _sample_track(track: _PreparedTrack, tick: int):
    index = bisect_left(track.ticks, tick)
    if index < len(track.ticks) and track.ticks[index] == tick:
        return track.values[index]
    if index == 0 or index == len(track.ticks):
        raise BodySwayProbeMathError("Body-sway sample is outside its key span")
    left_tick, right_tick = track.ticks[index - 1], track.ticks[index]
    left, right = track.values[index - 1], track.values[index]
    ratio = float(Fraction(tick - left_tick, right_tick - left_tick))
    if isinstance(left, tuple):
        return tuple(
            left[axis] + (right[axis] - left[axis]) * ratio
            for axis in (0, 1)
        )
    return left + (right - left) * ratio
