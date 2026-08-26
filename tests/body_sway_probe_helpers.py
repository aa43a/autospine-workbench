"""Compact canonical fixtures for BodySwayProbeReport v1 tests."""

from __future__ import annotations

from copy import deepcopy

from autospine_workbench.body_sway_probe_profile import body_sway_probe_profile
from autospine_workbench.body_sway_probe_sample_validation import (
    representative_sample_sha256,
)
from autospine_workbench.body_sway_probe_validation import SEMANTICS
from tests.idle_behavior_decision_helpers import adjust_decision
from tests.test_idle_behavior_candidate_validation import valid_candidates


SHA = "a" * 64
BONES = ["pelvis-spine", "spine-chest", "chest-neck", "neck-head"]
RIG_BONES = [
    "arm.left", "chest-neck", "neck-head", "pelvis-spine", "root-pelvis",
    "spine-chest",
]
ROTATION_BONES = [
    "arm.left", "chest-neck", "neck-head", "pelvis-spine", "spine-chest",
]
BASE_ROTATIONS = {
    "arm.left": 5.0, "chest-neck": -1.0, "neck-head": 2.0,
    "pelvis-spine": 1.0, "spine-chest": 0.5,
}


def source():
    return {
        "idle_behavior_candidates_sha256": SHA,
        "idle_behavior_decision_sha256": SHA,
        "layer_manifest_sha256": SHA,
        "p3": {field: SHA for field in (
            "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
            "resolved_project_sha256", "rig_sha256", "run_sha256",
            "probes_sha256", "visuals_sha256", "bundle_sha256",
        )},
        "p5": {field: SHA for field in (
            "target_profile_sha256", "instance_sha256", "run_sha256",
            "retarget_report_sha256", "mesh_regression_sha256", "bundle_sha256",
        )},
        "p9": {field: SHA for field in (
            "foot_lock_candidates_sha256", "depth_order_candidates_sha256",
            "motion_policy_decision_sha256", "reviewed_motion_policy_sha256",
            "motion_instance_v2_sha256", "run_sha256", "bundle_sha256",
        )},
    }


def check(check_id, *, status="passed", subjects=1, samples=65, failures=0):
    return {
        "check_id": check_id,
        "status": status,
        "reason_code": f"sampled_check_{status}",
        "subject_count": subjects,
        "sample_count": samples,
        "failure_count": failures,
        "evidence_sha256": "b" * 64,
    }


def unavailable_check(check_id, reason, *, status="unobservable"):
    return {
        "check_id": check_id,
        "status": status,
        "reason_code": reason,
        "subject_count": 0,
        "sample_count": 0,
        "failure_count": 0,
        "evidence_sha256": None,
    }


def valid_report(*, with_mesh=True):
    candidates = valid_candidates()
    decision = adjust_decision(candidates)
    attachments = [{"attachment_id": "body", "type": "region"}]
    if with_mesh:
        attachments.append({"attachment_id": "leg", "type": "mesh"})
    checks = [
        check("loop_closure", subjects=1, samples=2),
        check("fk_finite", subjects=len(RIG_BONES)),
        check("sampled_mesh_deformation") if with_mesh else unavailable_check(
            "sampled_mesh_deformation", "reviewed_noop", status="not_applicable"
        ),
        check("sampled_canvas_containment", subjects=len(attachments)),
        check("shared_index_internal_continuity") if with_mesh else unavailable_check(
            "shared_index_internal_continuity", "reviewed_noop",
            status="not_applicable",
        ),
        unavailable_check(
            "inter_attachment_seams", "reviewed_seam_anchors_missing",
        ),
        unavailable_check(
            "visual_quality", "manual_runtime_preview_required",
        ),
    ]
    passed = 5 if with_mesh else 3
    not_applicable = 0 if with_mesh else 2
    return {
        "format": "autospine-body-sway-probe-report",
        "format_version": 1,
        "project_id": candidates["project_id"],
        "clip_id": candidates["clip_id"],
        "source": source(),
        "timing": {
            "ticks_per_second": 1_000_000,
            "duration_ticks": 1_000_000,
            "loop": True,
        },
        "selection": {
            "candidate_id": decision["candidate_id"],
            "feature_id": "body_sway",
            "action": "adjust",
            "probe_status": "pending_probe",
            "parameters": deepcopy(decision["payload"]),
        },
        "prober": body_sway_probe_profile(),
        "semantics": deepcopy(SEMANTICS),
        "schedule": {
            "tick_schedule_sha256": "c" * 64,
            "sample_count": 65,
            "first_tick": 0,
            "last_tick": 1_000_000,
        },
        "sample_stream": {
            "sample_stream_sha256": "d" * 64,
            "rig_bone_ids": list(RIG_BONES),
            "rotation_bone_ids": list(ROTATION_BONES),
            "overlay_bone_ids": list(BONES),
            "attachments": attachments,
            "representative_samples": [
                sample(0, [0.0, 2.0, 0.0, -0.5]),
                sample(250_000, [0.0, -2.0, 0.0, 0.5]),
                sample(1_000_000, [0.0, 2.0, 0.0, -0.5]),
            ],
        },
        "checks": checks,
        "status": "manual_visual_required",
        "release_gate": {
            "status": "blocked",
            "reason_codes": [
                "manual_runtime_preview_required",
                "reviewed_seam_anchors_missing",
                "safe_range_unproven",
            ],
        },
        "summary": {
            "schedule_sample_count": 65,
            "representative_sample_count": 3,
            "rig_bone_count": len(RIG_BONES),
            "rotation_bone_count": len(ROTATION_BONES),
            "overlay_bone_count": len(BONES),
            "attachment_count": len(attachments),
            "mesh_attachment_count": int(with_mesh),
            "check_count": 7,
            "passed_check_count": passed,
            "rejected_check_count": 0,
            "unobservable_check_count": 2,
            "not_applicable_check_count": not_applicable,
        },
    }


def sample(tick, values):
    overlay_by_bone = dict(zip(BONES, values, strict=True))
    base = [
        {"bone_id": bone_id, "value": BASE_ROTATIONS[bone_id]}
        for bone_id in ROTATION_BONES
    ]
    overlay = [
        {"bone_id": bone_id, "value": overlay_by_bone.get(bone_id, 0.0)}
        for bone_id in ROTATION_BONES
    ]
    combined = [
        {
            "bone_id": bone_id,
            "value": round(
                BASE_ROTATIONS[bone_id] + overlay_by_bone.get(bone_id, 0.0),
                9,
            ),
        }
        for bone_id in ROTATION_BONES
    ]
    row = {
        "tick": tick,
        "base_rotation_deg": base,
        "overlay_rotation_deg": overlay,
        "combined_rotation_deg": combined,
        "root_translation_xy": [3.0, -2.0],
    }
    row["sample_sha256"] = representative_sample_sha256(row)
    return row


def reject_check(document, index):
    row = document["checks"][index]
    row.update({
        "status": "rejected",
        "reason_code": "sampled_check_rejected",
        "failure_count": 1,
    })
    document["status"] = "structural_rejected"
    document["release_gate"]["reason_codes"].append(
        "sampled_structural_check_rejected"
    )
    document["release_gate"]["reason_codes"].sort()
    document["summary"]["passed_check_count"] -= 1
    document["summary"]["rejected_check_count"] += 1
