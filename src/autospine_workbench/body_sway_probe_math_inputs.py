"""Strict finite input normalization for body-sway probe mathematics."""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
import math
import re
from typing import Any

from .body_sway_probe_profile import MAX_CYCLES
from .idle_behavior_decision_validation_fields import (
    MAX_REVIEW_AMPLITUDE_DEG,
)
from .idle_behavior_inventory import BODY_BONE_IDS
from .motion_roles import CANONICAL_BONE_ID_BY_ROLE


ROOT_BONE_ID = CANONICAL_BONE_ID_BY_ROLE["humanoid.root"]
_BONE_IDS = frozenset(CANONICAL_BONE_ID_BY_ROLE.values())
TICKS_PER_SECOND = 1_000_000
MAX_DURATION_TICKS = 600 * TICKS_PER_SECOND
MAX_TRACKS = 18
MAX_KEYS_PER_TRACK = 4096
MAX_TOTAL_KEYS = 32_768
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class BodySwayProbeMathError(ValueError):
    """Raised when a body-sway sample cannot be computed without guessing."""


def normalize_timing(value: Any) -> tuple[int, bool]:
    timing = _object(value, "timing")
    if set(timing) != {"ticks_per_second", "duration_ticks", "loop"} \
            or type(timing.get("ticks_per_second")) is not int \
            or timing.get("ticks_per_second") != TICKS_PER_SECOND \
            or type(timing.get("duration_ticks")) is not int \
            or not 1 <= timing["duration_ticks"] <= MAX_DURATION_TICKS \
            or type(timing.get("loop")) is not bool:
        raise BodySwayProbeMathError("Body-sway timing is invalid")
    return timing["duration_ticks"], timing["loop"]


def normalize_tracks(value: Any, duration: int):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_TRACKS:
        raise BodySwayProbeMathError("Body-sway tracks are invalid")
    result, previous, total, identities = [], None, 0, set()
    for raw in value:
        row = _object(raw, "track")
        if set(row) != {"bone_id", "property", "keys"}:
            raise BodySwayProbeMathError("Body-sway track fields are invalid")
        bone_id = _identifier(row.get("bone_id"), "track bone_id")
        prop = row.get("property")
        if bone_id not in _BONE_IDS \
                or prop not in {"rotation", "translation"} \
                or prop == "translation" and bone_id != ROOT_BONE_ID:
            raise BodySwayProbeMathError("Body-sway track target is unsupported")
        identity = (bone_id, prop)
        if previous is not None and identity <= previous:
            raise BodySwayProbeMathError(
                "Body-sway tracks must be sorted and unique"
            )
        keys = _keys(row.get("keys"), prop, duration)
        total += len(keys)
        result.append((bone_id, prop, keys))
        identities.add(identity)
        previous = identity
    if total > MAX_TOTAL_KEYS:
        raise BodySwayProbeMathError("Body-sway authored key limit exceeded")
    if (ROOT_BONE_ID, "translation") not in identities:
        raise BodySwayProbeMathError(
            "MotionInstance v2 root translation is missing"
        )
    return tuple(result)


def normalize_phases(value: Any):
    rows = _parameter_rows(value, "phase")
    result = []
    for bone_id, raw in rows:
        number = _number(raw, "phase fraction")
        if not 0.0 <= number < 1.0:
            raise BodySwayProbeMathError("Body-sway phase must be in [0, 1)")
        result.append((bone_id, Fraction(str(raw))))
    return tuple(result)


def normalize_amplitudes(value: Any):
    rows = _parameter_rows(value, "amplitude")
    result = []
    for bone_id, raw in rows:
        number = _number(raw, "amplitude")
        if not 0.0 <= number <= MAX_REVIEW_AMPLITUDE_DEG:
            raise BodySwayProbeMathError(
                "Body-sway amplitude is outside its review input envelope"
            )
        result.append((bone_id, number))
    if not any(number > 0.0 for _bone, number in result):
        raise BodySwayProbeMathError("Body-sway amplitudes cannot all be zero")
    return tuple(result)


def require_cycles(value: Any) -> int:
    if type(value) is not int or not 1 <= value <= MAX_CYCLES:
        raise BodySwayProbeMathError("Body-sway cycles are invalid")
    return value


def _keys(value: Any, prop: str, duration: int):
    if not isinstance(value, list) or not 2 <= len(value) <= MAX_KEYS_PER_TRACK:
        raise BodySwayProbeMathError("Body-sway key inventory is invalid")
    result, previous = [], -1
    for raw in value:
        row = _object(raw, "key")
        if set(row) != {"tick", "value"}:
            raise BodySwayProbeMathError("Body-sway key fields are invalid")
        tick = row.get("tick")
        if type(tick) is not int or tick <= previous or tick > duration:
            raise BodySwayProbeMathError("Body-sway key ticks are invalid")
        result.append((tick, _value(row.get("value"), prop)))
        previous = tick
    if result[0][0] != 0 or result[-1][0] != duration:
        raise BodySwayProbeMathError("Body-sway tracks must span the clip")
    return tuple(result)


def _value(value: Any, prop: str):
    if prop == "rotation":
        return _number(value, "rotation")
    if not isinstance(value, list) or len(value) != 2:
        raise BodySwayProbeMathError("Root translation must contain x and y")
    return (
        _number(value[0], "translation"),
        _number(value[1], "translation"),
    )


def _parameter_rows(value: Any, label: str):
    if not isinstance(value, list) or len(value) != len(BODY_BONE_IDS):
        raise BodySwayProbeMathError(f"Body-sway {label} rows are invalid")
    result, seen = [], set()
    for raw in value:
        row = _object(raw, f"{label} row")
        if set(row) != {"bone_id", "value"}:
            raise BodySwayProbeMathError(f"Body-sway {label} fields are invalid")
        bone_id = _identifier(row.get("bone_id"), f"{label} bone_id")
        if bone_id in seen:
            raise BodySwayProbeMathError(f"Body-sway {label} bones repeat")
        seen.add(bone_id)
        result.append((bone_id, row.get("value")))
    if tuple(bone_id for bone_id, _value in result) != BODY_BONE_IDS:
        raise BodySwayProbeMathError(
            f"Body-sway {label} bones differ from the fixed body chain"
        )
    return tuple(result)


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise BodySwayProbeMathError(f"Body-sway {label} must be finite")
    return float(value)


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise BodySwayProbeMathError(f"Body-sway {label} is invalid")
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BodySwayProbeMathError(f"Body-sway {label} must be an object")
    return value
