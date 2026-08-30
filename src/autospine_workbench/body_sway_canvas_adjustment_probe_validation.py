"""Sampled-probe and diagnosis checks for P10.2 canvas adjustment."""

from __future__ import annotations

from collections.abc import Mapping
import math

from .body_sway_canvas_adjustment_profile import GAIN_DENOMINATOR
from .idle_behavior_decision_validation_fields import (
    digest_value,
    exact_fields,
    identifier_value,
    object_value,
)
from .idle_behavior_inventory import BODY_BONE_IDS


CLASSIFICATIONS = {
    "reviewed_canvas_passed",
    "upstream_base_motion_canvas_overflow",
    "sampled_adjustment_candidate_available",
    "no_nonzero_sampled_adjustment_candidate",
}
SIDES = {"left", "right", "top", "bottom"}


class BodySwayCanvasAdjustmentProbeFieldError(ValueError):
    """Raised when sampled diagnostic fields disagree."""


def require_probe_rows(value, timing):
    """Require a gain-sorted subset that always includes reviewed gain 8/8."""

    if not isinstance(value, list) or not 1 <= len(value) <= 9:
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Canvas adjustment probe inventory is invalid"
        )
    result, previous = [], -1
    for raw in value:
        row = object_value(raw, "Canvas adjustment probe")
        exact_fields(row, {
            "gain", "sample_count", "canvas_status",
            "sampled_geometry_status", "canvas_failure_tick_count",
            "canvas_failure_vertex_count", "geometry_rejection_tick_count",
            "first_failure_tick", "last_failure_tick",
            "affected_attachment_ids", "failure_sides", "max_overflow_px",
            "worst_failure", "sampled_body_sway_peak_abs_delta_deg",
            "evidence_sha256",
        }, "Canvas adjustment probe")
        numerator = require_gain(row.get("gain"))
        if numerator <= previous:
            raise BodySwayCanvasAdjustmentProbeFieldError(
                "Canvas adjustment probes must be gain sorted and unique"
            )
        previous = numerator
        count = row.get("sample_count")
        if type(count) is not int or count < 2:
            raise BodySwayCanvasAdjustmentProbeFieldError(
                "Canvas adjustment sample count is invalid"
            )
        _probe_outcome(row, timing["duration_ticks"])
        digest_value(row.get("evidence_sha256"), "gain evidence")
        result.append(row)
    if result[-1]["gain"]["numerator"] != GAIN_DENOMINATOR:
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Canvas adjustment probes omit the reviewed gain"
        )
    return result


def require_diagnosis(value, probes):
    """Cross-check reviewed and zero-gain evidence with the classification."""

    row = object_value(value, "Canvas adjustment diagnosis")
    exact_fields(row, {
        "classification", "reason_codes", "reviewed_canvas_check",
        "zero_gain_canvas_status", "other_rejected_check_ids",
    }, "Canvas adjustment diagnosis")
    classification = row.get("classification")
    if classification not in CLASSIFICATIONS:
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Canvas adjustment classification is invalid"
        )
    for items in (row.get("reason_codes"), row.get("other_rejected_check_ids")):
        if not isinstance(items, list) or items != sorted(set(items)) \
                or any(not isinstance(item, str) for item in items):
            raise BodySwayCanvasAdjustmentProbeFieldError(
                "Canvas adjustment reason inventory is invalid"
            )
    check = object_value(row.get("reviewed_canvas_check"), "reviewed canvas check")
    exact_fields(check, {"status", "sample_count", "failure_count",
                         "evidence_sha256"}, "reviewed canvas check")
    if check.get("status") not in {"passed", "rejected"}:
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Reviewed canvas check status is invalid"
        )
    if any(type(check.get(field)) is not int or check[field] < 0
           for field in ("sample_count", "failure_count")) \
            or check["failure_count"] > check["sample_count"] \
            or (check["status"] == "passed") != (check["failure_count"] == 0):
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Reviewed canvas check count is invalid"
        )
    digest_value(check.get("evidence_sha256"), "reviewed canvas evidence")
    zero = _gain_row(probes, 0)
    reviewed = _gain_row(probes, GAIN_DENOMINATOR)
    expected_zero = zero["canvas_status"] if zero else "not_evaluated"
    if row.get("zero_gain_canvas_status") != expected_zero \
            or reviewed["canvas_status"] != check["status"] \
            or reviewed["canvas_failure_tick_count"] != check["failure_count"] \
            or reviewed["sample_count"] != check["sample_count"]:
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Diagnosis differs from exact sampled canvas evidence"
        )
    if classification == "reviewed_canvas_passed":
        valid = check["status"] == "passed" and zero is None \
            and len(probes) == 1
    elif classification == "upstream_base_motion_canvas_overflow":
        valid = check["status"] == "rejected" \
            and zero is not None and zero["canvas_status"] == "rejected" \
            and {probe["gain"]["numerator"] for probe in probes} == {0, 8}
    elif classification == "no_nonzero_sampled_adjustment_candidate":
        valid = check["status"] == "rejected" \
            and zero is not None and zero["canvas_status"] == "passed" \
            and {probe["gain"]["numerator"] for probe in probes} == set(range(9)) \
            and not any(
                probe["canvas_status"] == "passed"
                and probe["sampled_geometry_status"] == "passed"
                for probe in probes if probe["gain"]["numerator"] not in {0, 8}
            )
    else:
        valid = check["status"] == "rejected" \
            and zero is not None and zero["canvas_status"] == "passed"
    if not valid:
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Canvas adjustment classification is unsupported by its probes"
        )
    return classification


def require_summary(value, classification, probes, candidates):
    row = object_value(value, "Canvas adjustment summary")
    exact_fields(row, {
        "classification", "tested_gain_count", "adjustment_candidate_count",
        "reviewed_canvas_failure_tick_count",
        "zero_gain_canvas_failure_tick_count",
    }, "Canvas adjustment summary")
    zero = _gain_row(probes, 0)
    reviewed = _gain_row(probes, GAIN_DENOMINATOR)
    expected = {
        "classification": classification,
        "tested_gain_count": len(probes),
        "adjustment_candidate_count": len(candidates),
        "reviewed_canvas_failure_tick_count":
            reviewed["canvas_failure_tick_count"],
        "zero_gain_canvas_failure_tick_count": (
            zero["canvas_failure_tick_count"] if zero else None
        ),
    }
    if any(row.get(field) != result for field, result in expected.items()) \
            or (classification == "sampled_adjustment_candidate_available") \
            != (len(candidates) == 1):
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Canvas adjustment summary is inconsistent"
        )


def require_gain(value):
    row = object_value(value, "Canvas adjustment gain")
    exact_fields(row, {"numerator", "denominator"}, "Canvas adjustment gain")
    numerator = row.get("numerator")
    if type(numerator) is not int or not 0 <= numerator <= GAIN_DENOMINATOR \
            or row.get("denominator") != GAIN_DENOMINATOR:
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Canvas adjustment gain is outside the fixed grid"
        )
    return numerator


def _probe_outcome(row, duration):
    canvas, geometry = row.get("canvas_status"), row.get("sampled_geometry_status")
    if canvas not in {"passed", "rejected"} \
            or geometry not in {"passed", "rejected"}:
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Canvas adjustment probe status is invalid"
        )
    failures = row.get("canvas_failure_tick_count")
    vertices = row.get("canvas_failure_vertex_count")
    rejected = row.get("geometry_rejection_tick_count")
    if any(type(item) is not int or not 0 <= item <= row["sample_count"]
           for item in (failures, rejected)) or rejected < failures \
            or type(vertices) is not int or vertices < failures:
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Canvas adjustment failure counts are invalid"
        )
    first, last = row.get("first_failure_tick"), row.get("last_failure_tick")
    if failures == 0:
        valid = canvas == "passed" and first is None and last is None \
            and vertices == 0
    else:
        valid = canvas == "rejected" and type(first) is int \
            and type(last) is int and 0 <= first <= last <= duration
    if not valid:
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Canvas adjustment failure interval is inconsistent"
        )
    attachments = row.get("affected_attachment_ids")
    sides = row.get("failure_sides")
    if not isinstance(attachments, list) \
            or attachments != sorted(set(attachments)) \
            or any(not isinstance(item, str) for item in attachments) \
            or not isinstance(sides, list) or sides != sorted(set(sides)) \
            or not set(sides) <= SIDES:
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Canvas adjustment failure aggregation is invalid"
        )
    for identifier in attachments:
        identifier_value(identifier, "affected attachment")
    maximum = row.get("max_overflow_px")
    if not _finite(maximum) or maximum < 0.0 \
            or (failures == 0) != (maximum == 0.0):
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Canvas adjustment maximum overflow is invalid"
        )
    _worst(row.get("worst_failure"), failures, maximum, attachments, duration)
    _peak_deltas(row.get("sampled_body_sway_peak_abs_delta_deg"))
    if (geometry == "passed") != (rejected == 0):
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Canvas adjustment geometry status is inconsistent"
        )


def _worst(value, failures, maximum, attachments, duration):
    if value is None:
        if failures != 0:
            raise BodySwayCanvasAdjustmentProbeFieldError(
                "Canvas adjustment worst failure is missing"
            )
        return
    row = object_value(value, "Canvas adjustment worst failure")
    exact_fields(row, {"tick", "attachment_id", "vertex_index", "point_xy",
                       "sides", "overflow_px"}, "Canvas adjustment worst failure")
    point, sides = row.get("point_xy"), row.get("sides")
    if failures == 0 or type(row.get("tick")) is not int \
            or not 0 <= row["tick"] <= duration \
            or row.get("attachment_id") not in attachments \
            or type(row.get("vertex_index")) is not int \
            or row["vertex_index"] < 0 \
            or not isinstance(point, list) or len(point) != 2 \
            or not all(_finite(item) for item in point) \
            or not isinstance(sides, list) or sides != sorted(set(sides)) \
            or not sides or not set(sides) <= SIDES \
            or row.get("overflow_px") != maximum:
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Canvas adjustment worst failure is invalid"
        )


def _peak_deltas(value):
    if not isinstance(value, list) or len(value) != len(BODY_BONE_IDS) \
            or [row.get("bone_id") for row in value
                if isinstance(row, Mapping)] != list(BODY_BONE_IDS):
        raise BodySwayCanvasAdjustmentProbeFieldError(
            "Canvas adjustment sampled delta inventory is invalid"
        )
    for row in value:
        exact_fields(row, {"bone_id", "value"}, "sampled delta")
        if not _finite(row.get("value")) or row["value"] < 0.0:
            raise BodySwayCanvasAdjustmentProbeFieldError(
                "Canvas adjustment sampled delta is invalid"
            )


def _gain_row(probes, numerator):
    return next((row for row in probes
                 if row["gain"]["numerator"] == numerator), None)


def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) \
        and math.isfinite(value)
