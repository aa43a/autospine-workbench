"""Strict per-sample validation for setup regression reports."""

from __future__ import annotations

import hashlib
import json
import math

from .manifest_artifacts import require_safe_token, require_sha256


_SAMPLE_FIELDS = {
    "project_id", "source", "actual", "approved", "metrics",
    "thresholds", "reason_codes", "status", "comparison_sha256",
}
_SOURCE_FIELDS = {
    "p3_rig_sha256", "p3_bundle_sha256", "p6_skeleton_json_sha256",
    "p6_bundle_sha256", "spine42_v3_skeleton_json_sha256",
    "spine42_v3_bundle_sha256", "runtime_capture_bundle_sha256",
    "capture_plan_sha256", "runtime_session_set_sha256",
    "runtime_capture_manifest_sha256", "spine42_v3_run_document_sha256",
    "raster_metrics_sha256",
}
_IMAGE_FIELDS = {
    "artifact_id", "case_id", "kind", "animation", "tick",
    "png_sha256", "rgba_sha256", "width", "height",
}
_APPROVED_IMAGE_FIELDS = {
    "runtime_case_id", "png_sha256", "rgba_sha256", "width", "height",
}
_METRIC_FIELDS = {
    "differing_pixels", "differing_pixel_ratio", "mean_absolute_error",
    "max_channel_delta",
}
_THRESHOLD_FIELDS = {
    "max_differing_pixel_ratio", "max_mean_absolute_error",
    "max_channel_delta",
}
HASH_DOMAIN = "autospine-spine42-v3-setup-regression-sample/v1"


class Spine42V3SetupRegressionSampleError(ValueError):
    """Raised when a report sample is inconsistent with its request row."""


def require_setup_regression_sample(value, expected):
    """Validate identities, metrics, thresholds, and the derived outcome."""

    if type(value) is not dict or set(value) != _SAMPLE_FIELDS \
            or value.get("project_id") != expected["project_id"]:
        raise Spine42V3SetupRegressionSampleError(
            "Setup regression sample fields are invalid"
        )
    source = _object(value.get("source"), _SOURCE_FIELDS, "source")
    for field in _SOURCE_FIELDS:
        require_sha256(source[field], field)
    p6, spine, runtime = (
        expected["p6_setup_address"], expected["spine42_v3_address"],
        expected["runtime_capture_address"],
    )
    if (
        source["p3_rig_sha256"], source["p3_bundle_sha256"],
        source["p6_skeleton_json_sha256"], source["p6_bundle_sha256"],
        source["spine42_v3_skeleton_json_sha256"],
        source["spine42_v3_bundle_sha256"],
        source["runtime_capture_bundle_sha256"],
    ) != (
        expected["p3_rig_sha256"], expected["p3_bundle_sha256"],
        p6["skeleton_json_sha256"], p6["bundle_sha256"],
        spine["skeleton_json_sha256"], spine["bundle_sha256"],
        runtime["capture_bundle_sha256"],
    ):
        raise Spine42V3SetupRegressionSampleError(
            "Setup regression sample source is cross-wired"
        )
    actual = _image(value.get("actual"), _IMAGE_FIELDS, "artifact_id")
    if actual["case_id"] != "setup" or actual["kind"] != "opaque_composite" \
            or actual["animation"] is not None \
            or type(actual["tick"]) is not int or actual["tick"] != 0:
        raise Spine42V3SetupRegressionSampleError(
            "Setup regression actual image is not the setup opaque frame"
        )
    approved = _image(
        value.get("approved"), _APPROVED_IMAGE_FIELDS, "runtime_case_id"
    )
    if approved["runtime_case_id"] != expected["approved_runtime_case_id"] \
            or approved["png_sha256"] != expected["approved_png_sha256"] \
            or (actual["width"], actual["height"]) != \
                (approved["width"], approved["height"]):
        raise Spine42V3SetupRegressionSampleError(
            "Setup regression approved image is cross-wired"
        )
    metrics = _metrics(value.get("metrics"))
    thresholds = _thresholds(value.get("thresholds"))
    pixels = actual["width"] * actual["height"]
    differing = metrics["differing_pixels"]
    nonzero = differing > 0
    if differing > pixels \
            or metrics["differing_pixel_ratio"] != differing / pixels \
            or (metrics["mean_absolute_error"] > 0) is not nonzero \
            or (metrics["max_channel_delta"] > 0) is not nonzero:
        raise Spine42V3SetupRegressionSampleError(
            "Setup regression metric arithmetic is inconsistent"
        )
    reasons = threshold_reason_codes(metrics, thresholds)
    if value.get("reason_codes") != reasons \
            or value.get("status") != ("passed" if not reasons else "rejected"):
        raise Spine42V3SetupRegressionSampleError(
            "Setup regression sample result is inconsistent"
        )
    if value.get("comparison_sha256") != setup_regression_sample_sha256(value):
        raise Spine42V3SetupRegressionSampleError(
            "Setup regression sample identity is invalid"
        )
    return _copy(value)


def setup_regression_sample_sha256(value):
    """Return the domain-separated identity of one sample body."""

    if type(value) is not dict:
        raise Spine42V3SetupRegressionSampleError(
            "Setup regression sample is invalid"
        )
    body = _copy(value)
    body.pop("comparison_sha256", None)
    return hashlib.sha256(_canonical({
        "domain": HASH_DOMAIN, "sample": body,
    })).hexdigest()


def threshold_reason_codes(metrics, thresholds):
    """Derive stable failure reasons from approved thresholds."""

    tests = (
        ("differing_pixel_ratio_exceeded", "differing_pixel_ratio",
         "max_differing_pixel_ratio"),
        ("mean_absolute_error_exceeded", "mean_absolute_error",
         "max_mean_absolute_error"),
        ("max_channel_delta_exceeded", "max_channel_delta", "max_channel_delta"),
    )
    return [reason for reason, metric, limit in tests
            if metrics[metric] > thresholds[limit]]


def _image(value, fields, identity):
    row = _object(value, fields, "image")
    require_safe_token(row[identity], identity)
    require_sha256(row["png_sha256"], "PNG")
    require_sha256(row["rgba_sha256"], "RGBA")
    if any(type(row[key]) is not int or not 1 <= row[key] <= 4096
           for key in ("width", "height")):
        raise Spine42V3SetupRegressionSampleError("Setup image size is invalid")
    return row


def _metrics(value):
    row = _object(value, _METRIC_FIELDS, "metrics")
    if type(row["differing_pixels"]) is not int or row["differing_pixels"] < 0 \
            or type(row["max_channel_delta"]) is not int \
            or not 0 <= row["max_channel_delta"] <= 255:
        raise Spine42V3SetupRegressionSampleError("Setup metrics are invalid")
    _finite(row["differing_pixel_ratio"], 0, 1)
    _finite(row["mean_absolute_error"], 0, 255)
    return row


def _thresholds(value):
    row = _object(value, _THRESHOLD_FIELDS, "thresholds")
    _finite(row["max_differing_pixel_ratio"], 0, 1)
    _finite(row["max_mean_absolute_error"], 0, 255)
    if type(row["max_channel_delta"]) is not int \
            or not 0 <= row["max_channel_delta"] <= 255:
        raise Spine42V3SetupRegressionSampleError("Setup thresholds are invalid")
    return row


def _finite(value, low, high):
    if type(value) not in {int, float} or not math.isfinite(value) \
            or not low <= value <= high:
        raise Spine42V3SetupRegressionSampleError("Setup metric is not finite")


def _object(value, fields, label):
    if type(value) is not dict or set(value) != fields:
        raise Spine42V3SetupRegressionSampleError(
            f"Setup regression {label} fields are invalid"
        )
    return value


def _copy(value):
    try:
        return json.loads(_canonical(value))
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise Spine42V3SetupRegressionSampleError(
            "Setup regression sample is not finite JSON"
        ) from exc


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


__all__ = [
    "Spine42V3SetupRegressionSampleError",
    "require_setup_regression_sample", "setup_regression_sample_sha256",
    "threshold_reason_codes",
]
