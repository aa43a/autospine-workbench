"""Cross-chain and head-identity checks for P10.6a v2 source admission."""

from __future__ import annotations

from .body_sway_dynamic_seam_evidence_profile_v2 import CERTIFIED_STATUS
from .motion_instance_v2_validation import motion_instance_v2_sha256
from .resolved_project import canonical_sha256
from .seam_anchor_review_json import canonical_json_bytes


class BodySwayMotionConsumerSourceChecksV2Error(ValueError):
    """Raised when certified evidence or exact cross-binding differs."""


def require_body_sway_motion_consumer_v2_certified(probe):
    claims = probe["claims"]
    proof = probe["source"]["body_sway_continuous_preview_proof_v2"]
    if probe["status"] != CERTIFIED_STATUS \
            or claims.get(
                "continuous_preview_v2_anchor_residual_within_engineering_"
                "tolerance"
            ) is not True \
            or claims.get(
                "structural_gap_proxy_within_engineering_tolerance"
            ) is not True \
            or proof["status"] \
                != "continuous_preview_model_structural_certified" \
            or proof["claims"].get(
                "continuous_preview_model_structural_safety"
            ) is not True:
        raise BodySwayMotionConsumerSourceChecksV2Error(
            "P10.5d v2 structural proxy evidence is not certified"
        )


def require_body_sway_motion_consumer_v2_cross_chain(
    source, probe, proof, candidate, report, motion, projection,
    bundle_motion, bundle,
):
    project, clip = source["project_id"], source["clip_id"]
    p3, p5, p9 = (
        report["source"]["p3"], report["source"]["p5"],
        report["source"]["p9"],
    )
    if any(value != project for value in (
        probe["project_id"], proof["project_id"], bundle.project_id,
        projection["project_id"],
    )) or any(value != clip for value in (
        probe["clip_id"], proof["clip_id"], bundle.clip_id,
        projection["clip_id"], motion["clip_id"],
    )):
        raise BodySwayMotionConsumerSourceChecksV2Error(
            "Motion consumer v2 project or clip identities are cross-wired"
        )
    continuous = proof["source"]
    if canonical_json_bytes(motion) != canonical_json_bytes(bundle_motion) \
            or motion_instance_v2_sha256(motion) \
                != p9["motion_instance_v2_sha256"] \
            or continuous["motion_instance_v2_sha256"] \
                != p9["motion_instance_v2_sha256"]:
        raise BodySwayMotionConsumerSourceChecksV2Error(
            "Embedded MotionInstance v2 differs from exact P9 bytes"
        )
    if motion["timing"] != projection["timing"] \
            or candidate["timing"] != projection["timing"] \
            or source["layer_manifest_sha256"] != p3["layer_manifest_sha256"] \
            or source["p3_rig_sha256"] != p3["rig_sha256"] \
            or source["p3_bundle_sha256"] != p3["bundle_sha256"]:
        raise BodySwayMotionConsumerSourceChecksV2Error(
            "Motion consumer v2 timing, Manifest, or P3 is cross-wired"
        )
    if continuous["rig_ir_sha256"] != p3["rig_sha256"] \
            or continuous["target_profile_sha256"] \
                != p5["target_profile_sha256"] \
            or motion["source"]["p3_rig_sha256"] != p3["rig_sha256"] \
            or motion["source"]["p3_bundle_sha256"] != p3["bundle_sha256"] \
            or motion["source"]["target_profile_sha256"] \
                != p5["target_profile_sha256"] \
            or projection["source"]["base_motion_instance_v2_sha256"] \
                != p9["motion_instance_v2_sha256"]:
        raise BodySwayMotionConsumerSourceChecksV2Error(
            "Motion consumer v2 Rig, target, or projection is cross-wired"
        )


def expected_body_sway_motion_consumer_v2_head_observation(source):
    proof = source["body_sway_continuous_preview_proof_v2"]
    amplitude_source = proof["source"]["amplitude_envelope_candidate_v2"] \
        ["source"]
    admission = amplitude_source["review_admission_v2"]
    visual = admission["source"]["visual_review"]
    seam = source["reviewed_seam_anchor_set_v1"]["source"]
    identity = {
        "source_set_sha256": source["source_set_sha256"],
        "project_id": source["project_id"],
        "visual_review_v2": {
            "admission_sha256": amplitude_source[
                "review_admission_v2_sha256"
            ],
            "candidate_sha256": visual["candidate_v2_sha256"],
            "revision": visual["revision"],
            "decision_sha256": visual["decision_v2_sha256"],
        },
        "seam_anchor_review_v1": {
            "candidate_sha256": seam["seam_anchor_candidate_sha256"],
            "revision": seam["review_revision"],
            "decision_sha256": seam["seam_anchor_review_decision_sha256"],
            "reviewed_set_sha256": source[
                "reviewed_seam_anchor_set_v1_sha256"
            ],
        },
    }
    identity_sha = canonical_sha256(identity)
    return {
        "method": "visual-v2-recompile-plus-seam-v1-history-replay",
        "scope": "compile_time", "identity_sha256": identity_sha,
        "identity": identity,
        "checks": {
            "visual_review_v2_head": "observed_current",
            "seam_anchor_review_v1_head": "observed_current",
            "reviewed_seam_anchor_set_v1": "canonical_replay_matched",
        },
        "permanent_authority_claimed": False,
    }


__all__ = [
    "BodySwayMotionConsumerSourceChecksV2Error",
    "expected_body_sway_motion_consumer_v2_head_observation",
    "require_body_sway_motion_consumer_v2_certified",
    "require_body_sway_motion_consumer_v2_cross_chain",
]
