"""Fixtures for exact reviewed seam-anchor set bundle tests."""

from __future__ import annotations

import json
from pathlib import Path

from autospine_workbench.layer_manifest import LayerManifestBundleStore
from autospine_workbench.mesh_bundle_reader import VerifiedMeshBundleReader
from autospine_workbench.mesh_bundle_store import MeshBundleStore
from autospine_workbench.mesh_pipeline import VerifiedMeshPipeline
from autospine_workbench.region_rig import compile_region_rig
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.reviewed_seam_anchor_set_bundle_store import (
    ReviewedSeamAnchorSetBundleStore,
)
from autospine_workbench.reviewed_seam_anchor_set_compiler import (
    compile_reviewed_seam_anchor_set,
)
from autospine_workbench.rig_bundle import RigBundleStore
from autospine_workbench.seam_anchor_candidates import SeamAnchorCandidates
from autospine_workbench.seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
)
from autospine_workbench.seam_anchor_review_application import (
    SeamAnchorReviewApplication,
)
from autospine_workbench.seam_anchor_review_candidate_binding import (
    BoundSeamAnchorReviewCandidate,
    load_bound_seam_anchor_review_candidate,
)
from autospine_workbench.seam_anchor_review_decision import (
    SeamAnchorReviewDecision,
)
from autospine_workbench.seam_anchor_review_history import (
    load_seam_anchor_review_decision,
)
from autospine_workbench.seam_anchor_review_json import canonical_json_bytes
from tests.p10_candidate_helpers import PROJECT, _resolved_for_project
from tests.reviewed_seam_anchor_set_helpers import reviewed_set_inputs
from tests.seam_anchor_review_helpers import seam_review_rows
from tests.test_seam_anchor_review_http_evidence_e2e import (
    _manifest_and_assets,
)
from tests.test_verified_mesh_compiler import _probes


def exact_bundle_values(*, note: str = "six seams"):
    candidate_doc, decision_doc, rig = reviewed_set_inputs()
    decision_doc["review"]["notes"] = note
    candidates = SeamAnchorCandidates(
        canonical_json_bytes(candidate_doc).decode("utf-8")
    )
    decision = SeamAnchorReviewDecision(
        canonical_json_bytes(decision_doc).decode("utf-8")
    )
    reviewed_set = compile_reviewed_seam_anchor_set(
        candidates.document, decision.document, rig
    )
    return candidates, decision, rig, reviewed_set


def bound_value(candidates: SeamAnchorCandidates, rig: dict):
    return BoundSeamAnchorReviewCandidate(
        candidates,
        json.dumps(
            rig, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ),
    )


class PersistedReviewedSeamAnchorSetFixture:
    """Publish P3, revision 1 bundle, then advance review head to revision 2."""

    def __init__(self, root: Path, *, advance: bool = True) -> None:
        self.state = Path(root) / "state"
        manifest, assets, sizes = _manifest_and_assets(Path(root) / "assets")
        compiled = compile_region_rig(
            manifest,
            _resolved_for_project(),
            layer_manifest_sha256=canonical_sha256(manifest),
            image_sizes=sizes,
        )
        layers, manifest_sha = LayerManifestBundleStore(self.state).publish(
            PROJECT, manifest, assets
        )
        rig_path, rig_sha = RigBundleStore(self.state).publish(
            PROJECT,
            compiled.rig,
            compiled.run_manifest,
            _probes(PROJECT, compiled.rig, compiled.run_manifest),
            layers,
        )
        mesh_result = VerifiedMeshPipeline(self.state).build(
            PROJECT, rig_sha, rig_path.name
        )
        mesh_address = MeshBundleStore(self.state).publish(
            PROJECT,
            mesh_result.rig,
            mesh_result.run_manifest,
            mesh_result.probes,
            mesh_result.visuals,
            mesh_result.pngs,
        )
        mesh = VerifiedMeshBundleReader(self.state).load(
            PROJECT, mesh_address.rig_sha256, mesh_address.bundle_sha256
        )
        self.address = ExactSeamAnchorReviewAddress(
            PROJECT, manifest_sha, mesh.rig_sha256, mesh.bundle_sha256
        )
        app = SeamAnchorReviewApplication(self.state)
        prepared = app.prepare(self.address)
        first = app.submit(
            self.address, self._payload(prepared, "first ready review")
        )
        if first.status != "reviewed_anchor_set_ready_for_compile":
            raise AssertionError("Persisted seam fixture is not fully observable")
        bound = load_bound_seam_anchor_review_candidate(
            self.state, self.address
        )
        decision = load_seam_anchor_review_decision(
            self.state,
            self.address,
            bound.candidates.sha256,
            first.decision_sha256,
            candidates=bound.candidates,
            rig=bound.rig,
        )
        reviewed_set = compile_reviewed_seam_anchor_set(
            bound.candidates.document, decision.document, bound.rig
        )
        self.published = ReviewedSeamAnchorSetBundleStore(
            self.state
        ).publish(bound.candidates, decision, bound.rig, reviewed_set)
        self._application = app
        if advance:
            self.advance()

    def advance(self) -> None:
        current = self._application.prepare(self.address)
        second = self._application.submit(
            self.address, self._payload(current, "second ready review")
        )
        self.current_revision = second.revision
        self.current_head_sha256 = second.decision_sha256

    @staticmethod
    def _payload(prepared, notes: str) -> dict:
        return {
            "base_revision": prepared.history.current_revision,
            "candidate_sha256": prepared.candidate_sha256,
            "previous_decision_sha256": prepared.history.head_decision_sha256,
            "review": {"reviewer_id": "bundle-test", "notes": notes},
            "decisions": seam_review_rows(
                prepared.candidate_document, "accept"
            ),
        }
