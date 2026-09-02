"""Compact exact-bundle fixtures for P10.6a v2 contract tests."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from autospine_workbench.body_sway_dynamic_seam_bundle_reader_v2 import (
    BodySwayDynamicSeamBundleReaderV2,
)
from autospine_workbench.body_sway_dynamic_seam_bundle_store_v2 import (
    BodySwayDynamicSeamBundleStoreV2,
)
from autospine_workbench.body_sway_dynamic_seam_evidence_profile_v2 import (
    CERTIFIED_STATUS,
)
from autospine_workbench.body_sway_dynamic_seam_head_checks_v2 import (
    BodySwayDynamicSeamHeadObservationV2,
)
from autospine_workbench.body_sway_dynamic_seam_profile_v2 import (
    body_sway_dynamic_seam_source_sha256_v2,
)
from autospine_workbench.body_sway_motion_consumer_dynamic_bundle_v2 import (
    require_exact_body_sway_dynamic_seam_bundle_v2,
)
from autospine_workbench.body_sway_probe_report_evidence import (
    tick_schedule_sha256,
)
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.seam_anchor_review_json import canonical_json_bytes
from tests.body_sway_motion_consumer_helpers import consumer_fixture


SOURCE_MODULE = "autospine_workbench.body_sway_motion_consumer_source_v2."
CONTRACT_MODULE = (
    "autospine_workbench.body_sway_dynamic_seam_bundle_contract_v2."
)


def consumer_v2_fixture(root: Path):
    fixture, p9_bundle, _probe, _identity = consumer_fixture(root)
    source, probe = _dynamic_documents(p9_bundle)
    source["source_set_sha256"] = (
        body_sway_dynamic_seam_source_sha256_v2(source)
    )
    probe["source"] = deepcopy(source)
    with validated_dynamic_documents(source, probe):
        published = BodySwayDynamicSeamBundleStoreV2(
            fixture.state_root
        ).publish(
            source, probe,
        )
        dynamic = BodySwayDynamicSeamBundleReaderV2(
            fixture.state_root
        ).load(
            source["project_id"], published.probe_sha256,
            published.bundle_sha256,
        )
    contract = SimpleNamespace(
        project_id=dynamic.project_id, clip_id=dynamic.clip_id,
        source_set_sha256=dynamic.source_set_sha256,
        source_document_sha256=dynamic.source_document_sha256,
        probe_sha256=dynamic.probe_sha256,
        bundle_sha256=dynamic.bundle_sha256,
        document_bytes=dynamic.document_bytes,
    )
    return fixture, p9_bundle, dynamic, contract


def _dynamic_documents(bundle):
    motion = bundle.document("motion-instance-v2.json")
    ticks = [0, motion["timing"]["duration_ticks"]]
    tracks = [
        {
            "bone_id": track["bone_id"], "property": "rotation",
            "keys": [deepcopy(track["keys"][0]), deepcopy(track["keys"][-1])],
        }
        for track in motion["tracks"] if track["property"] == "rotation"
    ]
    projection = {
        "project_id": bundle.project_id, "clip_id": bundle.clip_id,
        "source": {
            "base_motion_instance_v2_sha256": bundle.motion_instance_v2_sha256,
        },
        "timing": deepcopy(motion["timing"]),
        "probe_tick_schedule_sha256": tick_schedule_sha256(tuple(ticks)),
        "probe_sample_stream_sha256": "b" * 64,
        "sample_ticks": ticks, "rotation_tracks": tracks,
        "summary": {
            "sample_count": len(ticks), "rotation_track_count": len(tracks),
            "rotation_key_count": len(ticks) * len(tracks),
        },
    }
    p3 = {
        "layer_manifest_sha256": "1" * 64,
        "rig_sha256": motion["source"]["p3_rig_sha256"],
        "bundle_sha256": motion["source"]["p3_bundle_sha256"],
    }
    p5 = {"target_profile_sha256": motion["source"]["target_profile_sha256"]}
    review_admission = {
        "source": {"visual_review": {
            "candidate_v2_sha256": "2" * 64,
            "revision": 3, "decision_v2_sha256": "4" * 64,
        }},
    }
    candidate = {
        "timing": deepcopy(motion["timing"]),
        "source": {
            "review_admission_v2_sha256": "5" * 64,
            "review_admission_v2": review_admission,
            "reviewed_probe_report": {
                "source": {"p3": p3, "p5": p5, "p9": bundle.identities},
            },
        },
    }
    continuous_source = {
        "amplitude_envelope_candidate_v2": candidate,
        "rig_ir_sha256": p3["rig_sha256"],
        "target_profile_sha256": p5["target_profile_sha256"],
        "motion_instance_v2_sha256": bundle.motion_instance_v2_sha256,
        "motion_instance_v2": motion,
        "preview_projection_v2_sha256": canonical_sha256(projection),
        "preview_projection_v2": projection,
    }
    proof = {
        "project_id": bundle.project_id, "clip_id": bundle.clip_id,
        "source": continuous_source,
        "status": "continuous_preview_model_structural_certified",
        "claims": {"continuous_preview_model_structural_safety": True},
    }
    reviewed_set = {
        "source": {
            "seam_anchor_candidate_sha256": "6" * 64,
            "review_revision": 7,
            "seam_anchor_review_decision_sha256": "8" * 64,
        },
    }
    source = {
        "format": "autospine-body-sway-dynamic-seam-source",
        "format_version": 2, "project_id": bundle.project_id,
        "clip_id": bundle.clip_id, "source_set_sha256": "9" * 64,
        "layer_manifest_sha256": p3["layer_manifest_sha256"],
        "p3_rig_sha256": p3["rig_sha256"],
        "p3_bundle_sha256": p3["bundle_sha256"],
        "body_sway_continuous_preview_proof_v2_sha256": "a" * 64,
        "body_sway_continuous_preview_proof_v2": proof,
        "seam_anchor_candidates_v1_sha256": "e" * 64,
        "seam_anchor_candidates_v1": {},
        "seam_anchor_review_decision_v1_sha256": "f" * 64,
        "seam_anchor_review_decision_v1": {},
        "review_revision": 7,
        "reviewed_seam_anchor_set_v1_sha256": "c" * 64,
        "reviewed_seam_anchor_set_v1_bundle_sha256": "d" * 64,
        "reviewed_seam_anchor_set_v1": reviewed_set,
    }
    probe = {
        "format": "autospine-body-sway-dynamic-seam-probe",
        "format_version": 2, "project_id": bundle.project_id,
        "clip_id": bundle.clip_id, "source": deepcopy(source),
        "status": CERTIFIED_STATUS,
        "claims": {
            "continuous_preview_v2_anchor_residual_within_engineering_"
            "tolerance": True,
            "structural_gap_proxy_within_engineering_tolerance": True,
        },
        "problem": {}, "segments": [], "analyzer": {},
        "release_gate": {"status": "blocked"}, "summary": {},
    }
    return source, probe


@contextmanager
def patched_dynamic_bundle_replay(dynamic, contract):
    with patch(
        SOURCE_MODULE + "require_exact_body_sway_dynamic_seam_bundle_v2",
        wraps=require_exact_body_sway_dynamic_seam_bundle_v2,
    ) as rebuilt:
        yield rebuilt


@contextmanager
def validated_dynamic_documents(source, probe):
    """Let synthetic fixtures traverse the real immutable store and reader."""

    def admit(value):
        if canonical_json_bytes(value) != canonical_json_bytes(source):
            raise ValueError("source tamper")
        return deepcopy(value)

    def probe_digest(value):
        if canonical_json_bytes(value) != canonical_json_bytes(probe):
            raise ValueError("probe tamper")
        return hashlib.sha256(canonical_json_bytes(value)).hexdigest()

    with patch(
        CONTRACT_MODULE + "require_body_sway_dynamic_seam_source_v2",
        side_effect=admit,
    ), patch(
        CONTRACT_MODULE + "body_sway_dynamic_seam_probe_sha256_v2",
        side_effect=probe_digest,
    ):
        yield


def head_observation_v2(core):
    document = core.expected_head_observation
    return BodySwayDynamicSeamHeadObservationV2(
        core.head_identity_sha256,
        canonical_json_bytes(document).decode("utf-8"),
    )
