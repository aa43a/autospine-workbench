"""Exact P9 plus compact certified P10.5d shells for P10.6a tests."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from autospine_workbench.body_sway_dynamic_seam_head_checks import (
    BodySwayDynamicSeamHeadIdentity,
    BodySwayDynamicSeamHeadObservation,
)
from autospine_workbench.body_sway_probe_report_evidence import (
    tick_schedule_sha256,
)
from autospine_workbench.body_sway_visual_review_address import (
    ExactVisualReviewAddress,
)
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleReader,
)
from autospine_workbench.seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
)
from autospine_workbench.seam_anchor_review_json import canonical_json_bytes
from tests.reviewed_motion_bundle_helpers import ReviewedMotionStorageFixture


SHA = "a" * 64
SOURCE = "autospine_workbench.body_sway_motion_consumer_source."
VALIDATION = "autospine_workbench.body_sway_motion_consumer_validation."


def consumer_fixture(root: Path):
    fixture = ReviewedMotionStorageFixture(Path(root))
    fixture.publish()
    contract = fixture.contract
    bundle = VerifiedReviewedMotionBundleReader(fixture.state_root).load(
        contract.project_id,
        contract.motion_instance_v2_sha256,
        contract.bundle_sha256,
        mesh_bundle=fixture.mesh,
        retarget_bundle=fixture.retarget,
    )
    probe = certified_probe(bundle)
    identity = head_identity(bundle.project_id)
    return fixture, bundle, probe, identity


def certified_probe(bundle):
    motion = bundle.document("motion-instance-v2.json")
    ticks = [0, motion["timing"]["duration_ticks"]]
    tracks = []
    for track in motion["tracks"]:
        if track["property"] != "rotation":
            continue
        tracks.append({
            "bone_id": track["bone_id"],
            "property": "rotation",
            "keys": [deepcopy(track["keys"][0]), deepcopy(track["keys"][-1])],
        })
    projection = {
        "project_id": bundle.project_id,
        "clip_id": bundle.clip_id,
        "timing": deepcopy(motion["timing"]),
        "probe_tick_schedule_sha256": tick_schedule_sha256(tuple(ticks)),
        "probe_sample_stream_sha256": "b" * 64,
        "sample_ticks": ticks,
        "rotation_tracks": tracks,
        "summary": {
            "sample_count": len(ticks),
            "rotation_track_count": len(tracks),
            "rotation_key_count": len(ticks) * len(tracks),
        },
    }
    continuous = {
        "source_set_sha256": "c" * 64,
        "amplitude_envelope_candidate": {
            "source": {
                "reviewed_probe_report": {
                    "source": {"p9": deepcopy(bundle.identities)}
                }
            }
        },
        "rig_ir_sha256": motion["source"]["p3_rig_sha256"],
        "target_profile_sha256": motion["source"]["target_profile_sha256"],
        "motion_instance_v2_sha256": bundle.motion_instance_v2_sha256,
        "motion_instance_v2": motion,
        "preview_projection_sha256": canonical_sha256(projection),
        "preview_projection": projection,
    }
    proof = {
        "project_id": bundle.project_id,
        "clip_id": bundle.clip_id,
        "source": continuous,
        "status": "continuous_preview_model_structural_certified",
        "claims": {"continuous_preview_model_structural_safety": True},
    }
    return {
        "format": "autospine-body-sway-dynamic-seam-probe",
        "format_version": 1,
        "project_id": bundle.project_id,
        "clip_id": bundle.clip_id,
        "source": {
            "source_set_sha256": "d" * 64,
            "body_sway_continuous_proof_sha256": "e" * 64,
            "body_sway_continuous_preview_proof": proof,
            "reviewed_seam_anchor_set_sha256": "f" * 64,
            "reviewed_seam_anchor_set_bundle_sha256": "1" * 64,
        },
        "claims": {
            "continuous_preview_model_reviewed_anchor_proximity_within_"
            "engineering_tolerance": True,
        },
        "status": (
            "continuous_preview_model_reviewed_anchor_proximity_certified"
        ),
    }


def head_identity(project_id):
    return BodySwayDynamicSeamHeadIdentity(
        "d" * 64,
        project_id,
        ExactVisualReviewAddress(
            project_id, "2" * 64, "3" * 64, "4" * 64
        ),
        "5" * 64, 7, "6" * 64,
        ExactSeamAnchorReviewAddress(
            project_id, "7" * 64, "8" * 64, "9" * 64
        ),
        "a" * 64, 11, "b" * 64, "f" * 64,
    )


def head_observation(identity):
    document = {
        "method": "visual-review-double-snapshot-plus-seam-review-history-a-b",
        "scope": "compile_time",
        "identity": identity.public_document(),
        "checks": {
            "visual_review_head": "observed_current",
            "seam_anchor_review_head": "observed_current",
            "reviewed_seam_anchor_set": "canonical_replay_matched",
        },
        "permanent_authority_claimed": False,
    }
    return BodySwayDynamicSeamHeadObservation(
        identity, canonical_json_bytes(document).decode("utf-8")
    )


@contextmanager
def patched_probe_replay(probe, identity):
    expected = canonical_json_bytes(probe)

    def replay(value):
        if canonical_json_bytes(value) != expected:
            raise ValueError("test-only dynamic probe mismatch")
        return expected

    with ExitStack() as stack:
        source_replay = stack.enter_context(patch(
            SOURCE + "body_sway_dynamic_seam_probe_canonical_bytes",
            side_effect=replay,
        ))
        head = stack.enter_context(patch(
            SOURCE + "extract_body_sway_dynamic_seam_head_identity",
            return_value=identity,
        ))
        validation_replay = stack.enter_context(patch(
            VALIDATION + "body_sway_dynamic_seam_probe_canonical_bytes",
            side_effect=replay,
        ))
        yield source_replay, head, validation_replay
