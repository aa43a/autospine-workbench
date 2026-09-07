"""Source-bound axis-wise calibration drafts, with no annotation authority.

Callers must first validate the candidate against its benchmark manifest. This
pure analyzer checks the candidate's local shape but cannot resolve that manifest.
"""
from copy import deepcopy
import math
import re

from ..resolved_project import canonical_sha256
from .mapping import COORDINATE_SYSTEM, SCHEMA as CANDIDATE_SCHEMA, transform_point, validate_transform
from .validation import BenchmarkError, require_digest, validate_asset

SCHEMA = "autospine.benchmark-mapping-anchors/v1"
REPORT_SCHEMA = "autospine.benchmark-mapping-calibration/v1"
PROFILE = {"id": "axis_ols_v1", "min_axis_span_px": 1.0,
           "max_residual_relative_height": 0.03}


def _candidate(candidate):
    fields = {"schema", "dataset_sha256", "character_id", "dataset_split", "png_source",
              "psd_source", "source_to_psd_transform", "basis", "confidence",
              "review_required", "authority", "evidence"}
    if type(candidate) is not dict or set(candidate) != fields or \
            candidate["schema"] != CANDIDATE_SCHEMA or candidate["authority"] != "none" or \
            candidate["confidence"] is not None or candidate["review_required"] is not True:
        raise BenchmarkError("benchmark_mapping_candidate_invalid")
    for key, suffix in (("png_source", ".png"), ("psd_source", ".psd")):
        validate_asset(candidate[key], suffix)
    require_digest(candidate["dataset_sha256"])
    validate_transform(candidate["source_to_psd_transform"])
    return candidate


def _point(value, canvas):
    if type(value) is not list or len(value) != 2:
        raise BenchmarkError("benchmark_mapping_anchor_point_invalid")
    for number, limit in zip(value, canvas):
        try:
            valid = type(number) in {int, float} and math.isfinite(number) and 0 <= number <= limit
        except OverflowError:
            valid = False
        if not valid:
            raise BenchmarkError("benchmark_mapping_anchor_point_invalid")


def validate_mapping_anchors(candidate, anchors):
    """Validate 2..32 distinct corresponding points in continuous canvas bounds."""
    _candidate(candidate)
    if type(anchors) is not dict or set(anchors) != {
        "schema", "authority", "candidate_sha256", "anchors",
    } or anchors["schema"] != SCHEMA or anchors["authority"] != "none":
        raise BenchmarkError("benchmark_mapping_anchors_invalid")
    require_digest(anchors["candidate_sha256"])
    if anchors["candidate_sha256"] != canonical_sha256(candidate):
        raise BenchmarkError("benchmark_mapping_anchor_candidate_mismatch")
    points = anchors["anchors"]
    if type(points) is not list or not 2 <= len(points) <= 32:
        raise BenchmarkError("benchmark_mapping_anchor_count_invalid")
    ids, png_points, psd_points = set(), set(), set()
    for point in points:
        if type(point) is not dict or set(point) != {"id", "png", "psd"} or \
                type(point["id"]) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", point["id"]):
            raise BenchmarkError("benchmark_mapping_anchor_invalid")
        _point(point["png"], candidate["png_source"]["canvas"])
        _point(point["psd"], candidate["psd_source"]["canvas"])
        if point["id"] in ids or tuple(point["png"]) in png_points or tuple(point["psd"]) in psd_points:
            raise BenchmarkError("benchmark_mapping_anchor_duplicate")
        ids.add(point["id"])
        png_points.add(tuple(point["png"]))
        psd_points.add(tuple(point["psd"]))
    return deepcopy(anchors)


def _fit_axis(points, axis):
    source = [float(point["png"][axis]) for point in points]
    target = [float(point["psd"][axis]) for point in points]
    if min(max(values) - min(values) for values in (source, target)) < PROFILE["min_axis_span_px"]:
        raise BenchmarkError("anchor_span_insufficient")
    center_x, center_y = math.fsum(source) / len(points), math.fsum(target) / len(points)
    dx = [value - center_x for value in source]
    dy = [value - center_y for value in target]
    slope = math.fsum(x * y for x, y in zip(dx, dy)) / math.fsum(x * x for x in dx)
    if slope == 0:
        raise BenchmarkError("anchor_transform_singular")
    intercept = center_y - slope * center_x
    if not all(math.isfinite(number) for number in (slope, intercept)):
        raise BenchmarkError("anchor_numeric_failure")
    return slope, intercept


def fit_mapping_anchors(candidate, anchors):
    """Fit independent X/Y scale and translation; rotation/shear are unsupported."""
    anchors = validate_mapping_anchors(candidate, anchors)
    points = anchors["anchors"]
    report = {"schema": REPORT_SCHEMA, "authority": "none",
              "candidate_sha256": canonical_sha256(candidate),
              "anchors_sha256": canonical_sha256(anchors), "algorithm_profile": deepcopy(PROFILE),
              "status": "blocked", "reason_codes": [], "transform": None,
              "residuals": [], "rmse_px": None, "max_residual_px": None,
              "max_residual_relative_height": None, "fitted_candidate": None}
    try:
        fitted = [_fit_axis(points, axis) for axis in (0, 1)]
    except BenchmarkError as exc:
        report["reason_codes"].append(exc.reason_code)
        return report
    transform = {"scale": [row[0] for row in fitted], "translation": [row[1] for row in fitted],
                 "coordinate_system": COORDINATE_SYSTEM}
    try:
        for key, inverse in (("png_source", False), ("psd_source", True)):
            width, height = candidate[key]["canvas"]
            for x in (0, width):
                for y in (0, height):
                    transform_point(transform, [x, y], inverse=inverse)
    except BenchmarkError:
        report["reason_codes"].append("anchor_numeric_failure")
        return report
    residuals = []
    for point in points:
        delta = [point["png"][axis] * fitted[axis][0] + fitted[axis][1] - point["psd"][axis]
                 for axis in (0, 1)]
        residuals.append({"id": point["id"], "delta": delta, "distance_px": math.hypot(*delta)})
    maximum = max(row["distance_px"] for row in residuals)
    report.update(transform=transform, residuals=residuals,
                  rmse_px=math.sqrt(math.fsum(row["distance_px"] ** 2 for row in residuals) / len(points)),
                  max_residual_px=maximum,
                  max_residual_relative_height=maximum / candidate["psd_source"]["canvas"][1])
    if len(points) == 2:
        report["reason_codes"].append("underconstrained_validation")
    if report["max_residual_relative_height"] > PROFILE["max_residual_relative_height"]:
        report["reason_codes"].append("anchor_residual_high")
        return report
    report["status"] = "needs_review"
    proposed = deepcopy(candidate)
    proposed.update(source_to_psd_transform=transform, basis="explicit_transform_draft")
    report["fitted_candidate"] = proposed
    return report


def validate_mapping_calibration(candidate, anchors, report):
    """Recompute every derived field, including status and profile; reject edits."""
    expected = fit_mapping_anchors(candidate, anchors)
    try:
        matches = canonical_sha256(expected) == canonical_sha256(report)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BenchmarkError("benchmark_mapping_calibration_invalid") from exc
    if not matches:
        raise BenchmarkError("benchmark_mapping_calibration_mismatch")
    return deepcopy(expected)
