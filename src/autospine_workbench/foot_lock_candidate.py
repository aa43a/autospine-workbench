"""Compile review-only target root corrections from exact leg contacts."""

from __future__ import annotations

import json
import math

from .foot_lock_candidate_inputs import (
    FootLockCandidateInputError,
    require_foot_lock_candidate_inputs,
)
from .foot_lock_candidate_report import FootLockCandidateReport
from .foot_lock_candidate_validation import (
    FORMAT,
    FORMAT_VERSION,
    FootLockCandidateValidationError,
    foot_lock_policy,
    require_foot_lock_candidates,
)
from .motion_instance_sampling import (
    MotionInstanceSamplingError,
    sample_instance_pose,
)
from .motion_retarget_bundle_integrity import VerifiedMotionRetargetBundle
from .projected_motion_bundle_integrity import VerifiedProjectedMotionBundle
from .resolved_project import canonical_sha256


DECIMALS = 9


class FootLockCandidateError(ValueError):
    """Raised when target-specific foot-lock evidence cannot be compiled."""


def compile_foot_lock_candidates(
    projected_bundle: VerifiedProjectedMotionBundle,
    retarget_bundle: VerifiedMotionRetargetBundle,
    *,
    max_correction_reference_ratio: float,
    max_residual_px: float,
) -> FootLockCandidateReport:
    """Solve raw frame candidates without mutating P5 or emitting timelines."""

    try:
        correction_limit = _positive(
            max_correction_reference_ratio, "correction/reference limit"
        )
        residual_limit = _nonnegative(max_residual_px, "residual limit")
        inputs = require_foot_lock_candidate_inputs(
            projected_bundle, retarget_bundle
        )
        contacts = _contact_rows(inputs)
        samples = _sample_rows(inputs, contacts, correction_limit, residual_limit)
        document = _document(
            projected_bundle, retarget_bundle, inputs, contacts, samples,
            correction_limit, residual_limit,
        )
        require_foot_lock_candidates(
            document,
            projected_bundle=projected_bundle,
            retarget_bundle=retarget_bundle,
        )
        canonical = json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
        report = FootLockCandidateReport(canonical)
        if report.sha256 != canonical_sha256(report.document):
            raise FootLockCandidateError(
                "Foot-lock candidate identity is inconsistent"
            )
        return report
    except FootLockCandidateError:
        raise
    except (
        FootLockCandidateInputError,
        FootLockCandidateValidationError,
        MotionInstanceSamplingError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise FootLockCandidateError(
            f"Foot-lock candidate compilation failed: {exc}"
        ) from exc


def _contact_rows(inputs) -> list[dict[str, Any]]:
    frame_by_tick = {
        frame["tick"]: frame["source_frame_index"]
        for frame in inputs.projected["frames"]
    }
    rows = []
    for index, marker in enumerate(inputs.contacts):
        tick = marker["start_tick"]
        endpoint = _endpoint(inputs, marker["distal_bone_id"], tick)
        rows.append({
            "contact_id": f"contact-{index:03d}",
            "limb": marker["limb"],
            "proximal_bone_id": marker["proximal_bone_id"],
            "distal_bone_id": marker["distal_bone_id"],
            "start_tick": tick,
            "end_tick": marker["end_tick"],
            "anchor_source_frame_index": frame_by_tick[tick],
            "anchor_endpoint_px": endpoint,
        })
    return rows


def _sample_rows(inputs, contacts, correction_limit, residual_limit):
    rows = []
    for frame in inputs.projected["frames"]:
        tick = frame["tick"]
        active = [
            row for row in contacts
            if row["start_tick"] <= tick < row["end_tick"]
        ]
        if not active:
            rows.append(_unconstrained(frame))
            continue
        observations = []
        desired = []
        for contact in active:
            endpoint = _endpoint(inputs, contact["distal_bone_id"], tick)
            delta = _sub(contact["anchor_endpoint_px"], endpoint)
            desired.append(delta)
            observations.append({
                "contact_id": contact["contact_id"],
                "limb": contact["limb"],
                "current_endpoint_px": endpoint,
                "desired_correction_px": delta,
            })
        correction = _mean(desired)
        correction_magnitude = _magnitude(correction)
        correction_ratio = _q(
            correction_magnitude / inputs.reference_length_px
        )
        residual_max = 0.0
        completed = []
        for observation, wanted in zip(observations, desired):
            residual = _sub(correction, wanted)
            magnitude = _magnitude(residual)
            residual_max = max(residual_max, magnitude)
            completed.append({
                **observation,
                "residual_after_candidate_px": residual,
                "residual_magnitude_px": magnitude,
                "residual_reference_ratio": _q(
                    magnitude / inputs.reference_length_px
                ),
            })
        state = "candidate"
        if residual_max > residual_limit:
            state = "rejected_conflict"
        elif correction_ratio > correction_limit:
            state = "rejected_limit"
        rows.append({
            "source_frame_index": frame["source_frame_index"],
            "tick": tick,
            "support_state": (
                "single_support" if len(active) == 1 else "dual_support"
            ),
            "state": state,
            "active_contact_ids": [row["contact_id"] for row in active],
            "observations": completed,
            "correction_candidate_px": correction,
            "correction_magnitude_px": correction_magnitude,
            "correction_reference_ratio": correction_ratio,
            "maximum_residual_px": _q(residual_max),
        })
    return rows


def _unconstrained(frame) -> dict[str, Any]:
    return {
        "source_frame_index": frame["source_frame_index"],
        "tick": frame["tick"],
        "support_state": "none",
        "state": "unconstrained",
        "active_contact_ids": [],
        "observations": [],
        "correction_candidate_px": None,
        "correction_magnitude_px": None,
        "correction_reference_ratio": None,
        "maximum_residual_px": None,
    }


def _document(p8, p5, inputs, contacts, samples, correction_limit, residual_limit):
    source = inputs.instance["source"]
    p3 = inputs.target["source"]["p3"]
    states = [row["state"] for row in samples]
    constrained = [row for row in samples if row["state"] != "unconstrained"]
    summary_status = "candidate_only"
    if "rejected_conflict" in states:
        summary_status = "rejected_conflict"
    elif "rejected_limit" in states:
        summary_status = "rejected_limit"
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "project_id": p5.project_id,
        "clip_id": p8.clip_id,
        "source": {
            "projected_motion_sha256": p8.projected_motion_sha256,
            "projected_bundle_sha256": p8.bundle_sha256,
            "camera_sha256": p8.camera_sha256,
            "p7_motion_sha256": p8.p7_motion_sha256,
            "p7_bundle_sha256": p8.p7_bundle_sha256,
            "p7_run_sha256": p8.p7_run_sha256,
            "target_profile_sha256": p5.target_profile_sha256,
            "motion_instance_sha256": p5.instance_sha256,
            "retarget_bundle_sha256": p5.bundle_sha256,
            "retarget_run_document_sha256": p5.run_document_sha256,
            "p3_rig_sha256": p3["rig_sha256"],
            "p3_bundle_sha256": p3["bundle_sha256"],
            "instance_motion_ir_sha256": source["motion_ir_sha256"],
            "instance_motion_bundle_sha256": source["motion_bundle_sha256"],
        },
        "policy": foot_lock_policy(correction_limit, residual_limit),
        "reference": {
            "kind": "target_profile.mean-leg-maximum-kinematic-reach",
            "value_px": inputs.reference_length_px,
            "unit": "pixel",
        },
        "contacts": contacts,
        "samples": samples,
        "summary": {
            "status": summary_status,
            "sample_count": len(samples),
            "contact_count": len(contacts),
            "unconstrained_count": states.count("unconstrained"),
            "candidate_count": states.count("candidate"),
            "rejected_limit_count": states.count("rejected_limit"),
            "rejected_conflict_count": states.count("rejected_conflict"),
            "maximum_correction_px": max(
                (row["correction_magnitude_px"] for row in constrained),
                default=0.0,
            ),
            "maximum_correction_reference_ratio": max(
                (row["correction_reference_ratio"] for row in constrained),
                default=0.0,
            ),
            "maximum_residual_px": max(
                (row["maximum_residual_px"] for row in constrained),
                default=0.0,
            ),
        },
    }


def _endpoint(inputs, bone_id: str, tick: int) -> list[float]:
    pose = sample_instance_pose(
        inputs.instance, target_profile=inputs.target, tick=tick
    )
    return [_q(value) for value in pose[bone_id]["endpoint_xy"]]


def _sub(left, right) -> list[float]:
    return [_q(float(left[index]) - float(right[index])) for index in range(2)]


def _mean(values) -> list[float]:
    return [_q(sum(row[index] for row in values) / len(values)) for index in range(2)]


def _magnitude(value) -> float:
    return _q(math.hypot(float(value[0]), float(value[1])))


def _positive(value, label: str) -> float:
    result = _nonnegative(value, label)
    if result <= 0:
        raise FootLockCandidateError(f"{label} must be positive")
    return result


def _nonnegative(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or not 0 <= float(value) <= 1e12:
        raise FootLockCandidateError(f"{label} must be finite and bounded")
    return _q(float(value))


def _q(value: float) -> float:
    if not math.isfinite(value):
        raise FootLockCandidateError("Foot-lock candidate produced a non-finite number")
    result = round(float(value), DECIMALS)
    return 0.0 if result == 0 else result
