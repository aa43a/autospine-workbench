"""Strict standalone validation for target-specific MotionInstance v1."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
from typing import Any

from .motion_roles import (
    CANONICAL_BONE_ID_BY_ROLE,
    CANONICAL_BONE_ROLE_ITEMS,
    CANONICAL_IK_HANDLES,
)
from .motion_target_validation import (
    MotionTargetValidationError,
    require_motion_target_profile,
)
from .resolved_project import canonical_sha256


FORMAT, FORMAT_VERSION = "autospine-motion-instance", 1
TICKS_PER_SECOND = 1_000_000
MAX_DURATION_TICKS = 600 * TICKS_PER_SECOND
MAX_TRACKS, MAX_KEYS_PER_TRACK, MAX_TOTAL_KEYS, MAX_MARKERS = 18, 4096, 32768, 256
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_ABS_ROTATION_DEG, MAX_ROTATION_STEP_DEG = 1_000_000.0, 180.0
MAX_ABS_TRANSLATION_PX = 10_000_000.0
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOP = {"format", "format_version", "clip_id", "timing", "source",
        "target_space", "tracks", "markers"}
_SOURCE_FIELDS = {
    "motion_ir_sha256", "motion_bundle_sha256", "motion_run_sha256",
    "target_profile_sha256", "retarget_run_identity_sha256",
}
_TARGET_SPACE = {
    "translation": "setup-local-pixel",
    "rotation": "setup-local-degree",
    "positive_rotation": "clockwise",
    "interpolation": "linear",
}
_BONE_IDS = frozenset(CANONICAL_BONE_ID_BY_ROLE.values())
_ROOT_BONE_ID = CANONICAL_BONE_ID_BY_ROLE["humanoid.root"]
_HANDLE_BONES = {
    handle: (
        CANONICAL_BONE_ID_BY_ROLE[f"humanoid.{limb}.upper.{side}"],
        CANONICAL_BONE_ID_BY_ROLE[f"humanoid.{limb}.lower.{side}"],
    )
    for handle in CANONICAL_IK_HANDLES
    for limb, side in (handle.split("."),)
}


class MotionInstanceValidationError(ValueError):
    """Raised when an instance is ambiguous, stale, unsafe, or non-canonical."""


def require_motion_instance(
    document: Mapping[str, Any],
    *,
    target_profile: Mapping[str, Any] | None = None,
) -> None:
    """Validate instance semantics and optionally bind one exact target profile."""
    try:
        root = _object(document, "MotionInstance")
        _exact(root, _TOP, "MotionInstance")
        if root.get("format") != FORMAT or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise MotionInstanceValidationError("MotionInstance format is unsupported")
        clip_id = root.get("clip_id")
        if not isinstance(clip_id, str) or not _SAFE_ID.fullmatch(clip_id):
            raise MotionInstanceValidationError("MotionInstance clip_id is invalid")
        duration, loop = _timing(root.get("timing"))
        source = _source(root.get("source"))
        space = _object(root.get("target_space"), "MotionInstance target space")
        _exact(space, set(_TARGET_SPACE), "MotionInstance target space")
        if space != _TARGET_SPACE:
            raise MotionInstanceValidationError("MotionInstance target space is unsupported")
        track_ids, total_keys = _tracks(root.get("tracks"), duration, loop)
        if total_keys > MAX_TOTAL_KEYS:
            raise MotionInstanceValidationError("MotionInstance total key limit exceeded")
        markers = _markers(root.get("markers"), duration)
        if target_profile is not None:
            _cross_target(target_profile, source, track_ids, markers)
        if len(_canonical(root)) > MAX_DOCUMENT_BYTES:
            raise MotionInstanceValidationError("MotionInstance byte limit exceeded")
    except MotionInstanceValidationError:
        raise
    except (MotionTargetValidationError, KeyError, OverflowError,
            TypeError, ValueError) as exc:
        raise MotionInstanceValidationError(
            f"MotionInstance validation failed: {exc}"
        ) from exc


def instance_sha256(document: Mapping[str, Any]) -> str:
    """Return the full canonical instance digest after semantic validation."""
    require_motion_instance(document)
    return canonical_sha256(document)


motion_instance_sha256 = instance_sha256


def _timing(value: Any) -> tuple[int, bool]:
    timing = _object(value, "MotionInstance timing")
    _exact(timing, {"ticks_per_second", "duration_ticks", "loop"}, "timing")
    if type(timing.get("ticks_per_second")) is not int \
            or timing.get("ticks_per_second") != TICKS_PER_SECOND:
        raise MotionInstanceValidationError("MotionInstance tick rate is unsupported")
    duration = _tick(timing.get("duration_ticks"), "duration")
    if not 1 <= duration <= MAX_DURATION_TICKS:
        raise MotionInstanceValidationError("MotionInstance duration is out of bounds")
    if type(timing.get("loop")) is not bool:
        raise MotionInstanceValidationError("MotionInstance loop must be boolean")
    return duration, timing["loop"]


def _source(value: Any) -> Mapping[str, Any]:
    source = _object(value, "MotionInstance source")
    _exact(source, _SOURCE_FIELDS, "MotionInstance source")
    for field in _SOURCE_FIELDS:
        _sha(source.get(field), field)
    return source


def _tracks(value: Any, duration: int, loop: bool) -> tuple[set[str], int]:
    tracks = _array(value, "MotionInstance tracks")
    if not 1 <= len(tracks) <= MAX_TRACKS:
        raise MotionInstanceValidationError("MotionInstance track limit exceeded")
    previous, seen, bone_ids, total = None, set(), set(), 0
    for raw in tracks:
        track = _object(raw, "MotionInstance track")
        _exact(track, {"bone_id", "property", "keys"}, "MotionInstance track")
        bone_id, prop = track.get("bone_id"), track.get("property")
        identity = (str(bone_id), str(prop))
        if bone_id not in _BONE_IDS or prop not in {"rotation", "translation"} \
                or (prop == "translation" and bone_id != _ROOT_BONE_ID):
            raise MotionInstanceValidationError("MotionInstance track target is unsupported")
        if identity in seen or (previous is not None and identity <= previous):
            raise MotionInstanceValidationError("Tracks must be sorted and unique")
        seen.add(identity)
        previous = identity
        bone_ids.add(str(bone_id))
        total += _keys(track, duration, loop)
    return bone_ids, total


def _keys(track: Mapping[str, Any], duration: int, loop: bool) -> int:
    keys = _array(track.get("keys"), "MotionInstance keys")
    if not 2 <= len(keys) <= MAX_KEYS_PER_TRACK:
        raise MotionInstanceValidationError("MotionInstance key limit exceeded")
    previous, values = -1, []
    for raw in keys:
        key = _object(raw, "MotionInstance key")
        _exact(key, {"tick", "value"}, "MotionInstance key")
        tick = _tick(key.get("tick"), "key tick")
        if tick <= previous or tick > duration:
            raise MotionInstanceValidationError("MotionInstance key ticks are invalid")
        previous = tick
        values.append(_value(track["property"], key.get("value")))
    if keys[0]["tick"] != 0 or keys[-1]["tick"] != duration:
        raise MotionInstanceValidationError("Every track must span the clip duration")
    if track["property"] == "rotation":
        if any(abs(right - left) > MAX_ROTATION_STEP_DEG
               for left, right in zip(values, values[1:])):
            raise MotionInstanceValidationError("MotionInstance rotation is wrapped")
    if loop and values[0] != values[-1]:
        raise MotionInstanceValidationError("Loop track endpoints must match exactly")
    return len(keys)


def _value(prop: str, value: Any):
    if prop == "rotation":
        return _number(value, "rotation", MAX_ABS_ROTATION_DEG)
    vector = _array(value, "MotionInstance translation")
    if len(vector) != 2:
        raise MotionInstanceValidationError("Translation must contain x and y")
    return [_number(item, "translation", MAX_ABS_TRANSLATION_PX) for item in vector]


def _markers(value: Any, duration: int) -> list[tuple[str, str, str]]:
    markers = _array(value, "MotionInstance markers")
    if len(markers) > MAX_MARKERS:
        raise MotionInstanceValidationError("MotionInstance marker limit exceeded")
    result, previous, seen, limb_ends = [], None, set(), {}
    fields = {
        "kind", "limb", "proximal_bone_id", "distal_bone_id",
        "start_tick", "end_tick", "mode",
    }
    for raw in markers:
        marker = _object(raw, "MotionInstance marker")
        _exact(marker, fields, "MotionInstance marker")
        limb = marker.get("limb")
        bones = (marker.get("proximal_bone_id"), marker.get("distal_bone_id"))
        start, end = (_tick(marker.get(name), f"marker {name}")
                      for name in ("start_tick", "end_tick"))
        identity = (start, end, str(limb))
        if marker.get("kind") != "contact" or marker.get("mode") != "annotation_only" \
                or limb not in _HANDLE_BONES or bones != _HANDLE_BONES[limb]:
            raise MotionInstanceValidationError("Contact marker binding is unsupported")
        if start >= end or end > duration or start < limb_ends.get(limb, -1):
            raise MotionInstanceValidationError("Contact marker interval is invalid")
        if identity in seen or (previous is not None and identity <= previous):
            raise MotionInstanceValidationError("Markers must be sorted and unique")
        previous, limb_ends[limb] = identity, end
        seen.add(identity)
        result.append((str(limb), str(bones[0]), str(bones[1])))
    return result


def _cross_target(target, source, track_ids, markers) -> None:
    require_motion_target_profile(target)
    if canonical_sha256(target) != source["target_profile_sha256"]:
        raise MotionInstanceValidationError("Target profile SHA binding is stale")
    inventory = [(item.get("role"), item.get("bone_id")) for item in
                 _array(target.get("bones"), "Target bones")]
    if inventory != list(CANONICAL_BONE_ROLE_ITEMS):
        raise MotionInstanceValidationError("Target profile bone inventory is invalid")
    ids = {bone_id for _role, bone_id in inventory}
    if not track_ids <= ids:
        raise MotionInstanceValidationError("Track is absent from the target profile")
    handles = {item.get("id"): (item.get("proximal_bone_id"),
                                item.get("distal_bone_id")) for item in
               _array(target.get("ik_handles"), "Target handles")}
    if any(handles.get(limb) != (proximal, distal)
           for limb, proximal, distal in markers):
        raise MotionInstanceValidationError("Contact differs from target IK handle")


def _number(value: Any, label: str, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or abs(float(value)) > maximum:
        raise MotionInstanceValidationError(f"{label} must be finite and bounded")
    return float(value)


def _tick(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise MotionInstanceValidationError(f"{label} must be a non-negative integer")
    return value


def _sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise MotionInstanceValidationError(f"{label} is not a SHA-256 digest")


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MotionInstanceValidationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise MotionInstanceValidationError(f"{label} must be an array")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise MotionInstanceValidationError(f"{label} fields are unsupported")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
