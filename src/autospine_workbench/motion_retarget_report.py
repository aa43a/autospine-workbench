"""Deterministic kinematic evidence for one exact P5 retarget result."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
from typing import Any

from .ik_probe_math import quantize
from .motion_bundle_integrity import VerifiedMotionBundle
from .motion_instance_sampling import (
    SAMPLE_STEP_TICKS,
    instance_sample_ticks,
    sample_instance_deltas,
    sample_instance_pose,
)
from .motion_retarget_compiler import (
    RetargetedMotion,
    compile_motion_instance,
)
from .motion_retarget_kinematics import solve_motion_ik_track
from .motion_target_profile import MotionTargetProfile
from .motion_retarget_report_validation import (
    FORMAT,
    FORMAT_VERSION,
    MAX_SAMPLE_COUNT,
    SAMPLER_POLICY,
    TOLERANCE,
    require_motion_retarget_report_shape,
)
from .resolved_project import canonical_sha256


class MotionRetargetReportError(ValueError):
    """Raised when exact inputs fail their kinematic retarget evidence gate."""


@dataclass(frozen=True, slots=True)
class MotionRetargetReport:
    """Frozen canonical report with isolated JSON access."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.document)


def build_motion_retarget_report(
    verified_motion: VerifiedMotionBundle,
    target_profile: MotionTargetProfile,
    retargeted: RetargetedMotion,
) -> MotionRetargetReport:
    """Rebuild all inputs and issue report bytes only when every check passes."""

    try:
        motion, target, instance = _exact_inputs(
            verified_motion, target_profile, retargeted
        )
        report = _derive_report(
            verified_motion, target_profile, retargeted,
            motion, target, instance,
        )
        require_motion_retarget_report_shape(report)
        return MotionRetargetReport(_canonical(report))
    except MotionRetargetReportError:
        raise
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError) as exc:
        raise MotionRetargetReportError(
            f"Motion retarget report generation failed: {exc}"
        ) from exc


def require_motion_retarget_report(
    document: Mapping[str, Any],
    *,
    verified_motion: VerifiedMotionBundle,
    target_profile: MotionTargetProfile,
    retargeted: RetargetedMotion,
) -> None:
    """Validate shape, then reproduce the complete canonical report."""

    try:
        require_motion_retarget_report_shape(document)
        expected = build_motion_retarget_report(
            verified_motion, target_profile, retargeted
        )
        if _canonical(document) != expected._canonical_json:
            raise MotionRetargetReportError(
                "Motion retarget report differs from rebuilt evidence"
            )
    except MotionRetargetReportError:
        raise
    except (OverflowError, TypeError, ValueError) as exc:
        raise MotionRetargetReportError(
            f"Motion retarget report validation failed: {exc}"
        ) from exc


def _exact_inputs(verified, profile, retargeted):
    if type(retargeted) is not RetargetedMotion:
        raise MotionRetargetReportError(
            "Retarget evidence requires an exact RetargetedMotion"
        )
    rebuilt = compile_motion_instance(verified, profile)
    if rebuilt != retargeted:
        raise MotionRetargetReportError(
            "Retarget result differs from exact rebuilt inputs"
        )
    return verified.motion, profile.document, retargeted.instance


def _derive_report(verified, profile, retargeted, motion, target, instance):
    ticks = instance_sample_ticks(instance, target_profile=target)
    if not 1 <= len(ticks) <= MAX_SAMPLE_COUNT:
        raise MotionRetargetReportError("Retarget sample count is out of bounds")
    ik_sources = [
        track for track in motion["tracks"] if track["target_kind"] == "ik_handle"
    ]
    retained_ticks = {0, instance["timing"]["duration_ticks"]}
    retained_ticks.update(
        key["tick"] for track in ik_sources for key in track["keys"]
    )
    poses, max_rotation, max_translation = {}, 0.0, 0.0
    bone_ids = {row["bone_id"] for row in target["bones"]}
    for tick in ticks:
        _rotations, translation = sample_instance_deltas(
            instance, target_profile=target, tick=tick
        )
        pose = sample_instance_pose(instance, target_profile=target, tick=tick)
        _require_finite_pose(pose, bone_ids)
        if tick in retained_ticks:
            poses[tick] = pose
        world_rotations = (abs(row["rotation_deg"]) for row in pose.values())
        max_rotation = max(max_rotation, *world_rotations)
        max_translation = max(max_translation, math.hypot(*translation))
    loop = _loop_result(instance, poses)
    ik = _ik_result(motion, target, poses, ik_sources)
    contacts = _contact_result(motion, target, instance)
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "status": "passed",
        "source": {
            "motion_ir_sha256": verified.clip_sha256,
            "motion_bundle_sha256": verified.bundle_sha256,
            "motion_run_sha256": verified.run_sha256,
            "target_profile_sha256": profile.sha256,
            "instance_sha256": retargeted.instance_sha256,
            "retarget_run_identity_sha256": retargeted.run_identity_sha256,
            "retarget_run_document_sha256": retargeted.run_document_sha256,
        },
        "sampler": {
            "step_ticks": SAMPLE_STEP_TICKS,
            "policy": SAMPLER_POLICY,
            "sample_count": len(ticks),
        },
        "finite_pose": {
            "status": "passed",
            "bone_count": len(bone_ids),
            "world_bone_sample_count": len(bone_ids) * len(ticks),
            "max_abs_rotation_deg": quantize(max_rotation),
            "max_root_translation_px": quantize(max_translation),
        },
        "loop_closure": loop,
        "ik": ik,
        "contacts": contacts,
    }


def _require_finite_pose(pose, expected_ids):
    if not isinstance(pose, Mapping) or set(pose) != expected_ids:
        raise MotionRetargetReportError("Sampled world bone inventory differs")
    for bone_id, row in pose.items():
        if not isinstance(row, Mapping):
            raise MotionRetargetReportError("Sampled world bone is invalid")
        values = [row.get("rotation_deg")]
        for field in ("origin_xy", "endpoint_xy"):
            point = row.get(field)
            if not isinstance(point, list) or len(point) != 2:
                raise MotionRetargetReportError("Sampled world point is invalid")
            values.extend(point)
        if any(not _finite(value) for value in values):
            raise MotionRetargetReportError(
                f"Sampled world bone {bone_id} is non-finite"
            )


def _loop_result(instance, poses):
    if not instance["timing"]["loop"]:
        return {"result": "not_applicable", "tolerance": TOLERANCE}
    duration = instance["timing"]["duration_ticks"]
    error = _pose_error(poses[0], poses[duration])
    if error > TOLERANCE:
        raise MotionRetargetReportError("Loop world pose does not close")
    return {
        "result": "passed", "tolerance": TOLERANCE,
        "maximum_numeric_error": quantize(error),
    }


def _pose_error(left, right):
    values = []
    for bone_id in sorted(left):
        for field in ("origin_xy", "rotation_deg", "endpoint_xy"):
            a, b = left[bone_id][field], right[bone_id][field]
            if isinstance(a, list):
                values.extend(abs(x - y) for x, y in zip(a, b, strict=True))
            else:
                values.append(abs(a - b))
    return max(values, default=0.0)


def _ik_result(motion, target, poses, sources):
    tracks, total_keys, total_setup, maximum = [], 0, 0, 0.0
    for source in sources:
        solved = solve_motion_ik_track(motion, target, source["target"])
        if any(sample.reach_state != "reachable" for sample in solved.samples):
            raise MotionRetargetReportError("Retarget IK contains unreachable samples")
        errors = []
        for sample in solved.samples:
            endpoint = poses[sample.tick][solved.distal_bone_id]["endpoint_xy"]
            errors.append(math.hypot(
                endpoint[0] - sample.requested_target_xy[0],
                endpoint[1] - sample.requested_target_xy[1],
            ))
        error = max(errors, default=0.0)
        if not _finite(error) or error > TOLERANCE:
            raise MotionRetargetReportError("Retarget IK effector error exceeds tolerance")
        setup_count = sum(key["value"] == "setup" for key in source["keys"])
        total_keys += len(solved.samples)
        total_setup += setup_count
        maximum = max(maximum, error)
        tracks.append({
            "handle_id": solved.handle_id,
            "key_count": len(solved.samples),
            "setup_key_count": setup_count,
            "maximum_effector_error_px": quantize(error),
        })
    return {
        "status": "passed", "tolerance_px": TOLERANCE,
        "track_count": len(tracks), "key_count": total_keys,
        "setup_key_count": total_setup,
        "maximum_effector_error_px": quantize(maximum),
        "tracks": tracks,
    }


def _contact_result(motion, target, instance):
    handles = {item["id"]: item for item in target["ik_handles"]}
    expected = [{
        **marker,
        "proximal_bone_id": handles[marker["limb"]]["proximal_bone_id"],
        "distal_bone_id": handles[marker["limb"]]["distal_bone_id"],
    } for marker in motion["markers"]]
    if instance["markers"] != expected:
        raise MotionRetargetReportError("Contact marker projection differs")
    return {
        "status": "passed", "source_count": len(expected),
        "preserved_count": len(instance["markers"]),
    }


def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) \
        and math.isfinite(value)


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
