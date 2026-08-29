"""Standalone interval and least-squares math checks for foot-lock reports."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any


MAX_NUMBER = 1_000_000_000_000.0
TOLERANCE = 5e-7
_CONTACT = {
    "contact_id", "limb", "proximal_bone_id", "distal_bone_id",
    "start_tick", "end_tick", "anchor_source_frame_index",
    "anchor_endpoint_px",
}
_SAMPLE = {
    "source_frame_index", "tick", "support_state", "state",
    "active_contact_ids", "observations", "correction_candidate_px",
    "correction_magnitude_px", "correction_reference_ratio",
    "maximum_residual_px",
}
_OBSERVATION = {
    "contact_id", "limb", "current_endpoint_px", "desired_correction_px",
    "residual_after_candidate_px", "residual_magnitude_px",
    "residual_reference_ratio",
}
_SUMMARY = {
    "status", "sample_count", "contact_count", "unconstrained_count",
    "candidate_count", "rejected_limit_count", "rejected_conflict_count",
    "maximum_correction_px", "maximum_correction_reference_ratio",
    "maximum_residual_px",
}


class FootLockCandidateMathError(ValueError):
    """Raised when stored candidate interval or solver math is stale."""


def require_contacts(value) -> list[Mapping[str, Any]]:
    rows = _array(value, "Foot-lock candidate contacts")
    if len(rows) > 256:
        raise FootLockCandidateMathError("Foot-lock contact limit exceeded")
    previous = None
    limb_end: dict[str, int] = {}
    result = []
    for index, raw in enumerate(rows):
        row = _object(raw, "Foot-lock contact")
        _exact(row, _CONTACT, "Foot-lock contact")
        limb = row.get("limb")
        side = limb.split(".")[-1] if limb in {"leg.left", "leg.right"} else ""
        identity = (row.get("start_tick"), row.get("end_tick"), limb)
        if row.get("contact_id") != f"contact-{index:03d}" \
                or row.get("proximal_bone_id") != f"thigh.{side}" \
                or row.get("distal_bone_id") != f"calf.{side}" \
                or not _interval(row) \
                or row["start_tick"] < limb_end.get(str(limb), -1) \
                or previous is not None and identity <= previous:
            raise FootLockCandidateMathError(
                "Foot-lock contacts must be canonical half-open leg intervals"
            )
        _frame_index(row.get("anchor_source_frame_index"))
        vector(row.get("anchor_endpoint_px"))
        limb_end[str(limb)] = row["end_tick"]
        previous = identity
        result.append(row)
    return result


def require_samples(value, contacts, reference, correction_limit, residual_limit):
    rows = _array(value, "Foot-lock candidate samples")
    if not 2 <= len(rows) <= 4096:
        raise FootLockCandidateMathError("Foot-lock sample count is invalid")
    states, corrections, ratios, residuals, previous_tick = [], [], [], [], -1
    for index, raw in enumerate(rows):
        row = _object(raw, "Foot-lock candidate sample")
        _exact(row, _SAMPLE, "Foot-lock candidate sample")
        tick = row.get("tick")
        if type(row.get("source_frame_index")) is not int \
                or row["source_frame_index"] != index \
                or type(tick) is not int or tick <= previous_tick:
            raise FootLockCandidateMathError(
                "Foot-lock sample schedule is invalid"
            )
        previous_tick = tick
        active = [
            contact for contact in contacts
            if contact["start_tick"] <= tick < contact["end_tick"]
        ]
        _sample_math(row, active, reference, correction_limit, residual_limit)
        states.append(row["state"])
        if active:
            corrections.append(row["correction_magnitude_px"])
            ratios.append(row["correction_reference_ratio"])
            residuals.append(row["maximum_residual_px"])
    return rows, states, corrections, ratios, residuals


def _sample_math(row, active, reference, correction_limit, residual_limit):
    ids = [contact["contact_id"] for contact in active]
    if row.get("active_contact_ids") != ids:
        raise FootLockCandidateMathError(
            "Foot-lock active contact set is inconsistent"
        )
    observations = _array(row.get("observations"), "Foot-lock observations")
    if not active:
        null_fields = (
            "correction_candidate_px", "correction_magnitude_px",
            "correction_reference_ratio", "maximum_residual_px",
        )
        if row.get("support_state") != "none" \
                or row.get("state") != "unconstrained" \
                or observations or any(row.get(field) is not None for field in null_fields):
            raise FootLockCandidateMathError(
                "Unconstrained foot-lock sample must not invent a correction"
            )
        return
    expected_support = "single_support" if len(active) == 1 else "dual_support"
    if len(active) > 2 or row.get("support_state") != expected_support \
            or len(observations) != len(active):
        raise FootLockCandidateMathError(
            "Foot-lock support state is inconsistent"
        )
    desired = []
    for observation, contact in zip(observations, active):
        _exact(_object(observation, "Foot-lock observation"),
               _OBSERVATION, "Foot-lock observation")
        current = vector(observation.get("current_endpoint_px"))
        wanted = vector(observation.get("desired_correction_px"))
        if observation.get("contact_id") != contact["contact_id"] \
                or observation.get("limb") != contact["limb"] \
                or not vector_close(
                    wanted, _sub(contact["anchor_endpoint_px"], current)
                ):
            raise FootLockCandidateMathError(
                "Foot-lock desired correction differs from its anchor"
            )
        desired.append(wanted)
    correction = vector(row.get("correction_candidate_px"))
    if not vector_close(correction, _mean(desired)):
        raise FootLockCandidateMathError(
            "Foot-lock correction is not the least-squares mean"
        )
    magnitude = number(row.get("correction_magnitude_px"))
    ratio = number(row.get("correction_reference_ratio"))
    if not close(magnitude, _magnitude(correction)) \
            or not close(ratio, magnitude / reference):
        raise FootLockCandidateMathError(
            "Foot-lock correction magnitude or ratio is inconsistent"
        )
    residual_max = 0.0
    for observation, wanted in zip(observations, desired):
        residual = vector(observation.get("residual_after_candidate_px"))
        residual_magnitude = number(observation.get("residual_magnitude_px"))
        residual_ratio = number(observation.get("residual_reference_ratio"))
        if not vector_close(residual, _sub(correction, wanted)) \
                or not close(residual_magnitude, _magnitude(residual)) \
                or not close(residual_ratio, residual_magnitude / reference):
            raise FootLockCandidateMathError(
                "Foot-lock residual math is inconsistent"
            )
        residual_max = max(residual_max, residual_magnitude)
    maximum = number(row.get("maximum_residual_px"))
    expected_state = "candidate"
    if residual_max > residual_limit:
        expected_state = "rejected_conflict"
    elif ratio > correction_limit:
        expected_state = "rejected_limit"
    if not close(maximum, residual_max) or row.get("state") != expected_state:
        raise FootLockCandidateMathError(
            "Foot-lock threshold state is inconsistent"
        )


def require_summary(value, contact_count, stats) -> None:
    rows, states, corrections, ratios, residuals = stats
    row = _object(value, "Foot-lock candidate summary")
    _exact(row, _SUMMARY, "Foot-lock candidate summary")
    status = "candidate_only"
    if "rejected_conflict" in states:
        status = "rejected_conflict"
    elif "rejected_limit" in states:
        status = "rejected_limit"
    expected = {
        "status": status,
        "sample_count": len(rows),
        "contact_count": contact_count,
        "unconstrained_count": states.count("unconstrained"),
        "candidate_count": states.count("candidate"),
        "rejected_limit_count": states.count("rejected_limit"),
        "rejected_conflict_count": states.count("rejected_conflict"),
        "maximum_correction_px": max(corrections, default=0.0),
        "maximum_correction_reference_ratio": max(ratios, default=0.0),
        "maximum_residual_px": max(residuals, default=0.0),
    }
    from .exact_json_contract import exact_json_equal
    if not exact_json_equal(row, expected):
        raise FootLockCandidateMathError(
            "Foot-lock candidate summary differs from its samples"
        )


def vector(value) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        raise FootLockCandidateMathError("Foot-lock vector is invalid")
    return [number(item) for item in value]


def number(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or abs(float(value)) > MAX_NUMBER:
        raise FootLockCandidateMathError(
            "Foot-lock number must be finite and bounded"
        )
    return float(value)


def vector_close(left, right):
    return all(close(float(a), float(b)) for a, b in zip(left, right))


def close(left, right):
    return math.isclose(left, right, rel_tol=TOLERANCE, abs_tol=TOLERANCE)


def _sub(left, right):
    return [float(left[index]) - float(right[index]) for index in range(2)]


def _mean(values):
    return [sum(row[index] for row in values) / len(values) for index in range(2)]


def _magnitude(value):
    return math.hypot(float(value[0]), float(value[1]))


def _interval(row) -> bool:
    start, end = row.get("start_tick"), row.get("end_tick")
    return type(start) is int and type(end) is int and 0 <= start < end


def _frame_index(value) -> int:
    if type(value) is not int or not 0 <= value < 4096:
        raise FootLockCandidateMathError("Foot-lock frame index is invalid")
    return value


def _object(value, label) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FootLockCandidateMathError(f"{label} must be an object")
    return value


def _array(value, label) -> list[Any]:
    if not isinstance(value, list):
        raise FootLockCandidateMathError(f"{label} must be an array")
    return value


def _exact(value, fields, label) -> None:
    if set(value) != fields:
        raise FootLockCandidateMathError(
            f"{label} fields are incomplete or unsupported"
        )
