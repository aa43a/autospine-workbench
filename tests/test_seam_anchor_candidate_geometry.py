"""Pure P10.5a static candidate geometry tests."""

from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from autospine_workbench.seam_anchor_candidate_geometry import (
    SeamAnchorCandidateGeometryError,
    derive_seam_candidate_relationships,
)
from autospine_workbench.seam_anchor_candidate_profile import (
    option_evidence_sha256,
    relationship_evidence_sha256,
)
from autospine_workbench.seam_anchor_sampling import (
    SeamAnchorSampling,
    SeamAnchorUnsupportedError,
)
from tests.seam_anchor_candidate_helpers import seam_inputs


class SeamAnchorCandidateGeometryTests(unittest.TestCase):
    def test_six_relationships_have_deterministic_reviewable_options(self):
        inputs = seam_inputs()
        first = derive_seam_candidate_relationships(inputs)
        self.assertEqual(first, derive_seam_candidate_relationships(inputs))
        self.assertEqual(6, len(first))
        self.assertTrue(all(row["status"] == "review_required"
                            for row in first))
        self.assertTrue(all(len(row["options"]) == 1 for row in first))
        for row in first:
            option = row["options"][0]
            self.assertEqual("candidate", option["status"])
            self.assertEqual(4, len(option["anchors"]))
            self.assertEqual([], option["reason_codes"])
            payload = {key: value for key, value in option.items()
                       if key != "evidence_sha256"}
            self.assertEqual(option_evidence_sha256(payload),
                             option["evidence_sha256"])
            relationship = {key: value for key, value in row.items()
                            if key != "evidence_sha256"}
            self.assertEqual(relationship_evidence_sha256(relationship),
                             row["evidence_sha256"])

    def test_region_mesh_uses_barycentric_child_locators(self):
        row = next(item for item in derive_seam_candidate_relationships(
            seam_inputs(mesh_id="arm.left")
        ) if item["relationship_id"] == "seam.torso_arm.left")
        self.assertEqual("mesh", row["options"][0]["child_attachment_type"])
        self.assertTrue(all(
            anchor["child"]["locator_type"] == "mesh-barycentric-q65535"
            for anchor in row["options"][0]["anchors"]
        ))

    def test_gap_is_preserved_and_never_promoted_to_locator_candidate(self):
        row = next(item for item in derive_seam_candidate_relationships(
            seam_inputs(gap_arm_left=True)
        ) if item["relationship_id"] == "seam.torso_arm.left")
        self.assertEqual("unobservable", row["status"])
        option = row["options"][0]
        self.assertEqual("unavailable", option["status"])
        self.assertEqual("gap", option["contact_evidence"]["mode"])
        self.assertEqual([], option["anchors"])
        self.assertIn("GAP_LOCATOR_UNSUPPORTED_IN_V1",
                      option["reason_codes"])

    def test_resource_budget_and_forged_input_type_fail_closed(self):
        with patch(
            "autospine_workbench.seam_anchor_candidate_geometry."
            "MAX_TOTAL_OPTIONS", 1
        ), self.assertRaisesRegex(
            SeamAnchorCandidateGeometryError, "budget"
        ):
            derive_seam_candidate_relationships(seam_inputs())
        with self.assertRaisesRegex(
            SeamAnchorCandidateGeometryError, "admitted"
        ):
            derive_seam_candidate_relationships(object())  # type: ignore[arg-type]
        forged = replace(seam_inputs(), _rig_json="{}")
        with self.assertRaises(SeamAnchorCandidateGeometryError):
            derive_seam_candidate_relationships(forged)

    def test_alpha_run_limit_becomes_explicit_unavailable_not_large_cache(self):
        with patch(
            "autospine_workbench.seam_anchor_alpha_cache."
            "MAX_RUNS_PER_MASK", 1
        ):
            rows = derive_seam_candidate_relationships(seam_inputs())
        self.assertTrue(all(row["status"] == "unobservable" for row in rows))
        self.assertTrue(all(
            option["reason_codes"] == ["SAMPLING_BUDGET_EXCEEDED"]
            for row in rows for option in row["options"]
        ))

    def test_impossible_sampling_and_pair_states_are_invariant_errors(self):
        vanished = SeamAnchorSampling(
            status="unavailable", reason_code="common_alpha_gap",
            principal_axis="x", requested_pair_count=4,
            canvas_point_pairs_xy=(),
        )
        with patch(
            "autospine_workbench.seam_anchor_candidate_geometry."
            "sample_common_alpha_pairs", return_value=vanished,
        ), self.assertRaisesRegex(
            SeamAnchorCandidateGeometryError, "no common alpha"
        ):
            derive_seam_candidate_relationships(seam_inputs())
        with patch(
            "autospine_workbench.seam_anchor_candidate_geometry."
            "materialize_sampled_locator_pairs",
            side_effect=SeamAnchorUnsupportedError("forged"),
        ), self.assertRaisesRegex(
            SeamAnchorCandidateGeometryError, "unsupported locator pair"
        ):
            derive_seam_candidate_relationships(seam_inputs())


if __name__ == "__main__":
    unittest.main()
