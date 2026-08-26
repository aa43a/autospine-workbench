"""Fixed MotionInstance-v2 portions inherited by a P10 preview."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from .body_sway_probe_math_inputs import ROOT_BONE_ID
from .spine42_draw_order_offsets import (
    Spine42DrawOrderOffsetError,
    apply_spine42_draw_order_offsets,
)


class TemporaryBodySwayPreviewBaseTimelineError(ValueError):
    """Raised when base motion fields escape the fixed preview profile."""


def require_preview_base_timelines(
    bones: Mapping[str, Any],
    timing: Mapping[str, Any],
    rotation_ids: list[str],
    *,
    event_frames: Any,
    declared_events: Any,
    draw_order_frames: Any,
    setup_slots: tuple[str, ...],
) -> dict[str, list[dict[str, Any]]]:
    """Validate root translation, base keys, markers, and draw order."""

    try:
        translations = _translations(bones, timing, rotation_ids)
        event_names = _events(event_frames, timing)
        if not isinstance(declared_events, Mapping) \
                or set(declared_events) != event_names \
                or any(value != {} for value in declared_events.values()):
            raise TemporaryBodySwayPreviewBaseTimelineError(
                "Preview event frames differ from event declarations"
            )
        _draw_order(draw_order_frames, timing, setup_slots)
        return translations
    except TemporaryBodySwayPreviewBaseTimelineError:
        raise
    except (
        KeyError, OverflowError, Spine42DrawOrderOffsetError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewBaseTimelineError(
            f"Temporary preview base timeline validation failed: {exc}"
        ) from exc


def _translations(bones, timing, rotation_ids):
    translations = {}
    for bone_id, raw in bones.items():
        timelines = _object(raw, f"base bone {bone_id}")
        if not timelines or not set(timelines) <= {"rotate", "translate"}:
            raise TemporaryBodySwayPreviewBaseTimelineError(
                f"Base timeline fields are invalid: {bone_id}"
            )
        if "rotate" in timelines:
            if bone_id not in rotation_ids:
                raise TemporaryBodySwayPreviewBaseTimelineError(
                    "Base rotation targets a bone absent from the projection"
                )
            _frames(timelines["rotate"], {"time", "value"}, timing)
        if "translate" in timelines:
            _frames(timelines["translate"], {"time", "x", "y"}, timing)
            translations[bone_id] = timelines["translate"]
    if set(translations) != {ROOT_BONE_ID}:
        raise TemporaryBodySwayPreviewBaseTimelineError(
            "Base motion must contain only the canonical root translation"
        )
    return translations


def _frames(frames, fields, timing):
    if not isinstance(frames, list) or not 1 <= len(frames) <= 4096:
        raise TemporaryBodySwayPreviewBaseTimelineError(
            "Base timeline key count is invalid"
        )
    previous = -1.0
    duration = timing["duration_ticks"] / timing["ticks_per_second"]
    for frame in frames:
        if not isinstance(frame, Mapping) or set(frame) != fields:
            raise TemporaryBodySwayPreviewBaseTimelineError(
                "Base timeline key fields are invalid"
            )
        time = _number(frame.get("time"), "base key time")
        if not 0 <= time <= duration or time <= previous:
            raise TemporaryBodySwayPreviewBaseTimelineError(
                "Base timeline key times are invalid"
            )
        for field in fields - {"time"}:
            _number(frame.get(field), f"base key {field}")
        previous = time


def _events(frames, timing):
    if not isinstance(frames, list) or len(frames) > 512:
        raise TemporaryBodySwayPreviewBaseTimelineError(
            "Preview event frames are invalid"
        )
    previous = None
    names = set()
    duration = timing["duration_ticks"] / timing["ticks_per_second"]
    for frame in frames:
        if not isinstance(frame, Mapping) or set(frame) != {"time", "name"} \
                or not isinstance(frame.get("name"), str) or not frame["name"]:
            raise TemporaryBodySwayPreviewBaseTimelineError(
                "Preview event frame is invalid"
            )
        key = (_number(frame.get("time"), "event time"), frame["name"])
        if not 0 <= key[0] <= duration or previous is not None and key < previous:
            raise TemporaryBodySwayPreviewBaseTimelineError(
                "Preview event order is invalid"
            )
        names.add(frame["name"])
        previous = key
    return names


def _draw_order(frames, timing, setup_slots):
    if not isinstance(frames, list) or not 1 <= len(frames) <= 4096:
        raise TemporaryBodySwayPreviewBaseTimelineError(
            "Preview draw-order frames are invalid"
        )
    previous = -1.0
    duration = timing["duration_ticks"] / timing["ticks_per_second"]
    for frame in frames:
        if not isinstance(frame, Mapping) or not {"time"} <= set(frame) \
                or not set(frame) <= {"time", "offsets"}:
            raise TemporaryBodySwayPreviewBaseTimelineError(
                "Preview draw-order frame fields are invalid"
            )
        time = _number(frame.get("time"), "draw-order time")
        if not 0 <= time <= duration or time <= previous \
                or "offsets" in frame and not isinstance(frame["offsets"], list):
            raise TemporaryBodySwayPreviewBaseTimelineError(
                "Preview draw-order frame is invalid"
            )
        apply_spine42_draw_order_offsets(setup_slots, frame.get("offsets", []))
        previous = time


def _object(value, label):
    if not isinstance(value, Mapping):
        raise TemporaryBodySwayPreviewBaseTimelineError(
            f"Temporary preview {label} must be an object"
        )
    return value


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)):
        raise TemporaryBodySwayPreviewBaseTimelineError(
            f"Temporary preview {label} must be finite"
        )
    return float(value)
