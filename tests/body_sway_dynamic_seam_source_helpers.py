"""Small exact P10.5c fixtures for P10.5d source-closure tests."""

from __future__ import annotations

from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.reviewed_seam_anchor_set_bundle_contract import (
    build_reviewed_seam_anchor_set_bundle_contract,
)
from autospine_workbench.reviewed_seam_anchor_set_compiler import (
    compile_reviewed_seam_anchor_set,
)
from tests.reviewed_seam_anchor_set_helpers import reviewed_set_inputs


def dynamic_seam_values(*, mesh: bool = False):
    """Return a minimal proof shell plus fully validated P10.5c values."""

    candidate, decision, rig = reviewed_set_inputs(
        mesh_id="arm.left" if mesh else None
    )
    reviewed_set = compile_reviewed_seam_anchor_set(
        candidate, decision, rig
    ).document
    contract = build_reviewed_seam_anchor_set_bundle_contract(
        candidate, decision, rig, reviewed_set
    )
    p3 = {
        "layer_manifest_sha256": candidate["source"][
            "layer_manifest_sha256"
        ],
        "rig_sha256": candidate["source"]["rig_sha256"],
        "bundle_sha256": candidate["source"]["bundle_sha256"],
    }
    proof = {
        "format": "test-proof-shell",
        "format_version": 1,
        "project_id": candidate["project_id"],
        "clip_id": "idle",
        "source": {
            "rig_ir_sha256": canonical_sha256(rig),
            "rig_ir": rig,
            "amplitude_envelope_candidate": {
                "source": {
                    "reviewed_probe_report": {"source": {"p3": p3}}
                }
            },
        },
    }
    return proof, candidate, decision, reviewed_set, contract


def build_kwargs(*, mesh: bool = False):
    proof, candidate, decision, reviewed_set, contract = (
        dynamic_seam_values(mesh=mesh)
    )
    return {
        "continuous_proof": proof,
        "seam_anchor_candidates": candidate,
        "seam_anchor_review_decision": decision,
        "reviewed_seam_anchor_set": reviewed_set,
        "reviewed_set_bundle_sha256": contract.bundle_sha256,
    }
