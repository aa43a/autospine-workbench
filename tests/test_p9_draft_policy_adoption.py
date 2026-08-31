"""Vertical tests for pending-draft discovery and explicit promotion."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.current_project_chain import CurrentProjectChain
from autospine_workbench.depth_order_inputs import require_depth_order_inputs
from autospine_workbench.p9_draft_policy_adoption import (
    INTENT,
    REQUEST_FORMAT,
    P9DraftPolicyAdoptionError,
    prepare_p9_draft_policy_adoption,
    publish_p9_draft_policy_adoption,
)
from autospine_workbench.p9_review_draft_reader import (
    get_p9_review_draft,
    list_p9_review_drafts,
)
from autospine_workbench.p9_review_draft_validation import (
    P9ReviewDraftValidationError,
    approved_policy_from_proposal,
)
from autospine_workbench.p9_review_draft_store import publish_p9_review_draft
from autospine_workbench.resolved_project import canonical_sha256
from tests.motion_policy_decision_helpers import MotionPolicyDecisionFixture


class P9DraftPolicyAdoptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.shared = tempfile.TemporaryDirectory()
        cls.fixture = MotionPolicyDecisionFixture(Path(cls.shared.name) / "chain")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.shared.cleanup()

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name) / "state"
        self.state.mkdir()
        self.namespace = "wave-left-r6-draft"
        self.project = self.fixture.upstream.mesh.project_id
        self._publish_draft()
        mesh = self.fixture.upstream.mesh
        self.current = {
            self.project: CurrentProjectChain(
                self.project,
                mesh.resolved_project_sha256,
                mesh.layer_manifest_sha256,
            ),
        }
        listing = list_p9_review_drafts(
            self.state, current_project_chains=self.current,
        )
        self.row = listing["drafts"][0]

    def test_list_and_detail_are_path_free_and_semantic(self):
        listing = list_p9_review_drafts(
            self.state, current_project_chains=self.current,
        )
        self.assertEqual(1, listing["count"])
        self.assertEqual(self.row["draft_id"], listing["recommended_draft_id"])
        self.assertEqual("current", self.row["authoring_alignment"])
        detail = get_p9_review_draft(
            self.state, self.row["draft_id"],
            current_project_chains=self.current,
        )
        pair = detail["semantic_summary"]["pairs"][0]
        self.assertEqual("face-vs-leg", pair["pair_id"])
        self.assertEqual("face", pair["setup_front_slot"])
        encoded = json.dumps(detail)
        self.assertNotIn("proposal", detail)
        self.assertNotIn(str(self.state), encoded)
        self.assertNotIn(str(self.shared.name), encoded)

    def test_explicit_confirmation_compiles_and_publishes_new_package(self):
        request = self._request()
        upstream = self.fixture.upstream
        with patch(
            "autospine_workbench.p9_draft_policy_adoption."
            "VerifiedMeshBundleReader",
            return_value=SimpleNamespace(load=lambda *_args: upstream.mesh),
        ), patch(
            "autospine_workbench.p9_draft_policy_adoption."
            "VerifiedMotionRetargetBundleReader",
            return_value=SimpleNamespace(load=lambda *_args: upstream.retarget),
        ), patch(
            "autospine_workbench.p9_draft_policy_adoption."
            "VerifiedProjectedMotionBundleReader",
            return_value=SimpleNamespace(load=lambda *_args: upstream.projected),
        ):
            prepared = prepare_p9_draft_policy_adoption(
                self.state, self.row["draft_id"], request,
                current_project_chains=self.current,
            )
        self.assertNotEqual(self.namespace, prepared.motion_id)
        receipt = publish_p9_draft_policy_adoption(
            self.state, prepared, current_project_chains=self.current,
        )
        replay = publish_p9_draft_policy_adoption(
            self.state, prepared, current_project_chains=self.current,
        )
        self.assertEqual("passed", receipt["status"])
        self.assertEqual({
            "format", "format_version", "status", "draft_id", "project_id",
            "motion_id", "clip_id", "reused", "policy_sha256",
            "depth_candidates_sha256", "package_id",
        }, set(receipt))
        self.assertFalse(receipt["reused"])
        self.assertTrue(replay["reused"])
        self.assertEqual(receipt["package_id"], replay["package_id"])
        self.assertNotIn(str(self.state), json.dumps(receipt))
        package = self.state / "reviews" / prepared.motion_id / self.project
        self.assertEqual({
            "depth-pair-policy.json", "foot-lock-candidates.json",
            "depth-order-candidates.json",
        }, {path.name for path in package.iterdir()})
        policy = json.loads(
            (package / "depth-pair-policy.json").read_text("utf-8")
        )
        self.assertEqual(
            {"status": "approved", "method": "human"}, policy["review"],
        )

    def test_missing_confirmation_fails_before_reader_or_write(self):
        request = self._request()
        request["explicit_confirmation"] = False
        with patch(
            "autospine_workbench.p9_draft_policy_adoption."
            "VerifiedMeshBundleReader",
        ) as reader, self.assertRaises(P9DraftPolicyAdoptionError):
            prepare_p9_draft_policy_adoption(
                self.state, self.row["draft_id"], request,
                current_project_chains=self.current,
            )
        reader.assert_not_called()
        self.assertEqual(
            {self.namespace},
            {path.name for path in (self.state / "reviews").iterdir()},
        )

    def test_single_confirmation_cannot_promote_multiple_depth_pairs(self):
        upstream = self.fixture.upstream
        inputs = require_depth_order_inputs(
            upstream.projected, upstream.retarget, upstream.mesh,
        )
        proposal = deepcopy(upstream.policy(inputs))
        proposal["format"] = "autospine-depth-pair-policy-proposal"
        proposal["review"] = {
            "status": "pending_human_review", "method": "human",
        }
        proposal["proposal"] = {
            "method": "exact-single-pair-operator-review-v1",
            "scope": "one visible pair",
            "rationale": "One confirmation must grant one decision only.",
            "limitations": ["Pending human review."],
        }
        proposal["pairs"].append(deepcopy(proposal["pairs"][0]))
        with self.assertRaises(P9ReviewDraftValidationError):
            approved_policy_from_proposal(proposal)

    def test_manifest_p4_and_p7_sources_must_match_verified_bundles(self):
        upstream = self.fixture.upstream
        wrong_sources = upstream.retarget.source_addresses
        wrong_sources["p4_bundle_sha256"] = "f" * 64
        retarget = _SourceOverride(upstream.retarget, wrong_sources)
        with patch(
            "autospine_workbench.p9_draft_policy_adoption."
            "VerifiedMeshBundleReader",
            return_value=SimpleNamespace(load=lambda *_args: upstream.mesh),
        ), patch(
            "autospine_workbench.p9_draft_policy_adoption."
            "VerifiedMotionRetargetBundleReader",
            return_value=SimpleNamespace(load=lambda *_args: retarget),
        ), patch(
            "autospine_workbench.p9_draft_policy_adoption."
            "VerifiedProjectedMotionBundleReader",
            return_value=SimpleNamespace(load=lambda *_args: upstream.projected),
        ), self.assertRaises(P9DraftPolicyAdoptionError):
            prepare_p9_draft_policy_adoption(
                self.state, self.row["draft_id"], self._request(),
                current_project_chains=self.current,
            )

    def _request(self) -> dict:
        return {
            "format": REQUEST_FORMAT,
            "format_version": 1,
            "intent": INTENT,
            "draft_id": self.row["draft_id"],
            "manifest_sha256": self.row["manifest_sha256"],
            "proposal_sha256": self.row["proposal_sha256"],
            "explicit_confirmation": True,
        }

    def _publish_draft(self) -> None:
        upstream = self.fixture.upstream
        inputs = require_depth_order_inputs(
            upstream.projected, upstream.retarget, upstream.mesh,
        )
        proposal = deepcopy(upstream.policy(inputs))
        proposal["format"] = "autospine-depth-pair-policy-proposal"
        proposal["review"] = {
            "status": "pending_human_review", "method": "human",
        }
        proposal["proposal"] = {
            "method": "exact-single-pair-operator-review-v1",
            "scope": "face versus leg",
            "rationale": "Exact fixture review scope.",
            "limitations": ["Pending human review."],
        }
        evidence = {"format": "test-kimodo-evidence", "format_version": 1}
        foot = self.fixture.foot
        source = upstream.retarget.source_addresses
        manifest = {
            "format": "autospine-motion-policy-review-draft",
            "format_version": 1,
            "status": "pending_human_depth_policy_review",
            "authority": {
                "approved_depth_policy": False,
                "depth_candidates_emitted": False,
                "p9_adoption_emitted": False,
            },
            "project_id": self.project,
            "motion_namespace": self.namespace,
            "clip_id": upstream.projected.clip_id,
            "source": {
                "p3": {
                    "rig_sha256": upstream.mesh.rig_sha256,
                    "bundle_sha256": upstream.mesh.bundle_sha256,
                },
                "p4": {
                    "profile_sha256": source["p4_profile_sha256"],
                    "bundle_sha256": source["p4_bundle_sha256"],
                },
                "p5": {
                    "instance_sha256": upstream.retarget.instance_sha256,
                    "bundle_sha256": upstream.retarget.bundle_sha256,
                },
                "p7": {
                    "motion_sha256": source["motion_clip_sha256"],
                    "bundle_sha256": source["motion_bundle_sha256"],
                },
                "p8": {
                    "motion_sha256": upstream.projected.projected_motion_sha256,
                    "bundle_sha256": upstream.projected.bundle_sha256,
                },
            },
            "outputs": {
                "kimodo_policy_evidence_sha256": canonical_sha256(evidence),
                "foot_candidates_sha256": canonical_sha256(foot),
                "depth_pair_policy_proposal_sha256": canonical_sha256(proposal),
            },
        }
        publish_p9_review_draft(
            self.state, self.namespace, self.project, {
                "shared/kimodo-policy-evidence.json": _canonical(evidence),
                f"{self.project}/depth-pair-policy.proposal.json": _canonical(proposal),
                f"{self.project}/foot-lock-candidates.json": _canonical(foot),
                f"{self.project}/draft-manifest.json": _canonical(manifest),
            },
        )


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


class _SourceOverride:
    def __init__(self, base, source_addresses: dict[str, str]) -> None:
        self._base = base
        self.source_addresses = source_addresses

    def __getattr__(self, name):
        return getattr(self._base, name)


if __name__ == "__main__":
    unittest.main()
