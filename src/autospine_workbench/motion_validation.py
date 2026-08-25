"""Strict semantic validation for reusable target-independent MotionIR v1."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
from typing import Any

from .motion_roles import (
    CANONICAL_BONE_ROLES,
    CANONICAL_IK_HANDLES,
    CONTACT_LIMBS,
)
from .resolved_project import canonical_sha256


FORMAT = "autospine-motion-ir"
FORMAT_VERSION = 1
TICKS_PER_SECOND = 1_000_000
MAX_DURATION_TICKS = 600 * TICKS_PER_SECOND
MAX_TRACKS = len(CANONICAL_BONE_ROLES) + 1 + len(CANONICAL_IK_HANDLES)
MAX_KEYS_PER_TRACK = 4096
MAX_TOTAL_KEYS = 32768
MAX_MARKERS = 256
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_ABS_ROTATION_DEG = 1_000_000.0
MAX_ABS_NORMALIZED = 1024.0
MAX_ROTATION_STEP_DEG = 180.0
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TOP_FIELDS = set(
    "format format_version clip_id ticks_per_second duration_ticks loop "
    "coordinate_system tracks markers".split()
)
_TRACK_FIELDS = {"target_kind", "target", "property", "interpolation", "keys"}
_KEY_FIELDS = {"tick", "value"}
_MARKER_FIELDS = {"kind", "limb", "start_tick", "end_tick", "mode"}
_COORDINATE_SYSTEM = {
    "x_axis": "right",
    "y_axis": "down",
    "root_translation_space": "setup_parent_local_normalized_reference_length",
    "ik_target_space": "handle_root_relative_outward_up_normalized_max_reach",
    "ik_unreachable_policy": "reject",
    "rotation_unit": "degree",
    "rotation_space": "setup_local_additive",
    "positive_rotation": "clockwise",
    "contact_interval": "half_open",
}


class MotionValidationError(ValueError):
    """Raised when MotionIR is ambiguous, unsafe, or target-specific."""


def motion_coordinate_system() -> dict[str, str]:
    """Return a fresh copy of the only supported v1 coordinate contract."""
    return dict(_COORDINATE_SYSTEM)


def require_motion_ir(document: Mapping[str, Any]) -> None:
    """Fail closed on MotionIR shape, time, role, value, or resource drift."""
    try:
        root = _object(document, "MotionIR")
        _exact(root, _TOP_FIELDS, "MotionIR")
        _identity(root)
        duration = _tick(root.get("duration_ticks"), "duration_ticks")
        if duration < 1 or duration > MAX_DURATION_TICKS:
            raise MotionValidationError("MotionIR duration exceeds its resource limit")
        if type(root.get("loop")) is not bool:
            raise MotionValidationError("MotionIR loop must be boolean")
        if root.get("coordinate_system") != _COORDINATE_SYSTEM:
            raise MotionValidationError("MotionIR coordinate system is unsupported")
        total_keys = _tracks(root.get("tracks"), duration, root["loop"])
        if total_keys > MAX_TOTAL_KEYS:
            raise MotionValidationError("MotionIR total key resource limit exceeded")
        _markers(root.get("markers"), duration)
        encoded = json.dumps(
            dict(root), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise MotionValidationError("MotionIR document byte limit exceeded")
    except MotionValidationError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise MotionValidationError(f"MotionIR validation failed: {exc}") from exc


def motion_ir_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical SHA only after complete semantic validation."""
    require_motion_ir(document)
    try:
        return canonical_sha256(document)
    except (TypeError, ValueError) as exc:
        raise MotionValidationError("MotionIR is not canonical JSON") from exc


def _identity(root: Mapping[str, Any]) -> None:
    if root.get("format") != FORMAT or type(root.get("format_version")) is not int \
            or root.get("format_version") != FORMAT_VERSION:
        raise MotionValidationError("MotionIR format version is unsupported")
    clip_id = root.get("clip_id")
    if not isinstance(clip_id, str) or not _SAFE_ID.fullmatch(clip_id):
        raise MotionValidationError("MotionIR clip_id is invalid")
    if type(root.get("ticks_per_second")) is not int \
            or root.get("ticks_per_second") != TICKS_PER_SECOND:
        raise MotionValidationError("MotionIR tick rate is unsupported")


def _tracks(value: Any, duration: int, loop: bool) -> int:
    tracks = _array(value, "MotionIR tracks")
    if not 1 <= len(tracks) <= MAX_TRACKS:
        raise MotionValidationError("MotionIR track resource limit exceeded")
    previous, seen, total = None, set(), 0
    for raw in tracks:
        track = _object(raw, "MotionIR track")
        _exact(track, _TRACK_FIELDS, "MotionIR track")
        identity = _track_identity(track)
        if identity in seen or (previous is not None and identity <= previous):
            raise MotionValidationError("MotionIR tracks must be sorted and unique")
        seen.add(identity)
        previous = identity
        keys = _track_keys(track, duration, loop)
        total += len(keys)
    return total


def _track_identity(track: Mapping[str, Any]) -> tuple[str, str, str]:
    kind, target, prop = (
        track.get("target_kind"), track.get("target"), track.get("property")
    )
    if track.get("interpolation") != "linear":
        raise MotionValidationError("MotionIR interpolation is unsupported")
    if kind == "bone_role" and target in CANONICAL_BONE_ROLES and prop == "rotation":
        pass
    elif kind == "bone_role" and target == "humanoid.root" and prop == "translation":
        pass
    elif kind == "ik_handle" and target in CANONICAL_IK_HANDLES and prop == "target":
        pass
    else:
        raise MotionValidationError("MotionIR track target/property combination is unsupported")
    return str(kind), str(target), str(prop)


def _track_keys(track: Mapping[str, Any], duration: int, loop: bool) -> list[Any]:
    keys = _array(track.get("keys"), "MotionIR track keys")
    if not 2 <= len(keys) <= MAX_KEYS_PER_TRACK:
        raise MotionValidationError("MotionIR key resource limit exceeded")
    previous_tick, values = -1, []
    for raw in keys:
        key = _object(raw, "MotionIR key")
        _exact(key, _KEY_FIELDS, "MotionIR key")
        tick = _tick(key.get("tick"), "key tick")
        if tick <= previous_tick or tick > duration:
            raise MotionValidationError("MotionIR key ticks must be strictly increasing")
        previous_tick = tick
        values.append(_track_value(track["property"], key.get("value")))
    if keys[0]["tick"] != 0 or keys[-1]["tick"] != duration:
        raise MotionValidationError("Every MotionIR track must span tick 0 through duration")
    if track["property"] == "rotation":
        for left, right in zip(values, values[1:]):
            if abs(right - left) > MAX_ROTATION_STEP_DEG:
                raise MotionValidationError("MotionIR rotation contains a wrapped angle jump")
    if loop and values[0] != values[-1]:
        raise MotionValidationError("Looping MotionIR track endpoints must match")
    return keys


def _track_value(prop: str, value: Any):
    if prop == "rotation":
        return _number(value, "rotation", MAX_ABS_ROTATION_DEG)
    if prop == "target" and value == "setup":
        return value
    if not isinstance(value, list) or len(value) != 2:
        raise MotionValidationError("MotionIR normalized vectors must contain x and y")
    return [
        _number(value[0], "normalized x", MAX_ABS_NORMALIZED),
        _number(value[1], "normalized y", MAX_ABS_NORMALIZED),
    ]


def _markers(value: Any, duration: int) -> None:
    markers = _array(value, "MotionIR markers")
    if len(markers) > MAX_MARKERS:
        raise MotionValidationError("MotionIR marker resource limit exceeded")
    previous, seen, limb_ends = None, set(), {}
    for raw in markers:
        marker = _object(raw, "MotionIR marker")
        _exact(marker, _MARKER_FIELDS, "MotionIR marker")
        start = _tick(marker.get("start_tick"), "marker start")
        end = _tick(marker.get("end_tick"), "marker end")
        limb = marker.get("limb")
        identity = (start, end, str(limb))
        if marker.get("kind") != "contact" or limb not in CONTACT_LIMBS \
                or marker.get("mode") != "annotation_only":
            raise MotionValidationError("MotionIR marker semantics are unsupported")
        if start >= end or end > duration:
            raise MotionValidationError("MotionIR contact interval is invalid")
        if identity in seen or (previous is not None and identity <= previous):
            raise MotionValidationError("MotionIR markers must be sorted and unique")
        if start < limb_ends.get(limb, -1):
            raise MotionValidationError("MotionIR contact intervals overlap")
        seen.add(identity)
        previous = identity
        limb_ends[limb] = end


def _number(value: Any, label: str, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or abs(float(value)) > maximum:
        raise MotionValidationError(f"MotionIR {label} must be finite and bounded")
    return float(value)


def _tick(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise MotionValidationError(f"MotionIR {label} must be a non-negative integer tick")
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MotionValidationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise MotionValidationError(f"{label} must be an array")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise MotionValidationError(f"{label} fields are incomplete or unsupported")
