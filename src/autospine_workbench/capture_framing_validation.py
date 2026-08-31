"""Strict semantic validation for CaptureFramingCandidate v1."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
from typing import Any

from .capture_framing_profile import (
    CANDIDATE_RELEASE_GATE,
    CANDIDATE_SEMANTICS,
    CAPTURE_VIEWPORT,
    COORDINATE_TRANSFORM_ID,
    ENVELOPE_KINDS,
    FORMAT,
    FORMAT_VERSION,
    capture_framing_profile,
)
from .capture_framing_geometry import (
    canvas_bounds_to_runtime,
    contains_with_capture_margin,
    union_canvas_envelope,
)
from .dynamic_viewport_fit_inputs import envelope_value
from .manifest_artifacts import require_safe_token, require_sha256
from .resolved_project import canonical_sha256


class CaptureFramingValidationError(ValueError):
    """Raised when a detached framing candidate is malformed or overclaims."""


def require_capture_framing_candidate(value: Mapping[str, Any]) -> None:
    try:
        _fields(value, {
            "format", "format_version", "project_id", "clip_id", "source",
            "timing", "coordinate_spaces", "envelopes",
            "union_envelope_canvas", "union_envelope_runtime",
            "union_extrema_witnesses", "capture_viewport",
            "proposed_world_viewport", "coverage", "compiler",
            "compiler_sha256", "semantics", "status", "release_gate",
        }, "candidate")
        if value["format"] != FORMAT or value["format_version"] != FORMAT_VERSION \
                or value["status"] != "candidate_only":
            raise CaptureFramingValidationError("Candidate identity is invalid")
        require_safe_token(value["project_id"], "Capture framing project")
        require_safe_token(value["clip_id"], "Capture framing clip")
        _source(value["source"])
        _timing(value["timing"], value["source"]["tick_schedule_sha256"])
        canvas_height = _coordinate_spaces(value["coordinate_spaces"])
        if value["capture_viewport"] != CAPTURE_VIEWPORT \
                or value["compiler"] != capture_framing_profile() \
                or value["compiler_sha256"] != canonical_sha256(
                    capture_framing_profile()
                ) or value["semantics"] != CANDIDATE_SEMANTICS \
                or value["release_gate"] != CANDIDATE_RELEASE_GATE:
            raise CaptureFramingValidationError("Pinned framing profile differs")
        envelopes = value["envelopes"]
        _fields(envelopes, set(ENVELOPE_KINDS), "envelopes")
        for kind in ENVELOPE_KINDS:
            _envelope_record(envelopes[kind], kind, canvas_height)
        union_canvas = _bounds(
            value["union_envelope_canvas"], "canvas union envelope"
        )
        expected_union, expected_witnesses = union_canvas_envelope(envelopes)
        if union_canvas != expected_union \
                or value["union_extrema_witnesses"] != expected_witnesses:
            raise CaptureFramingValidationError("Envelope union is inconsistent")
        union_runtime = _bounds(
            value["union_envelope_runtime"], "runtime union envelope"
        )
        if union_runtime != canvas_bounds_to_runtime(
            union_canvas, canvas_height
        ):
            raise CaptureFramingValidationError("Runtime union is inconsistent")
        world = require_capture_world_viewport(
            value["proposed_world_viewport"], union=union_runtime,
            capture_viewport=value["capture_viewport"],
        )
        _fields(value["coverage"], set(ENVELOPE_KINDS), "coverage")
        for kind in ENVELOPE_KINDS:
            expected = contains_with_capture_margin(
                world, envelopes[kind]["bounds_runtime"],
                value["capture_viewport"],
            )
            if value["coverage"][kind] is not expected or expected is not True:
                raise CaptureFramingValidationError(
                    f"{kind} framing coverage is inconsistent"
                )
    except CaptureFramingValidationError:
        raise
    except (
        KeyError, OverflowError, RecursionError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise CaptureFramingValidationError(
            f"Capture framing candidate validation failed: {exc}"
        ) from exc


def capture_framing_candidate_sha256(value: Mapping[str, Any]) -> str:
    require_capture_framing_candidate(value)
    return hashlib.sha256(_canonical(value)).hexdigest()


def require_capture_world_viewport(value, *, union, capture_viewport):
    _fields(value, {"x", "y", "width", "height"}, "world viewport")
    result = {field: _number(value[field], field) for field in value}
    if result["width"] <= 0 or result["height"] <= 0:
        raise CaptureFramingValidationError("World viewport size is invalid")
    capture_aspect = capture_viewport["width"] / capture_viewport["height"]
    if not math.isclose(
        result["width"] / result["height"], capture_aspect,
        rel_tol=0.0, abs_tol=1e-9,
    ) or not contains_with_capture_margin(result, union, capture_viewport):
        raise CaptureFramingValidationError(
            "World viewport does not preserve the full capture margin"
        )
    return result


def _source(value):
    _fields(value, {
        "package_id", "body_sway_probe_report_sha256",
        "dynamic_viewport_fit_sha256", "tick_schedule_sha256",
        "current_p10_1_head", "capture_framing_profile_sha256",
        "layer_manifest_sha256", "p3", "p5", "p9",
    }, "source")
    for field in (
        "package_id", "body_sway_probe_report_sha256",
        "dynamic_viewport_fit_sha256", "tick_schedule_sha256",
        "capture_framing_profile_sha256", "layer_manifest_sha256",
    ):
        require_sha256(value[field], field)
    head = value["current_p10_1_head"]
    _fields(head, {"candidate_sha256", "decision_sha256", "revision"}, "head")
    require_sha256(head["candidate_sha256"], "P10.0 candidate")
    require_sha256(head["decision_sha256"], "P10.1 decision")
    if type(head["revision"]) is not int or not 1 <= head["revision"] <= 10_000:
        raise CaptureFramingValidationError("P10.1 revision is invalid")
    expected = {
        "p3": {
            "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
            "resolved_project_sha256", "rig_sha256", "run_sha256",
            "probes_sha256", "visuals_sha256", "bundle_sha256",
        },
        "p5": {
            "target_profile_sha256", "instance_sha256", "run_sha256",
            "retarget_report_sha256", "mesh_regression_sha256", "bundle_sha256",
        },
        "p9": {
            "foot_lock_candidates_sha256", "depth_order_candidates_sha256",
            "motion_policy_decision_sha256", "reviewed_motion_policy_sha256",
            "motion_instance_v2_sha256", "run_sha256", "bundle_sha256",
        },
    }
    for stage, fields in expected.items():
        _fields(value[stage], fields, stage)
        for field in fields:
            require_sha256(value[stage][field], f"{stage}.{field}")
    if value["p3"]["layer_manifest_sha256"] != value["layer_manifest_sha256"]:
        raise CaptureFramingValidationError("Layer Manifest identity differs")
    if value["capture_framing_profile_sha256"] != canonical_sha256(
        capture_framing_profile()
    ):
        raise CaptureFramingValidationError("Framing profile identity differs")


def _coordinate_spaces(value):
    _fields(value, {
        "envelope_space", "world_viewport_space", "canvas_height",
        "transform_id",
    }, "coordinate spaces")
    canvas_height = _number(value["canvas_height"], "canvas height")
    if value["envelope_space"] != "rig-canvas-top-left-y-down" \
            or value["world_viewport_space"] \
            != "spine-world-bottom-left-y-up" \
            or value["transform_id"] != COORDINATE_TRANSFORM_ID \
            or canvas_height <= 0:
        raise CaptureFramingValidationError("Coordinate contract differs")
    return canvas_height


def _timing(value, schedule_sha):
    _fields(value, {"ticks_per_second", "duration_ticks", "loop"}, "timing")
    if value["ticks_per_second"] != 1_000_000 \
            or type(value["duration_ticks"]) is not int \
            or not 1 <= value["duration_ticks"] <= 600_000_000 \
            or type(value["loop"]) is not bool \
            or not isinstance(schedule_sha, str):
        raise CaptureFramingValidationError("Framing timing is invalid")


def _envelope_record(value, kind, canvas_height):
    _fields(value, {
        "sample_count", "attachment_sample_count", "point_count",
        "evidence_sha256", "bounds_canvas", "bounds_runtime",
        "extrema_witnesses",
    }, kind)
    minimum = 1
    for field in ("sample_count", "attachment_sample_count", "point_count"):
        if type(value[field]) is not int or value[field] < minimum:
            raise CaptureFramingValidationError(f"{kind} count is invalid")
    if kind == "setup" and value["sample_count"] != 1:
        raise CaptureFramingValidationError("Setup envelope must have one sample")
    require_sha256(value["evidence_sha256"], f"{kind} evidence")
    canvas = _bounds(value["bounds_canvas"], f"{kind} canvas bounds")
    runtime = _bounds(value["bounds_runtime"], f"{kind} runtime bounds")
    if runtime != canvas_bounds_to_runtime(canvas, canvas_height):
        raise CaptureFramingValidationError(f"{kind} runtime bounds differ")
    _witnesses(value["extrema_witnesses"], canvas, kind)


def _witnesses(value, bounds, label):
    _fields(value, {"left", "right", "top", "bottom"}, f"{label} witnesses")
    for side, axis, field in (
        ("left", 0, "min_xy"), ("right", 0, "max_xy"),
        ("top", 1, "min_xy"), ("bottom", 1, "max_xy"),
    ):
        witness = value[side]
        _fields(witness, {
            "tick", "attachment_id", "vertex_index", "point_xy",
        }, f"{label} {side} witness")
        if type(witness["tick"]) is not int or witness["tick"] < 0 \
                or type(witness["vertex_index"]) is not int \
                or witness["vertex_index"] < 0:
            raise CaptureFramingValidationError("Framing witness index is invalid")
        require_safe_token(witness["attachment_id"], "Framing attachment")
        point = witness["point_xy"]
        if type(point) is not list or len(point) != 2:
            raise CaptureFramingValidationError("Framing witness point is invalid")
        normalized = [_number(item, "Framing witness point") for item in point]
        if normalized != point or point[axis] != bounds[field][axis]:
            raise CaptureFramingValidationError("Framing witness boundary differs")


def _bounds(value, label):
    _fields(value, {"min_xy", "max_xy", "size", "center_xy"}, label)
    points = []
    for field in ("min_xy", "max_xy", "size", "center_xy"):
        row = value[field]
        if type(row) is not list or len(row) != 2:
            raise CaptureFramingValidationError(f"{label} {field} is invalid")
        points.append([_number(item, f"{label} {field}") for item in row])
    expected = envelope_value([points[0], points[1]])
    if value != expected:
        raise CaptureFramingValidationError(f"{label} derivation is inconsistent")
    return value


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)) or abs(float(value)) > 1e12:
        raise CaptureFramingValidationError(f"{label} is invalid")
    return float(value)


def _fields(value, expected, label):
    if not isinstance(value, Mapping) or set(value) != set(expected):
        raise CaptureFramingValidationError(f"{label} fields are unsupported")


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")
