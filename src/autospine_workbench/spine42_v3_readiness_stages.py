"""Per-sample exact replay stages for the P10.7b readiness audit."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .motion_instance_v3_bundle_reader import VerifiedMotionInstanceV3BundleReader
from .reviewed_motion_bundle_reader import VerifiedReviewedMotionBundleReader
from .reviewed_seam_anchor_set_bundle_reader import (
    VerifiedReviewedSeamAnchorSetBundleReader,
)
from .seam_anchor_review_address import ExactSeamAnchorReviewAddress
from .seam_anchor_review_candidate_binding import (
    load_bound_seam_anchor_review_candidate,
)
from .spine42_v3_bundle_reader import VerifiedSpine42V3BundleReader
from .spine42_v3_readiness_runtime import audit_runtime_and_raster


CHECKPOINT_IDS = (
    "p3_seam_source", "p9_reviewed_motion",
    "p10_5_reviewed_seam_anchor_set", "p10_6b_motion_instance_v3",
    "p10_7a_spine42_v3", "p10_7b_runtime_capture",
    "p10_7b_raster_review", "p6_setup_regression",
)
_FAILURES = (KeyError, OSError, RuntimeError, TypeError, ValueError)


def audit_spine42_v3_sample(
    sample: Mapping[str, Any], state_root: Path,
) -> dict[str, Any]:
    """Audit one strict request row, preserving checkpoint order."""

    context: dict[str, Any] = {}
    checkpoints = [
        _p3_seam(sample, state_root, context),
        _p9(sample, state_root, context),
        _seam_set(sample, state_root, context),
        _motion_v3(sample, state_root, context),
        _spine(sample, state_root, context),
        *audit_runtime_and_raster(sample, state_root, context),
        _checkpoint(
            "p6_setup_regression", "prerequisite_missing",
            ("p6_setup_golden_comparison_not_declared",),
            "compare_setup_case_with_p6_approved_golden",
        ),
    ]
    if tuple(row["checkpoint_id"] for row in checkpoints) != CHECKPOINT_IDS:
        raise RuntimeError("Readiness checkpoint order changed")
    ready = all(row["status"] == "verified" for row in checkpoints[:-1])
    actions = sorted({
        row["next_action_code"] for row in checkpoints
        if row["next_action_code"] is not None
    })
    return {
        "project_id": sample["project_id"],
        "checkpoints": checkpoints,
        "next_action_codes": actions,
        "status": "ready_for_p6_setup_comparison" if ready else "blocked",
    }


def _p3_seam(sample, root, context):
    try:
        address = ExactSeamAnchorReviewAddress(
            sample["project_id"], sample["layer_manifest_sha256"],
            sample["p3_rig_sha256"], sample["p3_bundle_sha256"],
        )
        bound = load_bound_seam_anchor_review_candidate(root, address)
        candidate = bound.candidates
        summary = candidate.document["summary"]
        context["seam_candidate"] = candidate
        return _checkpoint("p3_seam_source", "verified", (), None, {
            "candidate_sha256": candidate.sha256,
            "relationship_count": summary["relationship_count"],
            "review_required_count": summary["review_required_count"],
            "unobservable_count": summary["unobservable_count"],
        })
    except _FAILURES:
        return _mismatch(
            "p3_seam_source", "exact_p3_or_manifest_replay_failed",
            "repair_exact_p3_source_address",
        )


def _p9(sample, root, context):
    address = sample["reviewed_motion_address"]
    if address is None:
        return _missing(
            "p9_reviewed_motion", "exact_reviewed_motion_address_not_declared",
            "provide_exact_reviewed_motion_after_real_kimodo_p7_p8_p9_review",
        )
    try:
        value = VerifiedReviewedMotionBundleReader(root).load(
            sample["project_id"], address["motion_instance_v2_sha256"],
            address["bundle_sha256"],
        )
        p3 = value.document("run-manifest.json")["inputs"]["p3"]
        if p3 != {"rig_sha256": sample["p3_rig_sha256"],
                  "bundle_sha256": sample["p3_bundle_sha256"]}:
            raise ValueError("P9/P3 cross-wire")
        context["p9"] = value
        return _checkpoint("p9_reviewed_motion", "verified", (), None, {
            "clip_id": value.clip_id,
            "motion_instance_v2_sha256": value.motion_instance_v2_sha256,
            "bundle_sha256": value.bundle_sha256,
        })
    except _FAILURES:
        return _mismatch("p9_reviewed_motion", "exact_reviewed_motion_replay_failed")


def _seam_set(sample, root, context):
    candidate = context.get("seam_candidate")
    if candidate is None:
        return _missing(
            "p10_5_reviewed_seam_anchor_set", "p3_seam_source_not_verified",
            "repair_exact_p3_source_address",
        )
    address = sample["reviewed_seam_anchor_set_address"]
    if address is None:
        return _pending_seam(candidate)
    try:
        value = VerifiedReviewedSeamAnchorSetBundleReader(root).load(
            sample["project_id"],
            address["reviewed_seam_anchor_set_sha256"],
            address["bundle_sha256"],
        )
        source = value.candidates["source"]
        expected = {
            "layer_manifest_sha256": sample["layer_manifest_sha256"],
            "rig_sha256": sample["p3_rig_sha256"],
            "bundle_sha256": sample["p3_bundle_sha256"],
        }
        if any(source.get(key) != expected_value
               for key, expected_value in expected.items()) \
                or value.candidate_sha256 != candidate.sha256:
            raise ValueError("Seam/P3 cross-wire")
        context["seam"] = value
        return _checkpoint(
            "p10_5_reviewed_seam_anchor_set", "verified", (), None,
            {"candidate_sha256": value.candidate_sha256,
             "decision_sha256": value.decision_sha256,
             "review_revision": value.review_revision,
             "reviewed_seam_anchor_set_sha256": value.set_sha256,
             "bundle_sha256": value.bundle_sha256},
        )
    except _FAILURES:
        return _mismatch(
            "p10_5_reviewed_seam_anchor_set",
            "exact_reviewed_seam_anchor_set_replay_failed",
        )


def _pending_seam(candidate):
    count = candidate.document["summary"]["unobservable_count"]
    evidence = {
        "candidate_sha256": candidate.sha256,
        "unobservable_count": count,
    }
    if count:
        return _checkpoint(
            "p10_5_reviewed_seam_anchor_set", "review_blocked",
            ("seam_relationships_unobservable",),
            "repair_layer_semantics_or_define_explicit_partial_seam_contract",
            evidence,
        )
    return _checkpoint(
        "p10_5_reviewed_seam_anchor_set",
        "prerequisite_missing",
        ("reviewed_seam_anchor_set_address_not_declared",),
        "complete_review_and_declare_reviewed_seam_anchor_set",
        evidence,
    )


def _motion_v3(sample, root, context):
    address = sample["motion_instance_v3_address"]
    if address is None:
        return _missing(
            "p10_6b_motion_instance_v3", "motion_instance_v3_address_not_declared",
            "complete_p10_0_through_p10_6_and_declare_motion_instance_v3",
        )
    if "p9" not in context or "seam" not in context:
        return _missing(
            "p10_6b_motion_instance_v3", "motion_instance_v3_upstream_not_verified",
            "verify_p9_and_reviewed_seam_anchor_set",
        )
    try:
        value = VerifiedMotionInstanceV3BundleReader(root).load(
            sample["project_id"], address["motion_instance_v3_sha256"],
            address["bundle_sha256"], reviewed_bundle=context["p9"],
        )
        source = value.document(
            "body-sway-motion-consumer-admission.json"
        )["source"]
        seam = context["seam"]
        if (source["reviewed_seam_anchor_set_sha256"],
            source["reviewed_seam_anchor_set_bundle_sha256"]) != (
                seam.set_sha256, seam.bundle_sha256):
            raise ValueError("MotionInstance v3/seam cross-wire")
        context["motion_v3"] = value
        return _checkpoint(
            "p10_6b_motion_instance_v3", "verified", (), None,
            {"clip_id": value.clip_id,
             "motion_instance_v3_sha256": value.motion_instance_v3_sha256,
             "bundle_sha256": value.bundle_sha256},
        )
    except _FAILURES:
        return _mismatch(
            "p10_6b_motion_instance_v3", "exact_motion_instance_v3_replay_failed"
        )


def _spine(sample, root, context):
    address = sample["spine42_v3_address"]
    if address is None:
        return _missing(
            "p10_7a_spine42_v3", "spine42_v3_address_not_declared",
            "compile_and_declare_spine42_v3_bundle",
        )
    if "motion_v3" not in context:
        return _missing(
            "p10_7a_spine42_v3", "motion_instance_v3_not_verified",
            "verify_motion_instance_v3",
        )
    try:
        value = VerifiedSpine42V3BundleReader(root).load(
            sample["project_id"], address["skeleton_json_sha256"],
            address["bundle_sha256"],
        )
        motion = context["motion_v3"]
        if value.p3_source != {
            "rig_sha256": sample["p3_rig_sha256"],
            "bundle_sha256": sample["p3_bundle_sha256"],
        } or (value.motion_instance_v3_sha256,
              value.motion_instance_v3_bundle_sha256) != (
                  motion.motion_instance_v3_sha256, motion.bundle_sha256):
            raise ValueError("Spine v3 source cross-wire")
        context["spine"] = value
        return _checkpoint(
            "p10_7a_spine42_v3", "verified", (), None,
            {"clip_id": value.clip_id,
             "skeleton_json_sha256": value.skeleton_json_sha256,
             "bundle_sha256": value.bundle_sha256},
        )
    except _FAILURES:
        return _mismatch("p10_7a_spine42_v3", "exact_spine42_v3_replay_failed")


def _checkpoint(identifier, status, reasons, action, evidence=None):
    return {
        "checkpoint_id": identifier,
        "status": status,
        "reason_codes": list(reasons),
        "next_action_code": action,
        "evidence": evidence or {},
    }


def _missing(identifier, reason, action):
    return _checkpoint(
        identifier, "prerequisite_missing", (reason,), action
    )


def _mismatch(identifier, reason, action=None):
    return _checkpoint(
        identifier, "source_mismatch", (reason,),
        action or f"repair_{identifier}_exact_address",
    )


__all__ = ["audit_spine42_v3_sample"]
