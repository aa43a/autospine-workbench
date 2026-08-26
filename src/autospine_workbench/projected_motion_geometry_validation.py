"""Geometry and topology invariants for ProjectedMotionIR segment tracks."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from .motion_roles import CANONICAL_BONE_ROLE_ITEMS, nearest_mapped_parent_role


MAX_TRACKS = len(CANONICAL_BONE_ROLE_ITEMS)
MAX_ABS_NORMALIZED = 1024.0
MAX_ABS_ANGLE_DEG = 1_000_000.0
NUMERIC_TOLERANCE = 5e-4
COLLAPSE_SEGMENT_RATIO = 1e-6
COLLAPSE_REFERENCE_RATIO = 1e-9
_TRACK = {
    "role", "source_joint_name", "aim_joint_name", "delta_parent_role",
    "setup_source_length_normalized", "setup_projected_length_normalized",
    "samples",
}
_SAMPLE = {
    "source_frame_index", "tick", "projected_vector_normalized",
    "source_length_normalized", "projected_length_normalized",
    "foreshortening_ratio", "depth_cosine", "projected_world_angle_deg",
    "start_depth_root_relative_normalized",
    "end_depth_root_relative_normalized",
    "midpoint_depth_root_relative_normalized", "projection_state",
}


class ProjectedMotionValidationError(ValueError):
    """Raised when projected 3D-to-2D evidence is ambiguous or unsafe."""


def require_projected_segment_tracks(value: Any, frames, loop: bool) -> None:
    """Validate canonical roles and every segment geometry sample."""

    tracks = _array(value, "ProjectedMotionIR segment tracks")
    if not 1 <= len(tracks) <= MAX_TRACKS:
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR track resource limit exceeded"
        )
    role_order = {
        role: index for index, (role, _bone_id)
        in enumerate(CANONICAL_BONE_ROLE_ITEMS)
    }
    indexed: dict[str, Mapping[str, Any]] = {}
    previous = -1
    for raw in tracks:
        track = _object(raw, "ProjectedMotionIR segment track")
        _exact(track, _TRACK, "ProjectedMotionIR segment track")
        role = track.get("role")
        order = role_order.get(role, -1)
        if order <= previous or role in indexed:
            raise ProjectedMotionValidationError(
                "ProjectedMotionIR tracks must be canonically sorted and unique"
            )
        previous = order
        _name(track.get("source_joint_name"), "source_joint_name")
        _name(track.get("aim_joint_name"), "aim_joint_name")
        indexed[str(role)] = track
    for role, track in indexed.items():
        expected_parent = nearest_mapped_parent_role(role, indexed)
        if track.get("delta_parent_role") != expected_parent:
            raise ProjectedMotionValidationError(
                "ProjectedMotionIR delta parent topology is invalid"
            )
        _samples(track, frames, loop)


def _samples(track: Mapping[str, Any], frames, loop: bool) -> None:
    setup_source = _positive(
        track.get("setup_source_length_normalized"), "setup source length"
    )
    setup_projected = _nonnegative(
        track.get("setup_projected_length_normalized"),
        "setup projected length",
    )
    rows = _array(track.get("samples"), "ProjectedMotionIR segment samples")
    if len(rows) != len(frames):
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR segment samples differ from frames"
        )
    payloads, angles = [], []
    for expected, raw in zip(frames, rows):
        row = _object(raw, "ProjectedMotionIR segment sample")
        _exact(row, _SAMPLE, "ProjectedMotionIR segment sample")
        if row.get("source_frame_index") != expected[0] \
                or row.get("tick") != expected[1]:
            raise ProjectedMotionValidationError(
                "ProjectedMotionIR segment sample differs from frames"
            )
        payload, angle, state = _geometry(row)
        payloads.append(payload)
        angles.append((angle, state))
    first = rows[0]
    if not _close(setup_source, float(first["source_length_normalized"])) \
            or not _close(
                setup_projected, float(first["projected_length_normalized"])
            ):
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR setup lengths differ from frame zero"
        )
    for left, right in zip(angles, angles[1:]):
        if left[1] == right[1] == "observable" \
                and abs(right[0] - left[0]) > 180.0 + NUMERIC_TOLERANCE:
            raise ProjectedMotionValidationError(
                "ProjectedMotionIR angle contains a wrapped jump"
            )
    if loop and payloads[0] != payloads[-1]:
        raise ProjectedMotionValidationError(
            "Looping ProjectedMotionIR segment endpoints must match"
        )


def _geometry(row: Mapping[str, Any]):
    vector = _vector2(row.get("projected_vector_normalized"), "segment vector")
    source = _positive(row.get("source_length_normalized"), "source length")
    projected = _nonnegative(
        row.get("projected_length_normalized"), "projected length"
    )
    ratio = _number(row.get("foreshortening_ratio"), "foreshortening", 1.001)
    cosine = _number(row.get("depth_cosine"), "depth cosine", 1.001)
    angle = _number(
        row.get("projected_world_angle_deg"), "world angle", MAX_ABS_ANGLE_DEG
    )
    start = _number(
        row.get("start_depth_root_relative_normalized"), "start depth",
        MAX_ABS_NORMALIZED,
    )
    end = _number(
        row.get("end_depth_root_relative_normalized"), "end depth",
        MAX_ABS_NORMALIZED,
    )
    midpoint = _number(
        row.get("midpoint_depth_root_relative_normalized"), "midpoint depth",
        MAX_ABS_NORMALIZED,
    )
    if ratio < 0 or not _close(projected, math.hypot(*vector)) \
            or not _close(ratio, projected / source) \
            or not _close(cosine, (end - start) / source) \
            or not _close(midpoint, (start + end) / 2.0) \
            or not _close(ratio * ratio + cosine * cosine, 1.0):
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR segment geometry is inconsistent"
        )
    minimum = max(source * COLLAPSE_SEGMENT_RATIO, COLLAPSE_REFERENCE_RATIO)
    state = "observable" if projected > minimum else "collapsed"
    if row.get("projection_state") != state:
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR projection state is inconsistent"
        )
    if state == "observable":
        expected = math.degrees(math.atan2(vector[1], vector[0]))
        if abs(_wrapped_delta(angle, expected)) > NUMERIC_TOLERANCE:
            raise ProjectedMotionValidationError(
                "ProjectedMotionIR angle differs from its projected vector"
            )
    payload = (
        vector, source, projected, ratio, cosine, angle, start, end, midpoint,
        state,
    )
    return payload, angle, state


def _vector2(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ProjectedMotionValidationError(
            f"ProjectedMotionIR {label} must contain x and y"
        )
    return (
        _number(value[0], f"{label} x", MAX_ABS_NORMALIZED),
        _number(value[1], f"{label} y", MAX_ABS_NORMALIZED),
    )


def _positive(value: Any, label: str) -> float:
    result = _number(value, label, MAX_ABS_NORMALIZED)
    if result <= 0:
        raise ProjectedMotionValidationError(
            f"ProjectedMotionIR {label} must be positive"
        )
    return result


def _nonnegative(value: Any, label: str) -> float:
    result = _number(value, label, MAX_ABS_NORMALIZED)
    if result < 0:
        raise ProjectedMotionValidationError(
            f"ProjectedMotionIR {label} must be non-negative"
        )
    return result


def _number(value: Any, label: str, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or abs(float(value)) > maximum:
        raise ProjectedMotionValidationError(
            f"ProjectedMotionIR {label} must be finite and bounded"
        )
    return float(value)


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128 \
            or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for char in value):
        raise ProjectedMotionValidationError(
            f"ProjectedMotionIR {label} is invalid"
        )
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProjectedMotionValidationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProjectedMotionValidationError(f"{label} must be an array")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise ProjectedMotionValidationError(
            f"{label} fields are incomplete or unsupported"
        )


def _close(left: float, right: float) -> bool:
    return math.isclose(
        left, right, rel_tol=NUMERIC_TOLERANCE, abs_tol=NUMERIC_TOLERANCE
    )


def _wrapped_delta(left: float, right: float) -> float:
    return (left - right + 180.0) % 360.0 - 180.0
