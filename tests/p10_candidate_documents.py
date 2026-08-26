"""Build minimal reviewed-motion documents for the persisted P10 fixture."""

from __future__ import annotations

from autospine_workbench.depth_order_candidates import (
    GENERATOR_ID,
    GENERATOR_VERSION,
)
from autospine_workbench.foot_lock_candidate_validation import foot_lock_policy
from autospine_workbench.ik_target_geometry import SOURCE_IDENTITY_FIELDS
from autospine_workbench.motion_instance_v2_compiler import (
    compile_motion_instance_v2,
)
from autospine_workbench.motion_policy_decision import (
    build_motion_policy_decision,
)
from autospine_workbench.reviewed_motion_bundle_upstream import (
    require_reviewed_motion_upstreams,
)
from autospine_workbench.reviewed_motion_policy import (
    compile_reviewed_motion_policy,
)
from tests.motion_policy_decision_helpers import approved_review


def build_reviewed_documents(mesh, retarget):
    """Return canonical foot/depth/decision/policy/v2 documents."""

    foot, depth = _candidate_documents(mesh, retarget)
    decision = build_motion_policy_decision(
        foot,
        depth,
        review=approved_review(),
        decisions=[],
        root_release_keys=[],
        draw_order_loop_reset={"mode": "explicit", "approved": False},
    ).document
    policy = compile_reviewed_motion_policy(
        decision, foot, depth, mesh
    ).document
    base, target = require_reviewed_motion_upstreams(mesh, retarget)
    v2 = compile_motion_instance_v2(base, target, policy).document
    return foot, depth, decision, policy, v2


def _candidate_documents(mesh, retarget):
    base, _target = require_reviewed_motion_upstreams(mesh, retarget)
    duration = base["timing"]["duration_ticks"]
    ticks = (0, duration)
    p3 = {field: getattr(mesh, field) for field in SOURCE_IDENTITY_FIELDS}
    p5 = {
        "target_profile_sha256": retarget.target_profile_sha256,
        "instance_sha256": retarget.instance_sha256,
        "run_sha256": retarget.run_document_sha256,
        "retarget_report_sha256": retarget.retarget_report_sha256,
        "mesh_regression_sha256": retarget.mesh_regression_sha256,
        "bundle_sha256": retarget.bundle_sha256,
    }
    p8 = _p8_source(base)
    foot = _foot(mesh.project_id, base["clip_id"], ticks, p3, p5, p8)
    depth = _depth(
        mesh.project_id, base["clip_id"], ticks, base, mesh, p3, p5, p8
    )
    return foot, depth


def _p8_source(base):
    source = base["source"]
    return {
        "projected_motion_sha256": "1" * 64,
        "bundle_sha256": "2" * 64,
        "camera_sha256": "3" * 64,
        "run_sha256": "4" * 64,
        "legacy_motion_sha256": source["motion_ir_sha256"],
        "p7_motion_sha256": source["motion_ir_sha256"],
        "p7_bundle_sha256": source["motion_bundle_sha256"],
        "p7_run_sha256": "5" * 64,
    }


def _foot(project, clip, ticks, p3, p5, p8):
    samples = [{
        "source_frame_index": index,
        "tick": tick,
        "support_state": "none",
        "state": "unconstrained",
        "active_contact_ids": [],
        "observations": [],
        "correction_candidate_px": None,
        "correction_magnitude_px": None,
        "correction_reference_ratio": None,
        "maximum_residual_px": None,
    } for index, tick in enumerate(ticks)]
    return {
        "format": "autospine-foot-lock-candidates",
        "format_version": 1,
        "project_id": project,
        "clip_id": clip,
        "source": {
            "projected_motion_sha256": p8["projected_motion_sha256"],
            "projected_bundle_sha256": p8["bundle_sha256"],
            "camera_sha256": p8["camera_sha256"],
            "p7_motion_sha256": p8["p7_motion_sha256"],
            "p7_bundle_sha256": p8["p7_bundle_sha256"],
            "p7_run_sha256": p8["p7_run_sha256"],
            "target_profile_sha256": p5["target_profile_sha256"],
            "motion_instance_sha256": p5["instance_sha256"],
            "retarget_bundle_sha256": p5["bundle_sha256"],
            "retarget_run_document_sha256": p5["run_sha256"],
            "p3_rig_sha256": p3["rig_sha256"],
            "p3_bundle_sha256": p3["bundle_sha256"],
            "instance_motion_ir_sha256": p8["p7_motion_sha256"],
            "instance_motion_bundle_sha256": p8["p7_bundle_sha256"],
        },
        "policy": foot_lock_policy(1.0, 1.0),
        "reference": {
            "kind": "target_profile.mean-leg-maximum-kinematic-reach",
            "value_px": 1.0,
            "unit": "pixel",
        },
        "contacts": [],
        "samples": samples,
        "summary": {
            "status": "candidate_only",
            "sample_count": 2,
            "contact_count": 0,
            "unconstrained_count": 2,
            "candidate_count": 0,
            "rejected_limit_count": 0,
            "rejected_conflict_count": 0,
            "maximum_correction_px": 0.0,
            "maximum_correction_reference_ratio": 0.0,
            "maximum_residual_px": 0.0,
        },
    }


def _depth(project, clip, ticks, base, mesh, p3, p5, p8):
    setup = [row["id"] for row in sorted(
        mesh.rig["slots"], key=lambda row: row["setup_draw_order"]
    )]
    slot_ids = sorted(setup[:2])
    front = max(slot_ids, key=setup.index)
    slots = [
        {"slot_id": slot_id, "depth_role": f"role.{index}"}
        for index, slot_id in enumerate(slot_ids)
    ]
    samples = [_depth_sample(index, tick, slots, front)
               for index, tick in enumerate(ticks)]
    return {
        "format": "autospine-depth-order-candidates",
        "format_version": 1,
        "project_id": project,
        "clip_id": clip,
        "source": {
            "p8": p8,
            "p5": p5,
            "p3": p3,
            "depth_pair_policy_sha256": "6" * 64,
        },
        "timing": {**base["timing"], "frame_count": 2},
        "projection": {
            "camera_depth_positive": "away_from_camera",
            "front_score_sign": -1,
        },
        "generator": {
            "id": GENERATOR_ID,
            "version": GENERATOR_VERSION,
            "numeric_precision_decimals": 9,
        },
        "semantics": _depth_semantics(),
        "hysteresis": {
            "unit": "root_reference_normalized_depth",
            "enter_threshold": 0.05,
            "exit_threshold": 0.02,
            "minimum_hold_frames": 2,
        },
        "summary": {
            "status": "candidate_only",
            "pair_count": 1,
            "sample_count": 2,
            "event_count": 0,
            "collapsed_sample_count": 0,
        },
        "pairs": [{
            "pair_id": "setup-pair",
            "slots": slots,
            "setup_front_slot": front,
            "samples": samples,
            "events": [],
        }],
    }


def _depth_semantics():
    return {
        "mode": "candidate_only",
        "apply_policy": "review_required",
        "decision_emitted": False,
        "proxy_quality": "bone-segment-midpoint",
        "raster_truth_claimed": False,
        "runtime_timeline_emitted": False,
        "motion_instance_mutated": False,
        "spine_draw_order_emitted": False,
        "evidence_window": "inclusive_source_frame_range",
    }


def _depth_sample(index, tick, slots, front):
    return {
        "source_frame_index": index,
        "tick": tick,
        "scores": [{
            "slot_id": row["slot_id"],
            "depth_role": row["depth_role"],
            "midpoint_depth_root_relative_normalized": 0.0,
            "front_score": 0.0,
        } for row in slots],
        "score_delta_first_minus_second": 0.0,
        "current_front_slot": front,
        "pending_front_slot": None,
        "pending_frame_count": 0,
        "state": "hold",
    }
