"""Advisory-only P10.5b review-assist tests."""

from __future__ import annotations

from copy import deepcopy
import unittest

from autospine_workbench.seam_anchor_review_assist import (
    SeamAnchorReviewAssistError,
    build_seam_anchor_review_assist,
)
from tests.seam_anchor_review_helpers import review_candidate_and_rig


class SeamAnchorReviewAssistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate, _rig = review_candidate_and_rig()
        self.digest = "a" * 64

    def test_single_options_are_prefilled_but_never_approved(self):
        first = build_seam_anchor_review_assist(
            self.candidate, self.digest,
        )
        second = build_seam_anchor_review_assist(
            deepcopy(self.candidate), self.digest,
        )
        self.assertEqual(first, second)
        self.assertTrue(first["human_confirmation_required"])
        self.assertEqual(6, first["auto_fill_count"])
        self.assertEqual(0, first["manual_required_count"])
        for row in first["suggestions"]:
            self.assertIsNone(row["action"])
            self.assertTrue(row["batch_eligible"])
            self.assertEqual("single_option", row["disposition"])
            self.assertIsNotNone(row["option_id"])

    def test_multiple_options_only_highlight_and_unobservable_blocks(self):
        candidate = deepcopy(self.candidate)
        relationship = candidate["relationships"][0]
        alternative = deepcopy(relationship["options"][0])
        alternative["option_id"] = relationship["relationship_id"] + ".option.001"
        alternative["evidence_sha256"] = "b" * 64
        alternative["contact_evidence"]["overlap_ratios"] = [0.9, 0.8]
        relationship["options"].append(alternative)
        blocked = candidate["relationships"][2]
        blocked["status"] = "unobservable"
        blocked["reason_codes"] = ["attachment_missing"]
        blocked["options"] = []

        assist = build_seam_anchor_review_assist(candidate, self.digest)
        compared = assist["suggestions"][0]
        self.assertEqual("compare_options", compared["disposition"])
        self.assertIsNone(compared["action"])
        self.assertIsNone(compared["option_id"])
        self.assertEqual(alternative["option_id"], compared["highlight_option_id"])
        self.assertFalse(compared["batch_eligible"])
        unobservable = assist["suggestions"][2]
        self.assertEqual("blocked_unobservable", unobservable["disposition"])
        self.assertEqual("unobservable", unobservable["action"])
        self.assertIsNone(unobservable["option_id"])

    def test_invalid_identity_and_non_overlap_require_fail_closed_handling(self):
        with self.assertRaises(SeamAnchorReviewAssistError):
            build_seam_anchor_review_assist(self.candidate, "not-a-sha")
        candidate = deepcopy(self.candidate)
        candidate["relationships"][0]["options"][0][
            "contact_evidence"
        ]["gap_distance_px"] = 1.0
        row = build_seam_anchor_review_assist(candidate, self.digest)[
            "suggestions"
        ][0]
        self.assertEqual("manual_required", row["disposition"])
        self.assertFalse(row["batch_eligible"])
        self.assertIsNone(row["option_id"])


if __name__ == "__main__":
    unittest.main()
