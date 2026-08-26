"""Strict derived projection and capture-plan fields for preview manifests."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from .body_sway_preview_capture_plan import (
    MAX_CAPTURE_CASES,
    BodySwayPreviewCapturePlanError,
    body_sway_capture_plan_sha256,
    select_body_sway_preview_capture_ticks,
)
from .body_sway_preview_profile import (
    BASE_ANIMATION_NAME,
    COMBINED_ANIMATION_NAME,
    MAX_PREVIEW_SAMPLE_COUNT,
    MAX_ROTATION_KEY_COUNT,
    MAX_ROTATION_TRACK_COUNT,
)
from .idle_behavior_decision_validation_fields import (
    IdleBehaviorDecisionFieldError,
    digest_value,
    exact_fields,
    object_value,
    identifier_value,
)
from .body_sway_probe_report_evidence import tick_schedule_sha256
from .idle_behavior_inventory import BODY_BONE_IDS
from .motion_roles import CANONICAL_BONE_ID_BY_ROLE
from .spine42_runtime_contract import (
    DEFAULT_BACKGROUND,
    DEFAULT_DPR,
    DEFAULT_VIEWPORT,
)


_PROJECTION_FIELDS = {
    "projection_sha256", "probe_tick_schedule_sha256",
    "probe_sample_stream_sha256", "base_motion_instance_v2_sha256",
    "base_animation_sha256", "setup_sha256", "rotation_timeline_sha256", "sample_ticks",
    "rotation_bone_ids",
    "sample_count", "rotation_track_count", "rotation_key_count",
    "sampling", "rotation_interpolation", "root_translation", "markers",
    "draw_order", "animation_names",
}
_CAPTURE_FIELDS = {
    "capture_plan_sha256", "viewport", "device_pixel_ratio", "background",
    "preserve_drawing_buffer", "world_viewport", "selection_scope", "cases",
}


class TemporaryBodySwayPreviewFieldError(ValueError):
    """Raised when derived preview metadata is structurally inconsistent."""


def require_preview_projection_metadata(
    value: Any, *, source: Mapping[str, Any], timing: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate bounded sampled-linear metadata and its exact P9 binding."""

    try:
        row = object_value(value, "Temporary preview projection")
        exact_fields(row, _PROJECTION_FIELDS, "Temporary preview projection")
        for field in (
            "projection_sha256", "probe_tick_schedule_sha256",
            "probe_sample_stream_sha256", "base_motion_instance_v2_sha256",
            "base_animation_sha256", "setup_sha256", "rotation_timeline_sha256",
        ):
            digest_value(row.get(field), field)
        if row["base_motion_instance_v2_sha256"] \
                != source["p9"]["motion_instance_v2_sha256"]:
            raise TemporaryBodySwayPreviewFieldError(
                "Preview projection differs from the exact P9 instance"
            )
        samples = _integer(row.get("sample_count"), 2,
                           MAX_PREVIEW_SAMPLE_COUNT, "sample_count")
        tracks = _integer(row.get("rotation_track_count"), 1,
                          MAX_ROTATION_TRACK_COUNT, "rotation_track_count")
        keys = _integer(row.get("rotation_key_count"), 2,
                        MAX_ROTATION_KEY_COUNT, "rotation_key_count")
        if keys != samples * tracks:
            raise TemporaryBodySwayPreviewFieldError(
                "Preview rotation key count is inconsistent"
            )
        sample_ticks = row.get("sample_ticks")
        if not isinstance(sample_ticks, list) or len(sample_ticks) != samples \
                or any(type(tick) is not int for tick in sample_ticks) \
                or sample_ticks != sorted(set(sample_ticks)) \
                or sample_ticks[0] != 0 \
                or sample_ticks[-1] != timing["duration_ticks"] \
                or tick_schedule_sha256(tuple(sample_ticks)) \
                != row["probe_tick_schedule_sha256"]:
            raise TemporaryBodySwayPreviewFieldError(
                "Preview sample ticks differ from their P10.2 schedule seal"
            )
        bone_ids = row.get("rotation_bone_ids")
        if not isinstance(bone_ids, list) or len(bone_ids) != tracks \
                or bone_ids != sorted(set(bone_ids)) \
                or not set(BODY_BONE_IDS) <= set(bone_ids) \
                or not set(bone_ids) <= set(CANONICAL_BONE_ID_BY_ROLE.values()):
            raise TemporaryBodySwayPreviewFieldError(
                "Preview rotation bone inventory is invalid"
            )
        for bone_id in bone_ids:
            identifier_value(bone_id, "rotation_bone_id")
        fixed = {
            "sampling": "p10-probe-schedule",
            "rotation_interpolation": "sampled-linear",
            "root_translation": "exact-motion-instance-v2",
            "markers": "exact-motion-instance-v2",
            "draw_order": "exact-motion-instance-v2-stepped",
            "animation_names": {
                "base": BASE_ANIMATION_NAME,
                "combined": COMBINED_ANIMATION_NAME,
            },
        }
        if any(row.get(field) != expected for field, expected in fixed.items()):
            raise TemporaryBodySwayPreviewFieldError(
                "Temporary preview projection semantics are unsupported"
            )
        return {
            "sample_count": samples,
            "rotation_track_count": tracks,
            "rotation_key_count": keys,
            "sample_ticks": list(sample_ticks),
            "rotation_bone_ids": list(bone_ids),
        }
    except TemporaryBodySwayPreviewFieldError:
        raise
    except (
        IdleBehaviorDecisionFieldError, KeyError, TypeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewFieldError(
            f"Temporary preview projection is invalid: {exc}"
        ) from exc


def require_preview_capture_plan(
    value: Any, *, duration: int, ticks_per_second: int,
    selection: dict[str, Any], sample_ticks: list[int],
) -> int:
    """Validate fixed viewport and complete ordered base/combined pairs."""

    try:
        plan = object_value(value, "Temporary preview capture plan")
        exact_fields(plan, _CAPTURE_FIELDS, "Temporary preview capture plan")
        body_sway_capture_plan_sha256(dict(plan))
        if plan.get("viewport") != {
            "width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1],
        } or not _exact_number(plan.get("device_pixel_ratio"), DEFAULT_DPR) \
                or plan.get("background") != DEFAULT_BACKGROUND \
                or plan.get("preserve_drawing_buffer") is not True \
                or plan.get("selection_scope") \
                != "bounded-stills-for-manual-review":
            raise TemporaryBodySwayPreviewFieldError(
                "Temporary preview capture profile is unsupported"
            )
        _world_viewport(plan.get("world_viewport"))
        cases = plan.get("cases")
        if not isinstance(cases, list) or not 3 <= len(cases) <= MAX_CAPTURE_CASES \
                or len(cases) % 2 != 1:
            raise TemporaryBodySwayPreviewFieldError(
                "Temporary preview capture case count is invalid"
            )
        _case(cases[0], "setup", None, 0, ticks_per_second)
        previous = -1
        paired_ticks = set()
        for index in range(1, len(cases), 2):
            base, combined = cases[index], cases[index + 1]
            if not isinstance(base, Mapping) or not isinstance(combined, Mapping):
                raise TemporaryBodySwayPreviewFieldError(
                    "Temporary preview capture cases must be objects"
                )
            tick = base.get("tick")
            if type(tick) is not int or not 0 <= tick <= duration \
                    or tick <= previous or combined.get("tick") != tick:
                raise TemporaryBodySwayPreviewFieldError(
                    "Temporary preview paired ticks are invalid"
                )
            _case(base, f"base-t{tick:09d}", BASE_ANIMATION_NAME,
                  tick, ticks_per_second)
            _case(combined, f"combined-t{tick:09d}",
                  COMBINED_ANIMATION_NAME, tick, ticks_per_second)
            previous = tick
            paired_ticks.add(tick)
        if not {0, duration} <= paired_ticks:
            raise TemporaryBodySwayPreviewFieldError(
                "Temporary preview capture plan must include both endpoints"
            )
        expected_ticks = select_body_sway_preview_capture_ticks(
            {"duration_ticks": duration, "ticks_per_second": ticks_per_second},
            selection,
            tuple(sample_ticks),
        )
        if tuple(sorted(paired_ticks)) != expected_ticks:
            raise TemporaryBodySwayPreviewFieldError(
                "Temporary preview capture ticks differ from the fixed selector"
            )
        return len(cases)
    except TemporaryBodySwayPreviewFieldError:
        raise
    except (
        BodySwayPreviewCapturePlanError, IdleBehaviorDecisionFieldError,
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewFieldError(
            f"Temporary preview capture plan is invalid: {exc}"
        ) from exc


def _case(value, identifier, animation, tick, ticks_per_second) -> None:
    actual_tick = value.get("tick") if isinstance(value, Mapping) else None
    actual_time = value.get("time_seconds") if isinstance(value, Mapping) else None
    if not isinstance(value, Mapping) or set(value) != {
        "case_id", "animation", "tick", "time_seconds",
    } or value.get("case_id") != identifier \
            or value.get("animation") != animation \
            or type(actual_tick) is not int or actual_tick != tick \
            or not _exact_number(actual_time, tick / ticks_per_second):
        raise TemporaryBodySwayPreviewFieldError(
            f"Temporary preview capture case is invalid: {identifier}"
        )


def _world_viewport(value) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "x", "y", "width", "height",
    } or not _exact_number(value.get("x"), 0.0) \
            or not _exact_number(value.get("y"), 0.0):
        raise TemporaryBodySwayPreviewFieldError(
            "Temporary preview world viewport is invalid"
        )
    for field in ("width", "height"):
        number = value.get(field)
        if isinstance(number, bool) or not isinstance(number, (int, float)) \
                or not math.isfinite(float(number)) or number <= 0:
            raise TemporaryBodySwayPreviewFieldError(
                "Temporary preview world viewport is invalid"
            )


def _integer(value, minimum, maximum, label) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise TemporaryBodySwayPreviewFieldError(
            f"Temporary preview {label} is invalid"
        )
    return value


def _exact_number(value, expected) -> bool:
    return not isinstance(value, bool) \
        and isinstance(value, (int, float)) \
        and math.isfinite(float(value)) \
        and value == expected
