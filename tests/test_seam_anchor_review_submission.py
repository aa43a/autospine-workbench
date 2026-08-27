"""P10.5b user-authored seam submission boundary tests."""

from __future__ import annotations

from copy import deepcopy
import unittest

from autospine_workbench.seam_anchor_review_submission import (
    SeamAnchorReviewSubmissionError,
    require_seam_anchor_review_submission,
)
from tests.seam_anchor_review_helpers import (
    review_candidate_and_rig,
    seam_review_payload,
)


class SeamAnchorReviewSubmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate, _rig = review_candidate_and_rig()

    def test_normalizes_only_explicit_human_fields(self):
        value = seam_review_payload(self.candidate, action="adjust")
        result = require_seam_anchor_review_submission(value)
        self.assertEqual(0, result.base_revision)
        self.assertIsNone(result.previous_decision_sha256)
        self.assertEqual(6, len(result.decisions))
        self.assertIn("final_anchors", result.decisions[0])

    def test_extra_derived_duplicate_nonfinite_and_subclass_fail_closed(self):
        valid = seam_review_payload(self.candidate)
        cases = []
        extra = deepcopy(valid)
        extra["revision"] = 1
        cases.append(extra)
        derived = deepcopy(valid)
        derived["decisions"][0]["final_anchors"] = []
        cases.append(derived)
        duplicate = deepcopy(valid)
        duplicate["decisions"][1] = deepcopy(duplicate["decisions"][0])
        cases.append(duplicate)
        nonfinite = deepcopy(valid)
        nonfinite["review"]["notes"] = float("nan")
        cases.append(nonfinite)
        missing_note = deepcopy(valid)
        missing_note["decisions"][0]["action"] = "reject"
        missing_note["decisions"][0]["notes"] = ""
        cases.append(missing_note)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(
                SeamAnchorReviewSubmissionError
            ):
                require_seam_anchor_review_submission(value)

        class LyingList(list):
            def __len__(self):
                return 6

        subclass = deepcopy(valid)
        subclass["decisions"] = LyingList(subclass["decisions"])
        with self.assertRaises(SeamAnchorReviewSubmissionError):
            require_seam_anchor_review_submission(subclass)

    def test_revision_predecessor_matrix_is_strict(self):
        value = seam_review_payload(self.candidate)
        value["previous_decision_sha256"] = "a" * 64
        with self.assertRaises(SeamAnchorReviewSubmissionError):
            require_seam_anchor_review_submission(value)
        value["base_revision"] = 1
        normalized = require_seam_anchor_review_submission(value)
        self.assertEqual("a" * 64, normalized.previous_decision_sha256)


if __name__ == "__main__":
    unittest.main()
