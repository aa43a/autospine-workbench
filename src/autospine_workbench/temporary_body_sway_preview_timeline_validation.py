"""Strict sampled Spine timeline replay for TemporaryBodySwayPreview v1."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from .body_sway_preview_profile import (
    BASE_ANIMATION_NAME,
    COMBINED_ANIMATION_NAME,
)
from .body_sway_preview_projection import (
    body_sway_preview_base_animation_sha256,
    body_sway_preview_rotation_timeline_sha256,
    build_body_sway_preview_projection_document,
)
from .body_sway_probe_math import quantize_body_sway_number
from .resolved_project import canonical_sha256
from .temporary_body_sway_preview_base_timeline_validation import (
    TemporaryBodySwayPreviewBaseTimelineError,
    require_preview_base_timelines,
)


class TemporaryBodySwayPreviewTimelineError(ValueError):
    """Raised when Spine timelines do not replay the sealed preview tracks."""


def require_temporary_body_sway_preview_timeline(
    skeleton: Mapping[str, Any],
    projection: Mapping[str, Any],
    timing: Mapping[str, Any],
    source: Mapping[str, Any],
    selection: Mapping[str, Any],
    *,
    project_id: str,
    clip_id: str,
) -> None:
    """Rebuild rotation-track bytes and verify base-preserving semantics."""

    try:
        animations = _object(skeleton.get("animations"), "animations")
        if set(animations) != {BASE_ANIMATION_NAME, COMBINED_ANIMATION_NAME}:
            raise TemporaryBodySwayPreviewTimelineError(
                "Temporary preview animation names are invalid"
            )
        base = _animation(animations[BASE_ANIMATION_NAME], "base")
        combined = _animation(
            animations[COMBINED_ANIMATION_NAME], "combined"
        )
        if set(base) != set(combined) \
                or base.get("events") != combined.get("events") \
                or base["drawOrder"] != combined["drawOrder"]:
            raise TemporaryBodySwayPreviewTimelineError(
                "Combined events or draw order differ from exact base motion"
            )
        bone_ids = _skeleton_bone_ids(skeleton.get("bones"))
        base_bones = _object(base["bones"], "base bones")
        combined_bones = _object(combined["bones"], "combined bones")
        if not set(base_bones) <= bone_ids or not set(combined_bones) <= bone_ids:
            raise TemporaryBodySwayPreviewTimelineError(
                "Temporary preview timeline targets a missing bone"
            )
        rotation_ids = projection["rotation_bone_ids"]
        setup_slots = tuple(row["name"] for row in skeleton["slots"])
        translation = require_preview_base_timelines(
            base_bones, timing, rotation_ids,
            event_frames=base.get("events", []),
            declared_events=skeleton.get("events"),
            draw_order_frames=base["drawOrder"],
            setup_slots=setup_slots,
        )
        if body_sway_preview_base_animation_sha256(dict(base)) \
                != projection["base_animation_sha256"]:
            raise TemporaryBodySwayPreviewTimelineError(
                "Base animation differs from its exact projection identity"
            )
        expected_bones = set(rotation_ids) | set(translation)
        if set(combined_bones) != expected_bones:
            raise TemporaryBodySwayPreviewTimelineError(
                "Combined preview bone inventory is invalid"
            )
        tracks = []
        ticks = projection["sample_ticks"]
        for bone_id in rotation_ids:
            timelines = _object(
                combined_bones[bone_id], f"combined bone {bone_id}"
            )
            allowed = {"rotate"} | ({"translate"} if bone_id in translation else set())
            if set(timelines) != allowed:
                raise TemporaryBodySwayPreviewTimelineError(
                    f"Combined timeline fields are invalid: {bone_id}"
                )
            if bone_id in translation \
                    and timelines["translate"] != translation[bone_id]:
                raise TemporaryBodySwayPreviewTimelineError(
                    "Combined root translation differs from exact base motion"
                )
            keys = _rotation_keys(
                timelines["rotate"], ticks, timing["ticks_per_second"]
            )
            tracks.append({
                "bone_id": bone_id, "property": "rotation", "keys": keys,
            })
        for bone_id, frames in translation.items():
            if bone_id not in rotation_ids:
                timelines = _object(
                    combined_bones[bone_id], f"combined bone {bone_id}"
                )
                if set(timelines) != {"translate"} \
                        or timelines["translate"] != frames:
                    raise TemporaryBodySwayPreviewTimelineError(
                        "Combined translation differs from exact base motion"
                    )
        if body_sway_preview_rotation_timeline_sha256(tracks) \
                != projection["rotation_timeline_sha256"]:
            raise TemporaryBodySwayPreviewTimelineError(
                "Spine rotations differ from the sealed preview timeline"
            )
        rebuilt = build_body_sway_preview_projection_document(
            project_id=project_id,
            clip_id=clip_id,
            report_sha256=source["body_sway_probe_report_sha256"],
            base_motion_instance_v2_sha256=
                source["p9"]["motion_instance_v2_sha256"],
            base_animation_sha256=projection["base_animation_sha256"],
            setup_sha256=projection["setup_sha256"],
            timing=dict(timing), selection=dict(selection),
            tick_schedule_sha256_value=
                projection["probe_tick_schedule_sha256"],
            sample_stream_sha256=projection["probe_sample_stream_sha256"],
            sample_ticks=list(projection["sample_ticks"]),
            rotation_tracks=tracks,
        )
        if canonical_sha256(rebuilt) != projection["projection_sha256"]:
            raise TemporaryBodySwayPreviewTimelineError(
                "Spine rotations differ from the exact projection identity"
            )
        _require_loop_endpoints(combined_bones, timing)
    except TemporaryBodySwayPreviewTimelineError:
        raise
    except (
        KeyError, OverflowError, TemporaryBodySwayPreviewBaseTimelineError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewTimelineError(
            f"Temporary preview timeline validation failed: {exc}"
        ) from exc


def _animation(value, label):
    row = _object(value, f"{label} animation")
    if not {"bones", "drawOrder"} <= set(row) \
            or not set(row) <= {"bones", "events", "drawOrder"}:
        raise TemporaryBodySwayPreviewTimelineError(
            f"Temporary preview {label} animation fields are invalid"
        )
    return row


def _rotation_keys(frames, ticks, ticks_per_second):
    if not isinstance(frames, list) or len(frames) != len(ticks):
        raise TemporaryBodySwayPreviewTimelineError(
            "Combined rotation key count differs from the projection"
        )
    result = []
    for frame, tick in zip(frames, ticks, strict=True):
        if not isinstance(frame, Mapping) or set(frame) != {"time", "value"} \
                or frame.get("time") != tick / ticks_per_second:
            raise TemporaryBodySwayPreviewTimelineError(
                "Combined rotation key time is invalid"
            )
        value = _number(frame.get("value"), "rotation value")
        source_value = quantize_body_sway_number(-value)
        if value != -source_value:
            raise TemporaryBodySwayPreviewTimelineError(
                "Combined rotation key exceeds numeric precision"
            )
        result.append({"tick": tick, "value": source_value})
    return result


def _require_loop_endpoints(bones, timing):
    if not timing["loop"]:
        return
    for timelines in bones.values():
        for frames in timelines.values():
            if frames[0] != {**frames[-1], "time": frames[0]["time"]}:
                raise TemporaryBodySwayPreviewTimelineError(
                    "Looping preview timeline endpoints are not closed"
                )


def _skeleton_bone_ids(value):
    if not isinstance(value, list):
        raise TemporaryBodySwayPreviewTimelineError(
            "Temporary preview skeleton bones are invalid"
        )
    names = [row.get("name") for row in value if isinstance(row, Mapping)]
    if len(names) != len(value) or any(not isinstance(name, str) for name in names) \
            or len(names) != len(set(names)):
        raise TemporaryBodySwayPreviewTimelineError(
            "Temporary preview skeleton bone names are invalid"
        )
    return set(names)


def _object(value, label):
    if not isinstance(value, Mapping):
        raise TemporaryBodySwayPreviewTimelineError(
            f"Temporary preview {label} must be an object"
        )
    return value


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)):
        raise TemporaryBodySwayPreviewTimelineError(
            f"Temporary preview {label} must be finite"
        )
    return float(value)
