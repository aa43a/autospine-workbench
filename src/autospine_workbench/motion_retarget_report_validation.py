"""Resource-bounded structural contract for P5 retarget evidence reports."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
from typing import Any

from .motion_instance_sampling import SAMPLE_STEP_TICKS


FORMAT, FORMAT_VERSION = "autospine-motion-retarget-report", 1
TOLERANCE = 1e-8
MAX_REPORT_BYTES, MAX_SAMPLE_COUNT = 256 * 1024, 50_000
SAMPLER_POLICY = "fixed-step-plus-authored-keys-and-duration"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOP = {
    "format", "format_version", "status", "source", "sampler",
    "finite_pose", "loop_closure", "ik", "contacts",
}
_SOURCE = {
    "motion_ir_sha256", "motion_bundle_sha256", "motion_run_sha256",
    "target_profile_sha256", "instance_sha256",
    "retarget_run_identity_sha256", "retarget_run_document_sha256",
}


class MotionRetargetReportShapeError(ValueError):
    """Raised when report JSON is malformed, unbounded, or non-passing."""


def require_motion_retarget_report_shape(document: Mapping[str, Any]) -> None:
    """Fail closed on the complete static report shape and resource limits."""

    root = _object(document, "report")
    _exact(root, _TOP, "report")
    if root.get("format") != FORMAT or root.get("format_version") != FORMAT_VERSION \
            or type(root.get("format_version")) is not int \
            or root.get("status") != "passed":
        raise MotionRetargetReportShapeError(
            "Retarget report identity/status is invalid"
        )
    _source_shape(root.get("source"))
    sampler = _sampler_shape(root.get("sampler"))
    _finite_shape(root.get("finite_pose"), sampler)
    _loop_shape(root.get("loop_closure"))
    _ik_shape(root.get("ik"))
    _contact_shape(root.get("contacts"))
    try:
        encoded = json.dumps(
            dict(root), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (OverflowError, TypeError, ValueError) as exc:
        raise MotionRetargetReportShapeError(
            "Retarget report is not finite canonical JSON"
        ) from exc
    if len(encoded) > MAX_REPORT_BYTES:
        raise MotionRetargetReportShapeError(
            "Retarget report byte limit exceeded"
        )


def _source_shape(value):
    source = _object(value, "source")
    _exact(source, _SOURCE, "source")
    if any(not isinstance(source.get(key), str)
           or not _SHA256.fullmatch(source[key]) for key in _SOURCE):
        raise MotionRetargetReportShapeError(
            "Retarget report source SHA is invalid"
        )


def _sampler_shape(value):
    sampler = _object(value, "sampler")
    _exact(sampler, {"step_ticks", "policy", "sample_count"}, "sampler")
    if type(sampler.get("step_ticks")) is not int \
            or sampler.get("step_ticks") != SAMPLE_STEP_TICKS \
            or sampler.get("policy") != SAMPLER_POLICY:
        raise MotionRetargetReportShapeError(
            "Retarget sampler contract drifted"
        )
    _count(sampler.get("sample_count"), 1, MAX_SAMPLE_COUNT, "sample count")
    return sampler


def _finite_shape(value, sampler):
    finite = _object(value, "finite pose")
    fields = {
        "status", "bone_count", "world_bone_sample_count",
        "max_abs_rotation_deg", "max_root_translation_px",
    }
    _exact(finite, fields, "finite pose")
    if finite.get("status") != "passed":
        raise MotionRetargetReportShapeError("Finite pose check did not pass")
    bones = _count(finite.get("bone_count"), 1, 17, "bone count")
    samples = sampler["sample_count"]
    if _count(finite.get("world_bone_sample_count"), 1, 850_000,
              "world sample count") != bones * samples:
        raise MotionRetargetReportShapeError(
            "World sample count is inconsistent"
        )
    _nonnegative(finite.get("max_abs_rotation_deg"), "maximum rotation")
    _nonnegative(finite.get("max_root_translation_px"), "maximum translation")


def _loop_shape(value):
    loop = _object(value, "loop closure")
    result = loop.get("result")
    fields = {"result", "tolerance"} | (
        {"maximum_numeric_error"} if result == "passed" else set()
    )
    _exact(loop, fields, "loop closure")
    if result not in {"passed", "not_applicable"} \
            or loop.get("tolerance") != TOLERANCE:
        raise MotionRetargetReportShapeError("Loop closure result is invalid")
    if "maximum_numeric_error" in loop:
        _bounded(loop["maximum_numeric_error"], TOLERANCE, "loop error")


def _ik_shape(value):
    ik = _object(value, "IK")
    fields = {
        "status", "tolerance_px", "track_count", "key_count",
        "setup_key_count", "maximum_effector_error_px", "tracks",
    }
    _exact(ik, fields, "IK")
    tracks = ik.get("tracks")
    if ik.get("status") != "passed" or ik.get("tolerance_px") != TOLERANCE \
            or not isinstance(tracks, list):
        raise MotionRetargetReportShapeError("IK summary is invalid")
    if _count(ik.get("track_count"), 0, 4, "IK track count") != len(tracks):
        raise MotionRetargetReportShapeError("IK track count differs")
    keys, setups, handles = 0, 0, []
    for item in tracks:
        row = _object(item, "IK track")
        _exact(row, {"handle_id", "key_count", "setup_key_count",
                     "maximum_effector_error_px"}, "IK track")
        handle = row.get("handle_id")
        if not isinstance(handle, str):
            raise MotionRetargetReportShapeError("IK handle id is invalid")
        handles.append(handle)
        count = _count(row.get("key_count"), 2, 4096, "IK key count")
        setup = _count(row.get("setup_key_count"), 0, count, "IK setup count")
        _bounded(row.get("maximum_effector_error_px"), TOLERANCE, "IK error")
        keys, setups = keys + count, setups + setup
    aggregate_keys = _count(ik.get("key_count"), 0, 16_384, "IK total keys")
    aggregate_setup = _count(
        ik.get("setup_key_count"), 0, aggregate_keys, "IK total setup keys"
    )
    if handles != sorted(handles) or len(handles) != len(set(handles)) \
            or aggregate_keys != keys or aggregate_setup != setups:
        raise MotionRetargetReportShapeError("IK track aggregation is invalid")
    _bounded(ik.get("maximum_effector_error_px"), TOLERANCE, "IK maximum error")


def _contact_shape(value):
    contacts = _object(value, "contacts")
    _exact(contacts, {"status", "source_count", "preserved_count"}, "contacts")
    source = _count(contacts.get("source_count"), 0, 256, "contact count")
    preserved = _count(
        contacts.get("preserved_count"), 0, 256, "preserved contact count"
    )
    if contacts.get("status") != "passed" or preserved != source:
        raise MotionRetargetReportShapeError(
            "Contact preservation did not pass"
        )


def _object(value, label):
    if not isinstance(value, Mapping):
        raise MotionRetargetReportShapeError(
            f"Retarget {label} must be an object"
        )
    return value


def _exact(value, fields, label):
    if set(value) != fields:
        raise MotionRetargetReportShapeError(
            f"Retarget {label} fields are unsupported"
        )


def _nonnegative(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or value < 0:
        raise MotionRetargetReportShapeError(
            f"Retarget {label} is invalid"
        )
    return float(value)


def _bounded(value, maximum, label):
    result = _nonnegative(value, label)
    if result > maximum:
        raise MotionRetargetReportShapeError(
            f"Retarget {label} exceeds tolerance"
        )
    return result


def _count(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise MotionRetargetReportShapeError(
            f"Retarget {label} is invalid"
        )
    return value
