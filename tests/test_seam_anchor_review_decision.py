"""P10.5b candidate/P3-bound seam decision tests."""

from __future__ import annotations

from copy import deepcopy
import unittest

from autospine_workbench.seam_anchor_review_decision import (
    SeamAnchorReviewDecisionError,
    build_seam_anchor_review_decision,
)
from autospine_workbench.seam_anchor_review_decision_validation import (
    require_seam_anchor_review_decision,
)
from tests.seam_anchor_review_helpers import (
    review_candidate_and_rig,
    seam_review_rows,
)


class SeamAnchorReviewDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate, cls.rig = review_candidate_and_rig()

    def build(self, action="accept", *, previous=None, rows=None):
        return build_seam_anchor_review_decision(
            self.candidate, self.rig,
            review={"reviewer_id": "artist-01", "notes": "six seams"},
            decisions=rows or seam_review_rows(self.candidate, action),
            previous_decision=previous,
        )

    def test_accept_copies_candidate_anchors_and_ready_never_releases(self):
        decision = self.build()
        document = decision.document
        require_seam_anchor_review_decision(
            document, candidates=self.candidate, rig=self.rig
        )
        self.assertEqual("reviewed_anchor_set_ready_for_compile",
                         document["status"])
        self.assertEqual("blocked", document["release_gate"]["status"])
        self.assertEqual(24, document["summary"]["anchor_pair_count"])
        self.assertEqual(
            self.candidate["relationships"][0]["options"][0]["anchors"],
            document["decisions"][0]["anchors"],
        )

    def test_adjust_revalidates_and_reject_blocks(self):
        adjusted = self.build("adjust").document
        self.assertEqual(6, adjusted["summary"]["adjust_count"])
        rejected = self.build("reject").document
        self.assertEqual("reviewed_anchor_set_blocked", rejected["status"])
        self.assertIn("reviewed_seam_anchor_selection_blocked",
                      rejected["release_gate"]["reason_codes"])
        self.assertEqual(0, rejected["summary"]["anchor_pair_count"])

    def test_stale_relationship_option_and_invalid_adjustment_fail_closed(self):
        mutations = []
        stale_relationship = seam_review_rows(self.candidate)
        stale_relationship[0]["relationship_evidence_sha256"] = "a" * 64
        mutations.append(stale_relationship)
        stale_option = seam_review_rows(self.candidate)
        stale_option[0]["option_evidence_sha256"] = "b" * 64
        mutations.append(stale_option)
        reversed_pairs = seam_review_rows(self.candidate, "adjust")
        reversed_pairs[0]["final_anchors"].reverse()
        mutations.append(reversed_pairs)
        crosswire = seam_review_rows(self.candidate, "adjust")
        crosswire[0]["final_anchors"][0]["parent"][
            "attachment_id"
        ] = "pelvis"
        mutations.append(crosswire)
        for rows in mutations:
            with self.subTest(rows=rows), self.assertRaises(
                SeamAnchorReviewDecisionError
            ):
                self.build(rows=rows)

    def test_revision_chain_is_linear_and_candidate_bound(self):
        first = self.build()
        second = self.build("reject", previous=first.document)
        self.assertEqual(2, second.document["review"]["revision"])
        self.assertEqual(first.sha256,
                         second.document["review"][
                             "supersedes_decision_sha256"])
        other = deepcopy(self.candidate)
        other["source"]["bundle_sha256"] = "f" * 64
        with self.assertRaises(SeamAnchorReviewDecisionError):
            build_seam_anchor_review_decision(
                other, self.rig,
                review={"reviewer_id": "artist-01", "notes": "stale"},
                decisions=seam_review_rows(other),
                previous_decision=first.document,
            )


if __name__ == "__main__":
    unittest.main()
