"""Strict invariants for target-rig foreshortening candidate probes."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
from typing import Any

from .motion_roles import CANONICAL_BONE_ROLE_ITEMS
from .motion_target_validation import (
    MotionTargetValidationError,
    require_motion_target_profile,
)
from .projected_motion_bundle_integrity import VerifiedProjectedMotionBundle
from .projected_motion_validation import require_projected_motion_ir
from .resolved_project import canonical_sha256


FORMAT = "autospine-projected-scale-probes"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
MAX_SCALE = 1_000_000_000.0
MAX_LENGTH_PX = 1_000_000_000_000.0
TOLERANCE = 5e-5
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOP = {"format", "format_version", "project_id", "clip_id", "source",
        "policy", "summary", "tracks"}
_SOURCE = {
    "projected_motion_sha256", "projected_bundle_sha256", "camera_sha256",
    "p7_motion_sha256", "target_profile_sha256", "p3_rig_sha256",
    "p3_bundle_sha256",
}
_POLICY = {
    "mode": "candidate_only",
    "formula": "foreshortening_ratio_over_setup_ratio",
    "application": "independent_target_bone_length_probe",
    "baseline": "source_frame0",
    "target_scale_contract": "positive-unit-only-unchanged",
    "runtime_timeline_emitted": False,
    "depth_consumption": "none",
    "collapsed_policy": "reject_report",
}
_SUMMARY = {
    "status", "track_count", "sample_count", "collapsed_sample_count",
    "minimum_scale_x_candidate", "maximum_scale_x_candidate",
}
_TRACK = {
    "role", "bone_id", "setup_length_px",
    "setup_foreshortening_ratio", "samples",
}
_SAMPLE = {
    "source_frame_index", "tick", "foreshortening_ratio",
    "scale_x_candidate", "candidate_length_px", "delta_length_px",
    "projection_state",
}


class ProjectedScaleProbeValidationError(ValueError):
    """Raised when a hypothetical target-rig scale probe is inconsistent."""


def require_projected_scale_probes(
    document: Mapping[str, Any],
    *,
    projected_bundle: VerifiedProjectedMotionBundle | None = None,
    target_profile: Mapping[str, Any] | None = None,
) -> None:
    """Validate standalone report math and optional exact input bindings."""

    try:
        root = _object(document, "Projected scale probes")
        _exact(root, _TOP, "Projected scale probes")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise ProjectedScaleProbeValidationError(
                "Projected scale probe format is unsupported"
            )
        _identifier(root.get("project_id"), "project_id")
        _identifier(root.get("clip_id"), "clip_id")
        source = _source(root.get("source"))
        if root.get("policy") != _POLICY:
            raise ProjectedScaleProbeValidationError(
                "Projected scale probe policy is unsupported"
            )
        tracks, scales, collapsed = _tracks(root.get("tracks"))
        _summary(root.get("summary"), tracks, scales, collapsed)
        if projected_bundle is not None:
            _cross_projected(root, source, projected_bundle)
        if target_profile is not None:
            _cross_target(root, source, target_profile)
        encoded = json.dumps(
            dict(root), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise ProjectedScaleProbeValidationError(
                "Projected scale probe byte limit exceeded"
            )
    except ProjectedScaleProbeValidationError:
        raise
    except (
        MotionTargetValidationError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise ProjectedScaleProbeValidationError(
            f"Projected scale probe validation failed: {exc}"
        ) from exc


def projected_scale_probes_sha256(document: Mapping[str, Any]) -> str:
    require_projected_scale_probes(document)
    return canonical_sha256(document)


def scale_probe_policy() -> dict[str, Any]:
    return dict(_POLICY)


def _source(value: Any) -> Mapping[str, Any]:
    source = _object(value, "Projected scale probe source")
    _exact(source, _SOURCE, "Projected scale probe source")
    for field in _SOURCE:
        if not isinstance(source.get(field), str) \
                or not _SHA.fullmatch(source[field]):
            raise ProjectedScaleProbeValidationError(
                f"Projected scale probe {field} is invalid"
            )
    return source


def _tracks(value: Any):
    rows = _array(value, "Projected scale probe tracks")
    if not 1 <= len(rows) <= len(CANONICAL_BONE_ROLE_ITEMS):
        raise ProjectedScaleProbeValidationError(
            "Projected scale probe track count is invalid"
        )
    order = {
        role: index for index, (role, _bone_id)
        in enumerate(CANONICAL_BONE_ROLE_ITEMS)
    }
    previous, scales, collapsed, sample_count = -1, [], 0, None
    seen_bones: set[str] = set()
    frame_ticks: tuple[int, ...] | None = None
    for raw in rows:
        track = _object(raw, "Projected scale probe track")
        _exact(track, _TRACK, "Projected scale probe track")
        role = track.get("role")
        current = order.get(role, -1)
        if current <= previous:
            raise ProjectedScaleProbeValidationError(
                "Projected scale probe tracks must be canonical and unique"
            )
        previous = current
        bone_id = _identifier(track.get("bone_id"), "bone_id")
        if bone_id in seen_bones:
            raise ProjectedScaleProbeValidationError(
                "Projected scale probe bone bindings must be unique"
            )
        seen_bones.add(bone_id)
        setup_length = _positive(track.get("setup_length_px"), MAX_LENGTH_PX)
        setup_ratio = _positive(
            track.get("setup_foreshortening_ratio"), 1.001
        )
        samples = _array(track.get("samples"), "Projected scale probe samples")
        if not 2 <= len(samples) <= 4096 \
                or sample_count is not None and len(samples) != sample_count:
            raise ProjectedScaleProbeValidationError(
                "Projected scale probe sample count is inconsistent"
            )
        sample_count = len(samples)
        payloads = []
        for index, sample_raw in enumerate(samples):
            sample = _object(sample_raw, "Projected scale probe sample")
            _exact(sample, _SAMPLE, "Projected scale probe sample")
            payload = _sample(sample, index, setup_length, setup_ratio)
            payloads.append(payload)
            scales.append(payload[2])
            collapsed += payload[-1] == "collapsed"
        ticks = tuple(payload[1] for payload in payloads)
        if ticks[0] != 0 or any(
            right <= left for left, right in zip(ticks, ticks[1:])
        ) or frame_ticks is not None and ticks != frame_ticks:
            raise ProjectedScaleProbeValidationError(
                "Projected scale probe ticks must be shared and increasing"
            )
        frame_ticks = ticks
        if not _close(payloads[0][2], 1.0) \
                or not _close(payloads[0][3], setup_length) \
                or not _close(payloads[0][4], 0.0):
            raise ProjectedScaleProbeValidationError(
                "Projected scale probe frame zero is not its setup baseline"
            )
    return (len(rows), sample_count or 0), scales, collapsed


def _sample(sample, index: int, setup_length: float, setup_ratio: float):
    frame = sample.get("source_frame_index")
    tick = sample.get("tick")
    if frame != index or type(tick) is not int or tick < 0:
        raise ProjectedScaleProbeValidationError(
            "Projected scale probe sample identity is invalid"
        )
    ratio = _positive(sample.get("foreshortening_ratio"), 1.001)
    scale = _positive(sample.get("scale_x_candidate"), MAX_SCALE)
    length = _nonnegative(sample.get("candidate_length_px"), MAX_LENGTH_PX)
    delta = _number(sample.get("delta_length_px"), MAX_LENGTH_PX)
    state = sample.get("projection_state")
    if state != "observable" or not _close(scale, ratio / setup_ratio) \
            or not _close(length, setup_length * scale) \
            or not _close(delta, length - setup_length):
        raise ProjectedScaleProbeValidationError(
            "Projected scale probe sample math is inconsistent"
        )
    return frame, tick, scale, length, delta, state


def _summary(value, counts, scales, collapsed) -> None:
    summary = _object(value, "Projected scale probe summary")
    _exact(summary, _SUMMARY, "Projected scale probe summary")
    expected = {
        "status": "candidate_only",
        "track_count": counts[0],
        "sample_count": counts[0] * counts[1],
        "collapsed_sample_count": collapsed,
        "minimum_scale_x_candidate": min(scales),
        "maximum_scale_x_candidate": max(scales),
    }
    if summary != expected:
        raise ProjectedScaleProbeValidationError(
            "Projected scale probe summary differs from its tracks"
        )


def _cross_projected(root, source, verified) -> None:
    if type(verified) is not VerifiedProjectedMotionBundle:
        raise ProjectedScaleProbeValidationError(
            "Projected scale probe requires a verified P8 bundle"
        )
    projected = verified.projected_motion
    require_projected_motion_ir(projected)
    expected = {
        "projected_motion_sha256": verified.projected_motion_sha256,
        "projected_bundle_sha256": verified.bundle_sha256,
        "camera_sha256": verified.camera_sha256,
        "p7_motion_sha256": verified.p7_motion_sha256,
    }
    if any(source[field] != value for field, value in expected.items()) \
            or root["clip_id"] != projected["clip_id"]:
        raise ProjectedScaleProbeValidationError(
            "Projected scale probe P8 source binding differs"
        )
    by_role = {track["role"]: track for track in projected["segment_tracks"]}
    for track in root["tracks"]:
        upstream = by_role.get(track["role"])
        if upstream is None or len(track["samples"]) != len(upstream["samples"]):
            raise ProjectedScaleProbeValidationError(
                "Projected scale probe track differs from P8 evidence"
            )
        if track["setup_foreshortening_ratio"] != \
                upstream["samples"][0]["foreshortening_ratio"]:
            raise ProjectedScaleProbeValidationError(
                "Projected scale probe setup ratio differs from P8 evidence"
            )
        for sample, source_sample in zip(track["samples"], upstream["samples"]):
            fields = ("source_frame_index", "tick", "foreshortening_ratio",
                      "projection_state")
            if any(sample[field] != source_sample[field] for field in fields):
                raise ProjectedScaleProbeValidationError(
                    "Projected scale probe samples differ from P8 evidence"
                )


def _cross_target(root, source, target) -> None:
    require_motion_target_profile(target)
    target_sha = canonical_sha256(target)
    p3 = target["source"]["p3"]
    expected = {
        "target_profile_sha256": target_sha,
        "p3_rig_sha256": p3["rig_sha256"],
        "p3_bundle_sha256": p3["bundle_sha256"],
    }
    if root["project_id"] != target["project_id"] \
            or any(source[field] != value for field, value in expected.items()):
        raise ProjectedScaleProbeValidationError(
            "Projected scale probe target binding differs"
        )
    bones = {bone["role"]: bone for bone in target["bones"]}
    for track in root["tracks"]:
        bone = bones.get(track["role"])
        if bone is None or track["bone_id"] != bone["bone_id"] \
                or track["setup_length_px"] != \
                bone["setup_local"]["length_px"]:
            raise ProjectedScaleProbeValidationError(
                "Projected scale probe target bone differs"
            )


def _number(value: Any, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or abs(float(value)) > maximum:
        raise ProjectedScaleProbeValidationError(
            "Projected scale probe number is not finite and bounded"
        )
    return float(value)


def _positive(value: Any, maximum: float) -> float:
    result = _number(value, maximum)
    if result <= 0:
        raise ProjectedScaleProbeValidationError(
            "Projected scale probe number must be positive"
        )
    return result


def _nonnegative(value: Any, maximum: float) -> float:
    result = _number(value, maximum)
    if result < 0:
        raise ProjectedScaleProbeValidationError(
            "Projected scale probe number must be non-negative"
        )
    return result


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128 \
            or not value[0].isalnum() \
            or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for char in value):
        raise ProjectedScaleProbeValidationError(
            f"Projected scale probe {label} is invalid"
        )
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProjectedScaleProbeValidationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProjectedScaleProbeValidationError(f"{label} must be an array")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise ProjectedScaleProbeValidationError(
            f"{label} fields are incomplete or unsupported"
        )


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=TOLERANCE, abs_tol=TOLERANCE)
