"""P10.5c pure compiler tests for reviewed static seam anchors."""

from __future__ import annotations

import unittest

from autospine_workbench.reviewed_seam_anchor_set_binding_validation import (
    require_bound_reviewed_seam_anchor_set,
)
from autospine_workbench.reviewed_seam_anchor_set_compiler import (
    ReviewedSeamAnchorSetCompilerError,
    compile_reviewed_seam_anchor_set,
)
from autospine_workbench.reviewed_seam_anchor_set_profile import (
    RELATIONSHIP_IDS,
)
from autospine_workbench.reviewed_seam_anchor_set_validation import (
    reviewed_seam_anchor_set_sha256,
)
from autospine_workbench.seam_anchor_candidate_validation import (
    seam_anchor_candidates_sha256,
)
from autospine_workbench.seam_anchor_review_decision import (
    build_seam_anchor_review_decision,
)
from autospine_workbench.seam_anchor_review_decision_validation import (
    seam_anchor_review_decision_sha256,
)
from tests.reviewed_seam_anchor_set_helpers import reviewed_set_inputs
from tests.seam_anchor_review_helpers import seam_review_rows


class ReviewedSeamAnchorSetCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate, cls.decision, cls.rig = reviewed_set_inputs()

    def compile(self, decision=None):
        return compile_reviewed_seam_anchor_set(
            self.candidate, decision or self.decision, self.rig
        )

    def test_compiles_only_six_materialized_static_anchor_rows(self):
        value = self.compile()
        document = value.document
        require_bound_reviewed_seam_anchor_set(
            document, self.candidate, self.decision, self.rig
        )
        self.assertEqual(
            list(RELATIONSHIP_IDS),
            [row["relationship_id"] for row in document["relationships"]],
        )
        self.assertTrue(all(
            set(row) == {"relationship_id", "anchors"}
            for row in document["relationships"]
        ))
        self.assertEqual(
            self.decision["decisions"][0]["anchors"],
            document["relationships"][0]["anchors"],
        )
        self.assertNotIn("option_id", document["relationships"][0])
        self.assertNotIn("contact_evidence", document["relationships"][0])

    def test_seven_part_provenance_is_exact(self):
        document = self.compile().document
        source = document["source"]
        self.assertEqual(self.candidate["project_id"], document["project_id"])
        self.assertEqual(6, len(source))
        self.assertEqual(
            self.candidate["source"]["layer_manifest_sha256"],
            source["layer_manifest_sha256"],
        )
        self.assertEqual(
            self.candidate["source"]["rig_sha256"],
            source["p3_rig_sha256"],
        )
        self.assertEqual(
            self.candidate["source"]["bundle_sha256"],
            source["p3_bundle_sha256"],
        )
        self.assertEqual(
            seam_anchor_candidates_sha256(self.candidate),
            source["seam_anchor_candidate_sha256"],
        )
        self.assertEqual(1, source["review_revision"])
        self.assertEqual(
            seam_anchor_review_decision_sha256(self.decision),
            source["seam_anchor_review_decision_sha256"],
        )

    def test_ready_selection_does_not_claim_release_or_dynamic_proof(self):
        self.assertEqual(
            "reviewed_anchor_set_ready_for_compile", self.decision["status"]
        )
        self.assertEqual("blocked", self.decision["release_gate"]["status"])
        document = self.compile().document
        self.assertEqual("blocked", document["release_gate"]["status"])
        for claim in (
            "dynamic_seam_safety", "visual_seam_quality",
            "runtime_equivalence", "publishable_timeline",
            "release_authority",
        ):
            self.assertIs(False, document["claims"][claim])

    def test_accept_and_adjust_are_both_authoritative_without_reselection(self):
        rows = seam_review_rows(self.candidate)
        adjusted = seam_review_rows(self.candidate, "adjust")[1]
        rows[1] = adjusted
        decision = build_seam_anchor_review_decision(
            self.candidate,
            self.rig,
            review={"reviewer_id": "artist-02", "notes": "one adjusted"},
            decisions=rows,
        ).document
        document = self.compile(decision).document
        self.assertEqual(
            decision["decisions"][1]["anchors"],
            document["relationships"][1]["anchors"],
        )

    def test_mesh_locators_remain_exact_static_locators(self):
        candidate, decision, rig = reviewed_set_inputs(mesh_id="torso")
        document = compile_reviewed_seam_anchor_set(
            candidate, decision, rig
        ).document
        parent = document["relationships"][0]["anchors"][0]["parent"]
        self.assertEqual("mesh", parent["attachment_type"])
        self.assertEqual("mesh-barycentric-q65535", parent["locator_type"])

    def test_blocked_decision_cannot_compile(self):
        _candidate, decision, _rig = reviewed_set_inputs(action="reject")
        self.assertEqual("reviewed_anchor_set_blocked", decision["status"])
        with self.assertRaises(ReviewedSeamAnchorSetCompilerError):
            self.compile(decision)

    def test_canonical_hash_is_deterministic_and_document_is_isolated(self):
        first, second = self.compile(), self.compile()
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(first.sha256,
                         reviewed_seam_anchor_set_sha256(first.document))
        leaked = first.document
        leaked["relationships"][0]["anchors"].clear()
        self.assertEqual(4, len(first.document["relationships"][0]["anchors"]))

    def test_later_review_revision_changes_exact_provenance(self):
        second = build_seam_anchor_review_decision(
            self.candidate,
            self.rig,
            review={"reviewer_id": "artist-01", "notes": "confirmed"},
            decisions=seam_review_rows(self.candidate),
            previous_decision=self.decision,
        ).document
        first_set, second_set = self.compile(), self.compile(second)
        self.assertEqual(2, second_set.document["source"]["review_revision"])
        self.assertNotEqual(first_set.sha256, second_set.sha256)


if __name__ == "__main__":
    unittest.main()
