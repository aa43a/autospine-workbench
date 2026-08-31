"""Strict projection and capture-plan fields for temporary preview v2."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from .body_sway_preview_capture_plan import (
    MAX_CAPTURE_CASES,
    select_body_sway_preview_capture_ticks,
)
from .body_sway_preview_capture_plan_v2 import (
    BodySwayPreviewCapturePlanV2Error,
    body_sway_capture_plan_sha256_v2,
)
from .body_sway_preview_profile_v2 import (
    BASE_ANIMATION_NAME,
    CAPTURE_DEVICE_PIXEL_RATIO,
    CAPTURE_VIEWPORT,
    COMBINED_ANIMATION_NAME,
)
from .idle_behavior_decision_validation_fields import digest_value
from .spine42_runtime_contract import DEFAULT_BACKGROUND
from .temporary_body_sway_preview_fields import (
    TemporaryBodySwayPreviewFieldError,
    require_preview_projection_metadata,
)


_V1_PROJECTION_FIELDS = {
    "projection_sha256", "probe_tick_schedule_sha256",
    "probe_sample_stream_sha256", "base_motion_instance_v2_sha256",
    "base_animation_sha256", "setup_sha256", "rotation_timeline_sha256",
    "sample_ticks", "rotation_bone_ids", "sample_count",
    "rotation_track_count", "rotation_key_count", "sampling",
    "rotation_interpolation", "root_translation", "markers", "draw_order",
    "animation_names",
}
_V2_PROJECTION_FIELDS = _V1_PROJECTION_FIELDS | {
    "legacy_projection_sha256", "capture_framing_candidate_sha256",
    "capture_framing_decision_sha256", "capture_framing_revision",
    "world_viewport", "framing_mode",
}
_PLAN_FIELDS = {
    "capture_plan_sha256", "source", "viewport", "device_pixel_ratio",
    "background", "preserve_drawing_buffer", "world_viewport",
    "selection_scope", "cases",
}


class TemporaryBodySwayPreviewFieldV2Error(ValueError):
    """Raised when v2 framing metadata or its bounded cases differ."""


def require_preview_projection_metadata_v2(
    value: Any, *, source: Mapping[str, Any], timing: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate v1 math metadata plus the independent framing authority."""

    try:
        if not isinstance(value, Mapping) or set(value) != _V2_PROJECTION_FIELDS:
            raise TemporaryBodySwayPreviewFieldV2Error(
                "Temporary preview v2 projection fields are invalid"
            )
        for field in (
            "legacy_projection_sha256", "capture_framing_candidate_sha256",
            "capture_framing_decision_sha256",
        ):
            digest_value(value.get(field), field)
        revision = value.get("capture_framing_revision")
        if type(revision) is not int or not 1 <= revision <= 64 \
                or value.get("capture_framing_candidate_sha256") \
                != source["capture_framing_candidate_sha256"] \
                or value.get("capture_framing_decision_sha256") \
                != source["capture_framing_decision_sha256"] \
                or revision != source["capture_framing_revision"] \
                or value.get("framing_mode") \
                != "human-reviewed-capture-framing":
            raise TemporaryBodySwayPreviewFieldV2Error(
                "Temporary preview v2 framing source is inconsistent"
            )
        world = require_world_viewport_v2(value.get("world_viewport"))
        legacy = {field: value[field] for field in _V1_PROJECTION_FIELDS}
        counts = require_preview_projection_metadata(
            legacy, source=source, timing=timing,
        )
        return {
            **counts,
            "world_viewport": world,
            "capture_framing_revision": revision,
        }
    except TemporaryBodySwayPreviewFieldV2Error:
        raise
    except (
        KeyError, TemporaryBodySwayPreviewFieldError,
        TypeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewFieldV2Error(
            f"Temporary preview v2 projection is invalid: {exc}"
        ) from exc


def require_preview_capture_plan_v2(
    value: Any, *, timing: Mapping[str, Any], selection: dict[str, Any],
    projection: Mapping[str, Any],
) -> int:
    """Validate fixed 640px capture output and approved dynamic world frame."""

    try:
        if not isinstance(value, Mapping) or set(value) != _PLAN_FIELDS:
            raise TemporaryBodySwayPreviewFieldV2Error(
                "Temporary preview v2 capture plan fields are invalid"
            )
        body_sway_capture_plan_sha256_v2(dict(value))
        expected_source = {
            "preview_projection_sha256": projection["projection_sha256"],
            "capture_framing_candidate_sha256":
                projection["capture_framing_candidate_sha256"],
            "capture_framing_decision_sha256":
                projection["capture_framing_decision_sha256"],
            "capture_framing_revision":
                projection["capture_framing_revision"],
        }
        if value.get("source") != expected_source \
                or value.get("viewport") != CAPTURE_VIEWPORT \
                or not _exact_number(
                    value.get("device_pixel_ratio"),
                    CAPTURE_DEVICE_PIXEL_RATIO,
                ) \
                or value.get("background") != DEFAULT_BACKGROUND \
                or value.get("preserve_drawing_buffer") is not True \
                or value.get("selection_scope") \
                != "capture-framed-bounded-stills-for-manual-review-v2" \
                or require_world_viewport_v2(value.get("world_viewport")) \
                != projection["world_viewport"]:
            raise TemporaryBodySwayPreviewFieldV2Error(
                "Temporary preview v2 capture profile is inconsistent"
            )
        cases = value.get("cases")
        if not isinstance(cases, list) or not 3 <= len(cases) <= MAX_CAPTURE_CASES \
                or len(cases) % 2 != 1:
            raise TemporaryBodySwayPreviewFieldV2Error(
                "Temporary preview v2 capture case count is invalid"
            )
        ticks_per_second = timing["ticks_per_second"]
        duration = timing["duration_ticks"]
        _case(cases[0], "setup", None, 0, ticks_per_second)
        previous, paired = -1, set()
        for index in range(1, len(cases), 2):
            base, combined = cases[index], cases[index + 1]
            tick = base.get("tick") if isinstance(base, Mapping) else None
            if type(tick) is not int or not 0 <= tick <= duration \
                    or tick <= previous \
                    or not isinstance(combined, Mapping) \
                    or combined.get("tick") != tick:
                raise TemporaryBodySwayPreviewFieldV2Error(
                    "Temporary preview v2 paired ticks are invalid"
                )
            _case(base, f"base-t{tick:09d}", BASE_ANIMATION_NAME,
                  tick, ticks_per_second)
            _case(combined, f"combined-t{tick:09d}",
                  COMBINED_ANIMATION_NAME, tick, ticks_per_second)
            previous, paired = tick, paired | {tick}
        expected_ticks = select_body_sway_preview_capture_ticks(
            dict(timing), selection, tuple(projection["sample_ticks"]),
        )
        if tuple(sorted(paired)) != expected_ticks:
            raise TemporaryBodySwayPreviewFieldV2Error(
                "Temporary preview v2 cases differ from the fixed selector"
            )
        return len(cases)
    except TemporaryBodySwayPreviewFieldV2Error:
        raise
    except (
        BodySwayPreviewCapturePlanV2Error, KeyError, OverflowError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewFieldV2Error(
            f"Temporary preview v2 capture plan is invalid: {exc}"
        ) from exc


def require_world_viewport_v2(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping) or set(value) != {
        "x", "y", "width", "height",
    }:
        raise TemporaryBodySwayPreviewFieldV2Error(
            "Temporary preview v2 world viewport fields are invalid"
        )
    result = {}
    for field in ("x", "y", "width", "height"):
        number = value[field]
        if isinstance(number, bool) or not isinstance(number, (int, float)) \
                or not math.isfinite(float(number)) \
                or field in {"width", "height"} and number <= 0:
            raise TemporaryBodySwayPreviewFieldV2Error(
                "Temporary preview v2 world viewport is invalid"
            )
        result[field] = number
    return result


def _case(value, identifier, animation, tick, ticks_per_second) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "case_id", "animation", "tick", "time_seconds",
    } or value.get("case_id") != identifier \
            or value.get("animation") != animation \
            or value.get("tick") != tick \
            or not _exact_number(
                value.get("time_seconds"), tick / ticks_per_second,
            ):
        raise TemporaryBodySwayPreviewFieldV2Error(
            f"Temporary preview v2 capture case is invalid: {identifier}"
        )


def _exact_number(value, expected) -> bool:
    return not isinstance(value, bool) \
        and isinstance(value, (int, float)) \
        and math.isfinite(float(value)) and value == expected
