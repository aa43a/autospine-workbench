"""Contract for reviewed, cross-checked Kimodo heading evidence."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
import re
from typing import Any

from .heading_evidence_math import (
    HeadingEvidenceMathError,
    map_heading_components,
    unwrap_yaw_degrees,
)


FORMAT = "autospine-heading-evidence"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
TOLERANCE = 5e-7
_SHA = re.compile(r"^[0-9a-f]{64}$")
_AXES = frozenset(("+X", "-X", "+Y", "-Y", "+Z", "-Z"))
_TOP = {
    "format", "format_version", "clip_id", "source", "status", "policy",
    "frames", "summary",
}
_SOURCE = {
    "policy_evidence_sha256", "policy_map_sha256", "p7_motion_ir_sha256",
    "p7_bundle_sha256", "p7_run_sha256", "raw_npz_sha256",
    "kimodo_map_sha256", "p8_projected_motion_sha256", "p8_bundle_sha256",
    "p8_run_sha256", "camera_sha256",
}
_POLICY = {
    "mode", "vector_semantics", "components", "root_local_forward_axis",
    "yaw_convention", "crosscheck", "camera_basis", "depth_positive",
    "candidate_emitted", "decision_emitted", "runtime_timeline_emitted",
}
_FRAME = {
    "source_frame_index", "tick", "raw_components", "world_direction_xyz",
    "camera_screen_x_component", "camera_depth_component",
    "root_forward_camera_screen_x_component",
    "root_forward_camera_depth_component", "raw_yaw_deg",
    "unwrapped_yaw_deg", "root_forward_angle_error_deg",
}


class HeadingEvidenceValidationError(ValueError):
    """Raised when mapped heading evidence is stale or inconsistent."""


def require_heading_evidence(document: Mapping[str, Any]) -> None:
    """Validate status, deterministic mapped math, and review-only policy."""

    try:
        root = _object(document, "Heading evidence")
        _exact(root, _TOP, "Heading evidence")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise HeadingEvidenceValidationError(
                "Heading evidence format is unsupported"
            )
        _identifier(root.get("clip_id"))
        _source(root.get("source"))
        policy = _policy(root.get("policy"))
        status = root.get("status")
        frames = _array(root.get("frames"), "Heading evidence frames")
        if status == "unavailable":
            _unavailable(frames, root.get("summary"))
        elif status == "available":
            _available(frames, root.get("summary"), policy)
        else:
            raise HeadingEvidenceValidationError(
                "Heading evidence status is unsupported"
            )
        encoded = json.dumps(
            dict(root), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise HeadingEvidenceValidationError(
                "Heading evidence byte limit exceeded"
            )
    except HeadingEvidenceValidationError:
        raise
    except (HeadingEvidenceMathError, KeyError, TypeError, ValueError) as exc:
        raise HeadingEvidenceValidationError(
            f"Heading evidence validation failed: {exc}"
        ) from exc


def heading_evidence_sha256(document: Mapping[str, Any]) -> str:
    require_heading_evidence(document)
    return hashlib.sha256(_canonical(document)).hexdigest()


def heading_policy(policy_map: Mapping[str, Any], camera: Mapping[str, Any]) -> dict:
    heading = policy_map["heading"]
    return {
        "mode": "evidence_only",
        "vector_semantics": heading["vector_semantics"],
        "components": json.loads(json.dumps(heading["components"])),
        "root_local_forward_axis": heading["root_local_forward_axis"],
        "yaw_convention": heading["yaw_convention"],
        "crosscheck": json.loads(json.dumps(heading["crosscheck"])),
        "camera_basis": json.loads(json.dumps(camera["basis"])),
        "depth_positive": camera["depth_positive"],
        "candidate_emitted": False,
        "decision_emitted": False,
        "runtime_timeline_emitted": False,
    }


def _source(value) -> None:
    source = _object(value, "Heading evidence source")
    _exact(source, _SOURCE, "Heading evidence source")
    if any(not isinstance(source.get(field), str)
           or not _SHA.fullmatch(source[field]) for field in _SOURCE):
        raise HeadingEvidenceValidationError(
            "Heading evidence source SHA-256 is invalid"
        )


def _policy(value) -> Mapping[str, Any]:
    policy = _object(value, "Heading evidence policy")
    _exact(policy, _POLICY, "Heading evidence policy")
    if policy.get("mode") != "evidence_only" \
            or policy.get("vector_semantics") != "character_forward_world" \
            or policy.get("yaw_convention") != \
            "atan2_camera_screen_x_over_camera_depth" \
            or policy.get("candidate_emitted") is not False \
            or policy.get("decision_emitted") is not False \
            or policy.get("runtime_timeline_emitted") is not False \
            or policy.get("depth_positive") not in {
                "toward_camera", "away_from_camera",
            }:
        raise HeadingEvidenceValidationError(
            "Heading evidence review-only policy is unsupported"
        )
    components = _array(policy.get("components"), "Heading components")
    if len(components) != 2 or any(
        not isinstance(row, Mapping)
        or set(row) != {"index", "source_axis"}
        or row.get("index") != index
        for index, row in enumerate(components)
    ):
        raise HeadingEvidenceValidationError("Heading components are invalid")
    crosscheck = _object(policy.get("crosscheck"), "Heading crosscheck")
    maximum = _number(crosscheck.get("maximum_angle_error_deg"))
    if set(crosscheck) != {"policy", "maximum_angle_error_deg"} \
            or crosscheck.get("policy") != "projected_root_forward_angle" \
            or not 0 <= maximum <= 180:
        raise HeadingEvidenceValidationError("Heading crosscheck is invalid")
    basis = _object(policy.get("camera_basis"), "Heading camera basis")
    if set(basis) != {"screen_x", "screen_y", "depth"} \
            or any(value not in _AXES for value in basis.values()) \
            or len({str(value)[1:] for value in basis.values()}) != 3:
        raise HeadingEvidenceValidationError("Heading camera basis is invalid")
    # The policy-map validator owns plane topology; this checks copied tokens.
    map_heading_components(
        [1.0, 0.0], [row["source_axis"] for row in components], basis
    )
    map_heading_components(
        [0.0, 1.0], [row["source_axis"] for row in components], basis
    )
    if policy.get("root_local_forward_axis") not in {
        "+X", "-X", "+Y", "-Y", "+Z", "-Z",
    }:
        raise HeadingEvidenceValidationError(
            "Heading root local-forward axis is invalid"
        )
    return policy


def _unavailable(frames, value) -> None:
    summary = _object(value, "Heading evidence summary")
    expected = {
        "status": "unavailable",
        "reason_code": "source_heading_unavailable",
        "frame_count": 0,
        "maximum_root_forward_angle_error_deg": None,
    }
    if frames or summary != expected:
        raise HeadingEvidenceValidationError(
            "Unavailable heading evidence must not invent frame values"
        )


def _available(frames, value, policy) -> None:
    if not 2 <= len(frames) <= 4096:
        raise HeadingEvidenceValidationError("Heading frame count is invalid")
    components = [row["source_axis"] for row in policy["components"]]
    raw_yaws, errors, previous_tick = [], [], -1
    for index, raw in enumerate(frames):
        row = _object(raw, "Heading frame")
        _exact(row, _FRAME, "Heading frame")
        tick = row.get("tick")
        if row.get("source_frame_index") != index \
                or type(tick) is not int or tick <= previous_tick:
            raise HeadingEvidenceValidationError(
                "Heading frame schedule is invalid"
            )
        previous_tick = tick
        calculated = _standalone_frame(row, components, policy["camera_basis"])
        for field in (
            "world_direction_xyz", "camera_screen_x_component",
            "camera_depth_component", "raw_yaw_deg",
        ):
            if not _close_value(row[field], calculated[field]):
                raise HeadingEvidenceValidationError(
                    "Heading mapped frame math is inconsistent"
                )
        raw_yaws.append(_number(row["raw_yaw_deg"]))
        root_forward = _unit_pair(row, "root_forward_camera")
        heading_length = math.hypot(
            calculated["camera_screen_x_component"],
            calculated["camera_depth_component"],
        )
        dot = (
            calculated["camera_screen_x_component"] * root_forward[0]
            + calculated["camera_depth_component"] * root_forward[1]
        ) / heading_length
        expected_error = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
        error = _number(row["root_forward_angle_error_deg"])
        if not _close(error, expected_error):
            raise HeadingEvidenceValidationError(
                "Heading root-forward angle math is inconsistent"
            )
        if error > float(policy["crosscheck"]["maximum_angle_error_deg"]) \
                + TOLERANCE:
            raise HeadingEvidenceValidationError(
                "Heading root-forward crosscheck exceeds its reviewed limit"
            )
        errors.append(error)
    unwrapped = unwrap_yaw_degrees(raw_yaws)
    if any(not _close(row["unwrapped_yaw_deg"], expected)
           for row, expected in zip(frames, unwrapped)):
        raise HeadingEvidenceValidationError("Heading yaw unwrap is inconsistent")
    summary = _object(value, "Heading evidence summary")
    expected = {
        "status": "available",
        "reason_code": None,
        "frame_count": len(frames),
        "maximum_root_forward_angle_error_deg": max(errors),
    }
    if summary != expected:
        raise HeadingEvidenceValidationError(
            "Heading evidence summary differs from its frames"
        )


def _standalone_frame(row, components, basis):
    return map_heading_components(
        _vector(row["raw_components"], 2), components, basis
    )


def _unit_pair(row, prefix) -> tuple[float, float]:
    left = _number(row[f"{prefix}_screen_x_component"])
    depth = _number(row[f"{prefix}_depth_component"])
    if not math.isclose(math.hypot(left, depth), 1.0, abs_tol=TOLERANCE):
        raise HeadingEvidenceValidationError("Heading root-forward is not unit")
    return left, depth


def _vector(value, length):
    row = _array(value, "Heading vector")
    if len(row) != length:
        raise HeadingEvidenceValidationError("Heading vector length is invalid")
    return [_number(item) for item in row]


def _number(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or abs(float(value)) > 1e12:
        raise HeadingEvidenceValidationError(
            "Heading number must be finite and bounded"
        )
    return float(value)


def _close_value(left, right) -> bool:
    if isinstance(right, list):
        return isinstance(left, list) and len(left) == len(right) and all(
            _close(a, b) for a, b in zip(left, right)
        )
    return _close(left, right)


def _close(left, right) -> bool:
    return math.isclose(_number(left), _number(right), rel_tol=TOLERANCE,
                        abs_tol=TOLERANCE)


def _identifier(value) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= 128 \
            or not value[0].isalnum() \
            or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
                   for char in value):
        raise HeadingEvidenceValidationError("Heading clip id is invalid")


def _object(value, label) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HeadingEvidenceValidationError(f"{label} must be an object")
    return value


def _array(value, label) -> list[Any]:
    if not isinstance(value, list):
        raise HeadingEvidenceValidationError(f"{label} must be an array")
    return value


def _exact(value, fields, label) -> None:
    if set(value) != fields:
        raise HeadingEvidenceValidationError(
            f"{label} fields are incomplete or unsupported"
        )


def _canonical(value) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
