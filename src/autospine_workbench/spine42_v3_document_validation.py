"""Strict capability validation for projected MotionInstance v3 Spine JSON."""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
from typing import Any

from .motion_roles import CANONICAL_BONE_ID_BY_ROLE, CANONICAL_BONE_ROLE_BY_ID
from .spine42_draw_order_offsets import (
    Spine42DrawOrderOffsetError,
    apply_spine42_draw_order_offsets,
)
from .spine42_v3_setup_validation import (
    Spine42V3SetupValidationError,
    require_spine42_v3_setup,
)


_DOCUMENT_FIELDS = {
    "skeleton", "bones", "slots", "skins", "events", "animations",
}
_ANIMATION_REQUIRED = {"bones", "drawOrder"}
_ANIMATION_OPTIONAL = {"events"}
_BONE_TIMELINES = {"rotate", "translate"}
_CONTACT_EVENT = re.compile(
    r"contact\.(?:arm|leg)\.(?:left|right)\.(?:start|end)"
)
_ROOT_BONE_ID = CANONICAL_BONE_ID_BY_ROLE["humanoid.root"]
_MOTION_BONE_IDS = frozenset(CANONICAL_BONE_ROLE_BY_ID)


class Spine42V3DocumentValidationError(ValueError):
    """Raised when JSON exceeds the admitted P10.7a projection surface."""


def require_spine42_v3_document(
    document: Mapping[str, Any], *, clip_id: str,
) -> None:
    """Reject every Spine capability not emitted by the pinned v3 adapter."""

    try:
        _require_document(document, clip_id)
    except Spine42V3DocumentValidationError:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        Spine42DrawOrderOffsetError, Spine42V3SetupValidationError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42V3DocumentValidationError(
            f"Spine 4.2 v3 projected document is invalid: {exc}"
        ) from exc


def _require_document(document: Any, clip_id: str) -> None:
    value = _object(document, "document")
    if set(value) != _DOCUMENT_FIELDS:
        raise Spine42V3DocumentValidationError(
            "Spine v3 document fields exceed the pinned adapter profile"
        )
    bone_ids, setup_slots = require_spine42_v3_setup(value)
    if not _MOTION_BONE_IDS <= set(bone_ids):
        raise Spine42V3DocumentValidationError(
            "Spine v3 setup omits a canonical motion bone"
        )
    definitions = _event_definitions(value["events"])
    animations = _object(value["animations"], "animations")
    if set(animations) != {clip_id}:
        raise Spine42V3DocumentValidationError(
            "Spine v3 animation inventory differs from the clip"
        )
    animation = _object(animations[clip_id], "animation")
    fields = set(animation)
    if not _ANIMATION_REQUIRED <= fields \
            or not fields <= _ANIMATION_REQUIRED | _ANIMATION_OPTIONAL:
        raise Spine42V3DocumentValidationError(
            "Spine v3 animation uses an unsupported timeline family"
        )
    duration = _bone_tracks(animation["bones"], bone_ids)
    observed_events = _events(animation.get("events"), duration)
    if observed_events != definitions:
        raise Spine42V3DocumentValidationError(
            "Spine v3 event frames differ from event definitions"
        )
    _draw_order(animation["drawOrder"], setup_slots, duration)


def _event_definitions(value: Any) -> set[str]:
    events = _object(value, "event definitions")
    for name, definition in events.items():
        if type(name) is not str or not name or type(definition) is not dict \
                or definition or _CONTACT_EVENT.fullmatch(name) is None:
            raise Spine42V3DocumentValidationError(
                "Spine v3 event definitions exceed the pinned profile"
            )
    names = set(events)
    for name in names:
        limb = name.rsplit(".", 1)[0]
        if {f"{limb}.start", f"{limb}.end"} - names:
            raise Spine42V3DocumentValidationError(
                "Spine v3 contact event definitions are incomplete"
            )
    return names


def _bone_tracks(value: Any, bone_ids: tuple[str, ...]) -> float:
    tracks = _object(value, "bone timelines")
    allowed_bones = set(bone_ids) & _MOTION_BONE_IDS
    if not tracks or not set(tracks) <= allowed_bones:
        raise Spine42V3DocumentValidationError(
            "Spine v3 bone timeline inventory is invalid"
        )
    durations: set[float] = set()
    for bone_id, raw in tracks.items():
        timelines = _object(raw, f"bone timeline {bone_id}")
        if not timelines or not set(timelines) <= _BONE_TIMELINES:
            raise Spine42V3DocumentValidationError(
                "Spine v3 bone uses an unsupported timeline"
            )
        if "rotate" in timelines:
            durations.add(_frames(
                timelines["rotate"], {"time", "value"}, "rotate"
            ))
        if "translate" in timelines:
            if bone_id != _ROOT_BONE_ID:
                raise Spine42V3DocumentValidationError(
                    "Spine v3 translation is restricted to the root bone"
                )
            durations.add(_frames(
                timelines["translate"], {"time", "x", "y"}, "translate"
            ))
    if len(durations) != 1:
        raise Spine42V3DocumentValidationError(
            "Spine v3 timelines do not share one clip duration"
        )
    return durations.pop()


def _frames(value: Any, fields: set[str], label: str) -> float:
    frames = _array(value, f"{label} frames")
    if len(frames) < 2:
        raise Spine42V3DocumentValidationError(
            f"Spine v3 {label} timeline has too few frames"
        )
    previous = -1.0
    for index, raw in enumerate(frames):
        frame = _object(raw, f"{label} frame")
        if set(frame) != fields:
            raise Spine42V3DocumentValidationError(
                f"Spine v3 {label} frame fields are invalid"
            )
        time = _number(frame["time"], f"{label} time")
        if time < 0 or time <= previous or index == 0 and time != 0:
            raise Spine42V3DocumentValidationError(
                f"Spine v3 {label} frame times are not strictly increasing"
            )
        previous = time
        for name in fields - {"time"}:
            _number(frame[name], f"{label} {name}")
    return previous


def _events(value: Any, duration: float) -> set[str]:
    if value is None:
        return set()
    frames = _array(value, "event frames")
    if not frames:
        raise Spine42V3DocumentValidationError(
            "Spine v3 event timeline must be omitted when empty"
        )
    prior: tuple[float, str] | None = None
    names: set[str] = set()
    active: dict[str, bool] = {}
    for raw in frames:
        frame = _object(raw, "event frame")
        if set(frame) != {"time", "name"} or type(frame["name"]) is not str \
                or _CONTACT_EVENT.fullmatch(frame["name"]) is None:
            raise Spine42V3DocumentValidationError(
                "Spine v3 event frame fields are invalid"
            )
        current = (_nonnegative(frame["time"], "event time"), frame["name"])
        if current[0] > duration:
            raise Spine42V3DocumentValidationError(
                "Spine v3 event time exceeds the clip duration"
            )
        if prior is not None and current <= prior:
            raise Spine42V3DocumentValidationError(
                "Spine v3 event frames are not canonical"
            )
        prior = current
        name = frame["name"]
        limb, boundary = name.rsplit(".", 1)
        is_active = active.get(limb, False)
        if boundary == "start" and is_active \
                or boundary == "end" and not is_active:
            raise Spine42V3DocumentValidationError(
                "Spine v3 contact events are not paired and alternating"
            )
        active[limb] = boundary == "start"
        names.add(name)
    if any(active.values()):
        raise Spine42V3DocumentValidationError(
            "Spine v3 contact event interval is incomplete"
        )
    return names


def _draw_order(
    value: Any, setup_slots: tuple[str, ...], duration: float,
) -> None:
    frames = _array(value, "drawOrder frames")
    if not frames:
        raise Spine42V3DocumentValidationError(
            "Spine v3 drawOrder timeline is empty"
        )
    previous = -1.0
    for index, raw in enumerate(frames):
        frame = _object(raw, "drawOrder frame")
        if set(frame) not in ({"time"}, {"time", "offsets"}):
            raise Spine42V3DocumentValidationError(
                "Spine v3 drawOrder frame fields are invalid"
            )
        time = _nonnegative(frame["time"], "drawOrder time")
        if time > duration:
            raise Spine42V3DocumentValidationError(
                "Spine v3 drawOrder time exceeds the clip duration"
            )
        if time <= previous or index == 0 and time != 0:
            raise Spine42V3DocumentValidationError(
                "Spine v3 drawOrder times are not strictly increasing"
            )
        if index == 0 and set(frame) != {"time"}:
            raise Spine42V3DocumentValidationError(
                "Spine v3 drawOrder must begin in setup order"
            )
        previous = time
        offsets = frame.get("offsets", [])
        if "offsets" in frame and not offsets:
            raise Spine42V3DocumentValidationError(
                "Spine v3 empty drawOrder offsets must be omitted"
            )
        apply_spine42_draw_order_offsets(setup_slots, offsets)


def _object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise Spine42V3DocumentValidationError(f"Spine v3 {label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise Spine42V3DocumentValidationError(f"Spine v3 {label} must be an array")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)):
        raise Spine42V3DocumentValidationError(f"Spine v3 {label} is not finite")
    return float(value)


def _nonnegative(value: Any, label: str) -> float:
    result = _number(value, label)
    if result < 0:
        raise Spine42V3DocumentValidationError(
            f"Spine v3 {label} must be non-negative"
        )
    return result


__all__ = [
    "Spine42V3DocumentValidationError", "require_spine42_v3_document",
]
