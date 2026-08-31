"""Strict sampled Spine timeline replay for TemporaryBodySwayPreview v2."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from .body_sway_preview_profile_v2 import (
    BASE_ANIMATION_NAME,
    COMBINED_ANIMATION_NAME,
)
from .body_sway_preview_projection_v2 import (
    body_sway_preview_base_animation_sha256_v2,
    body_sway_preview_rotation_timeline_sha256_v2,
    build_body_sway_preview_projection_document_v2,
)
from .body_sway_probe_math import quantize_body_sway_number
from .resolved_project import canonical_sha256
from .temporary_body_sway_preview_base_timeline_validation import (
    TemporaryBodySwayPreviewBaseTimelineError,
    require_preview_base_timelines,
)


class TemporaryBodySwayPreviewTimelineV2Error(ValueError):
    """Raised when v2 Spine timelines differ from their sealed projection."""


def require_temporary_body_sway_preview_timeline_v2(
    skeleton: Mapping[str, Any], projection: Mapping[str, Any],
    timing: Mapping[str, Any], source: Mapping[str, Any],
    selection: Mapping[str, Any], *, project_id: str, clip_id: str,
) -> None:
    """Rebuild v2 projection tracks while preserving the exact base motion."""

    try:
        animations = _object(skeleton.get("animations"), "animations")
        if set(animations) != {BASE_ANIMATION_NAME, COMBINED_ANIMATION_NAME}:
            raise TemporaryBodySwayPreviewTimelineV2Error(
                "Temporary preview v2 animation names are invalid"
            )
        base = _animation(animations[BASE_ANIMATION_NAME], "base")
        combined = _animation(animations[COMBINED_ANIMATION_NAME], "combined")
        if set(base) != set(combined) \
                or base.get("events") != combined.get("events") \
                or base["drawOrder"] != combined["drawOrder"]:
            raise TemporaryBodySwayPreviewTimelineV2Error(
                "Preview v2 combined events or draw order differ from base"
            )
        bone_ids = _skeleton_bone_ids(skeleton.get("bones"))
        base_bones = _object(base["bones"], "base bones")
        combined_bones = _object(combined["bones"], "combined bones")
        if not set(base_bones) <= bone_ids or not set(combined_bones) <= bone_ids:
            raise TemporaryBodySwayPreviewTimelineV2Error(
                "Preview v2 timeline targets a missing bone"
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
        if body_sway_preview_base_animation_sha256_v2(dict(base)) \
                != projection["base_animation_sha256"]:
            raise TemporaryBodySwayPreviewTimelineV2Error(
                "Preview v2 base animation differs from its seal"
            )
        expected_bones = set(rotation_ids) | set(translation)
        if set(combined_bones) != expected_bones:
            raise TemporaryBodySwayPreviewTimelineV2Error(
                "Preview v2 combined bone inventory is invalid"
            )
        tracks = []
        ticks = projection["sample_ticks"]
        for bone_id in rotation_ids:
            timelines = _object(
                combined_bones[bone_id], f"combined bone {bone_id}"
            )
            allowed = {"rotate"} | (
                {"translate"} if bone_id in translation else set()
            )
            if set(timelines) != allowed:
                raise TemporaryBodySwayPreviewTimelineV2Error(
                    f"Preview v2 timeline fields are invalid: {bone_id}"
                )
            if bone_id in translation \
                    and timelines["translate"] != translation[bone_id]:
                raise TemporaryBodySwayPreviewTimelineV2Error(
                    "Preview v2 root translation differs from base"
                )
            tracks.append({
                "bone_id": bone_id,
                "property": "rotation",
                "keys": _rotation_keys(
                    timelines["rotate"], ticks, timing["ticks_per_second"]
                ),
            })
        for bone_id, frames in translation.items():
            if bone_id not in rotation_ids:
                timelines = _object(
                    combined_bones[bone_id], f"combined bone {bone_id}"
                )
                if set(timelines) != {"translate"} \
                        or timelines["translate"] != frames:
                    raise TemporaryBodySwayPreviewTimelineV2Error(
                        "Preview v2 translation differs from base"
                    )
        if body_sway_preview_rotation_timeline_sha256_v2(tracks) \
                != projection["rotation_timeline_sha256"]:
            raise TemporaryBodySwayPreviewTimelineV2Error(
                "Preview v2 rotations differ from their seal"
            )
        rebuilt = build_body_sway_preview_projection_document_v2(
            project_id=project_id, clip_id=clip_id,
            report_sha256=source["body_sway_probe_report_sha256"],
            base_motion_instance_v2_sha256=
                source["p9"]["motion_instance_v2_sha256"],
            capture_framing_candidate_sha256=
                source["capture_framing_candidate_sha256"],
            capture_framing_decision_sha256=
                source["capture_framing_decision_sha256"],
            capture_framing_revision=source["capture_framing_revision"],
            world_viewport=projection["world_viewport"],
            legacy_projection_sha256=projection["legacy_projection_sha256"],
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
            raise TemporaryBodySwayPreviewTimelineV2Error(
                "Preview v2 projection identity differs from Spine bytes"
            )
        _require_loop_endpoints(combined_bones, timing)
    except TemporaryBodySwayPreviewTimelineV2Error:
        raise
    except (
        KeyError, OverflowError, TemporaryBodySwayPreviewBaseTimelineError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewTimelineV2Error(
            f"Temporary preview v2 timeline validation failed: {exc}"
        ) from exc


def _animation(value, label):
    row = _object(value, f"{label} animation")
    if not {"bones", "drawOrder"} <= set(row) \
            or not set(row) <= {"bones", "events", "drawOrder"}:
        raise TemporaryBodySwayPreviewTimelineV2Error(
            f"Preview v2 {label} animation fields are invalid"
        )
    return row


def _rotation_keys(frames, ticks, ticks_per_second):
    if not isinstance(frames, list) or len(frames) != len(ticks):
        raise TemporaryBodySwayPreviewTimelineV2Error(
            "Preview v2 rotation key count differs"
        )
    result = []
    for frame, tick in zip(frames, ticks, strict=True):
        if not isinstance(frame, Mapping) or set(frame) != {"time", "value"} \
                or frame.get("time") != tick / ticks_per_second:
            raise TemporaryBodySwayPreviewTimelineV2Error(
                "Preview v2 rotation key time is invalid"
            )
        value = _number(frame.get("value"))
        source_value = quantize_body_sway_number(-value)
        if value != -source_value:
            raise TemporaryBodySwayPreviewTimelineV2Error(
                "Preview v2 rotation key exceeds numeric precision"
            )
        result.append({"tick": tick, "value": source_value})
    return result


def _require_loop_endpoints(bones, timing):
    if timing["loop"]:
        for timelines in bones.values():
            for frames in timelines.values():
                if frames[0] != {**frames[-1], "time": frames[0]["time"]}:
                    raise TemporaryBodySwayPreviewTimelineV2Error(
                        "Preview v2 loop endpoints are not closed"
                    )


def _skeleton_bone_ids(value):
    if not isinstance(value, list):
        raise TemporaryBodySwayPreviewTimelineV2Error(
            "Preview v2 skeleton bones are invalid"
        )
    names = [row.get("name") for row in value if isinstance(row, Mapping)]
    if len(names) != len(value) or len(names) != len(set(names)) \
            or any(not isinstance(name, str) for name in names):
        raise TemporaryBodySwayPreviewTimelineV2Error(
            "Preview v2 skeleton bone names are invalid"
        )
    return set(names)


def _object(value, label):
    if not isinstance(value, Mapping):
        raise TemporaryBodySwayPreviewTimelineV2Error(
            f"Preview v2 {label} must be an object"
        )
    return value


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)):
        raise TemporaryBodySwayPreviewTimelineV2Error(
            "Preview v2 rotation value must be finite"
        )
    return float(value)
