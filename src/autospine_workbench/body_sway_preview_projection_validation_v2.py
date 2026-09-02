"""Detached exact validation for the internal Preview v2 projection."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
from typing import Any

from .body_sway_preview_profile import (
    MAX_PREVIEW_SAMPLE_COUNT, MAX_ROTATION_KEY_COUNT,
    MAX_ROTATION_TRACK_COUNT,
)
from .body_sway_preview_profile_v2 import (
    PREVIEW_SEMANTICS, body_sway_preview_compiler_profile_v2,
)
from .body_sway_preview_projection_v2 import (
    build_body_sway_preview_projection_document_v2,
)
from .body_sway_probe_math import quantize_body_sway_number
from .body_sway_probe_report_evidence import tick_schedule_sha256
from .body_sway_probe_validation import (
    body_sway_probe_report_sha256, require_body_sway_selection,
)
from .idle_behavior_decision_validation_fields import (
    digest_value, identifier_value, require_timing,
)


_TOP = {
    "domain", "compiler", "semantics", "project_id", "clip_id",
    "source", "capture_framing", "legacy_projection_sha256", "timing",
    "selection", "probe_tick_schedule_sha256",
    "probe_sample_stream_sha256", "base_animation_sha256", "setup_sha256",
    "sample_ticks", "rotation_tracks", "summary",
}
_SOURCE = {
    "body_sway_probe_report_sha256", "base_motion_instance_v2_sha256",
    "capture_framing_candidate_sha256", "capture_framing_decision_sha256",
}


class BodySwayPreviewProjectionValidationV2Error(ValueError):
    """Raised when an embedded Preview v2 projection is not exact."""


def require_body_sway_preview_projection_v2(
    document: Mapping[str, Any], *, project_id: str, clip_id: str,
    report: Mapping[str, Any], motion_sha256: str,
    framing_candidate_sha256: str, framing_decision_sha256: str,
    framing_revision: int, reviewed_world_viewport: Mapping[str, Any],
) -> None:
    try:
        root = _object(document, "projection")
        _exact(root, _TOP, "projection")
        if root.get("domain") != "autospine-body-sway-preview-projection/v2" \
                or root.get("project_id") != project_id \
                or root.get("clip_id") != clip_id:
            raise BodySwayPreviewProjectionValidationV2Error(
                "Preview v2 projection identity differs"
            )
        _fixed(root.get("compiler"), body_sway_preview_compiler_profile_v2())
        _fixed(root.get("semantics"), PREVIEW_SEMANTICS)
        source = _source(
            root.get("source"), report, motion_sha256,
            framing_candidate_sha256, framing_decision_sha256,
        )
        viewport = _framing(
            root.get("capture_framing"), framing_revision,
            reviewed_world_viewport,
        )
        require_timing(root.get("timing"))
        require_body_sway_selection(root.get("selection"))
        for field in (
            "legacy_projection_sha256", "probe_tick_schedule_sha256",
            "probe_sample_stream_sha256", "base_animation_sha256",
            "setup_sha256",
        ):
            digest_value(root.get(field), f"Preview v2 projection {field}")
        ticks = _ticks(root.get("sample_ticks"), report)
        tracks = _tracks(root.get("rotation_tracks"), ticks, report)
        summary = {
            "sample_count": len(ticks), "rotation_track_count": len(tracks),
            "rotation_key_count": len(ticks) * len(tracks),
        }
        _fixed(root.get("summary"), summary)
        if summary["rotation_key_count"] > MAX_ROTATION_KEY_COUNT:
            raise BodySwayPreviewProjectionValidationV2Error(
                "Preview v2 projection key budget is exceeded"
            )
        rebuilt = build_body_sway_preview_projection_document_v2(
            project_id=project_id, clip_id=clip_id,
            report_sha256=source["body_sway_probe_report_sha256"],
            base_motion_instance_v2_sha256=motion_sha256,
            capture_framing_candidate_sha256=framing_candidate_sha256,
            capture_framing_decision_sha256=framing_decision_sha256,
            capture_framing_revision=framing_revision,
            world_viewport=viewport,
            legacy_projection_sha256=root["legacy_projection_sha256"],
            base_animation_sha256=root["base_animation_sha256"],
            setup_sha256=root["setup_sha256"], timing=dict(root["timing"]),
            selection=dict(root["selection"]),
            tick_schedule_sha256_value=root["probe_tick_schedule_sha256"],
            sample_stream_sha256=root["probe_sample_stream_sha256"],
            sample_ticks=ticks, rotation_tracks=tracks,
        )
        if _canonical(root) != _canonical(rebuilt):
            raise BodySwayPreviewProjectionValidationV2Error(
                "Preview v2 projection differs from its pinned builder"
            )
    except BodySwayPreviewProjectionValidationV2Error:
        raise
    except Exception as exc:
        raise BodySwayPreviewProjectionValidationV2Error(
            f"Preview v2 projection validation failed: {exc}"
        ) from exc


def _source(value, report, motion, framing_candidate, framing_decision):
    row = _object(value, "source")
    _exact(row, _SOURCE, "source")
    expected = {
        "body_sway_probe_report_sha256":
            body_sway_probe_report_sha256(report),
        "base_motion_instance_v2_sha256": motion,
        "capture_framing_candidate_sha256": framing_candidate,
        "capture_framing_decision_sha256": framing_decision,
    }
    for field in _SOURCE:
        digest_value(row.get(field), f"Preview v2 projection {field}")
    _fixed(row, expected)
    return row


def _framing(value, revision, expected_viewport):
    row = _object(value, "capture framing")
    _exact(row, {"revision", "world_viewport", "coordinate_space"},
           "capture framing")
    if type(row.get("revision")) is not int or row["revision"] != revision \
            or row.get("coordinate_space") \
                != "spine-world-bottom-left-y-up":
        raise BodySwayPreviewProjectionValidationV2Error(
            "Preview v2 capture framing differs"
        )
    viewport = _object(row.get("world_viewport"), "world viewport")
    _exact(viewport, {"x", "y", "width", "height"}, "world viewport")
    for field in ("x", "y", "width", "height"):
        _number(viewport.get(field), field, positive=field in {"width", "height"})
    _fixed(viewport, expected_viewport)
    return dict(viewport)


def _ticks(value, report):
    if not isinstance(value, list) \
            or not 2 <= len(value) <= MAX_PREVIEW_SAMPLE_COUNT \
            or any(type(tick) is not int or tick < 0 for tick in value) \
            or value[0] != 0 \
            or any(left >= right for left, right in zip(value, value[1:])):
        raise BodySwayPreviewProjectionValidationV2Error(
            "Preview v2 sample ticks are invalid"
        )
    schedule = report["schedule"]
    if len(value) != schedule["sample_count"] \
            or value[0] != schedule["first_tick"] \
            or value[-1] != schedule["last_tick"] \
            or tick_schedule_sha256(tuple(value)) \
                != schedule["tick_schedule_sha256"]:
        raise BodySwayPreviewProjectionValidationV2Error(
            "Preview v2 sample ticks differ from P10.2"
        )
    return list(value)


def _tracks(value, ticks, report):
    if not isinstance(value, list) \
            or not 1 <= len(value) <= MAX_ROTATION_TRACK_COUNT:
        raise BodySwayPreviewProjectionValidationV2Error(
            "Preview v2 rotation tracks are invalid"
        )
    expected_ids = report["sample_stream"]["rotation_bone_ids"]
    if [row.get("bone_id") for row in value if isinstance(row, Mapping)] \
            != expected_ids:
        raise BodySwayPreviewProjectionValidationV2Error(
            "Preview v2 rotation inventory differs from P10.2"
        )
    result = []
    for raw in value:
        row = _object(raw, "rotation track")
        _exact(row, {"bone_id", "property", "keys"}, "rotation track")
        identifier_value(row.get("bone_id"), "rotation bone")
        if row.get("property") != "rotation" \
                or not isinstance(row.get("keys"), list) \
                or len(row["keys"]) != len(ticks):
            raise BodySwayPreviewProjectionValidationV2Error(
                "Preview v2 rotation track shape differs"
            )
        keys = []
        for raw_key, tick in zip(row["keys"], ticks, strict=True):
            key = _object(raw_key, "rotation key")
            _exact(key, {"tick", "value"}, "rotation key")
            value_number = _number(key.get("value"), "rotation value")
            if type(key.get("tick")) is not int or key["tick"] != tick \
                    or quantize_body_sway_number(value_number) != value_number:
                raise BodySwayPreviewProjectionValidationV2Error(
                    "Preview v2 rotation key differs from its schedule"
                )
            keys.append({"tick": tick, "value": key["value"]})
        result.append({
            "bone_id": row["bone_id"], "property": "rotation", "keys": keys,
        })
    return result


def _object(value, label):
    if not isinstance(value, Mapping):
        raise BodySwayPreviewProjectionValidationV2Error(
            f"Preview v2 {label} must be an object"
        )
    return value


def _exact(value, fields, label):
    if set(value) != fields:
        raise BodySwayPreviewProjectionValidationV2Error(
            f"Preview v2 {label} fields are unsupported"
        )


def _fixed(value, expected):
    if _canonical(value) != _canonical(expected):
        raise BodySwayPreviewProjectionValidationV2Error(
            "Preview v2 fixed semantics differ"
        )


def _number(value, label, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)) \
            or positive and float(value) <= 0:
        raise BodySwayPreviewProjectionValidationV2Error(
            f"Preview v2 {label} is invalid"
        )
    return float(value)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


__all__ = [
    "BodySwayPreviewProjectionValidationV2Error",
    "require_body_sway_preview_projection_v2",
]
