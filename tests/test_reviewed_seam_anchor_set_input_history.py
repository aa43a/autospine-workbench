"""P10.5c detached history identity regression tests."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))


from autospine_workbench.reviewed_seam_anchor_set_inputs import (
    ReviewedSeamAnchorSetInputsError,
    prepare_current_head_reviewed_seam_anchor_set,
)
from autospine_workbench.seam_anchor_review_application_models import (
    ExactSeamAnchorReviewDecision,
)
from autospine_workbench.seam_anchor_review_decision_validation import (
    seam_anchor_review_decision_sha256,
)
from autospine_workbench.seam_anchor_review_history_models import (
    SeamAnchorReviewHistoryRow,
)
from autospine_workbench.seam_anchor_review_json import canonical_json_bytes
from tests.reviewed_seam_anchor_set_helpers import reviewed_set_inputs
from tests.test_reviewed_seam_anchor_set_inputs import _Application, _Fixture


READY = "reviewed_anchor_set_ready_for_compile"


class ReviewedSeamAnchorSetInputHistoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = _Fixture()
        _candidate, self.second, _rig = reviewed_set_inputs(
            previous=self.fixture.decision_document
        )
        self.second_sha = seam_anchor_review_decision_sha256(self.second)

    def test_malformed_history_rows_fail_before_exact_decision(self):
        valid = self.fixture.make_history([
            (self.fixture.decision_sha, READY), (self.second_sha, READY),
        ])
        exact = ExactSeamAnchorReviewDecision(
            self.fixture.address, self.fixture.candidate.sha256,
            self.second_sha, 2,
            canonical_json_bytes(self.second).decode("utf-8"),
        )
        malformed = (
            replace(valid, rows=(
                SeamAnchorReviewHistoryRow(1, "z" * 64, READY),
                valid.rows[1],
            )),
            replace(valid, rows=(
                SeamAnchorReviewHistoryRow(
                    1, self.fixture.decision_sha, "unknown"
                ),
                valid.rows[1],
            )),
            replace(valid, revision_count=2.0),
            replace(valid, current_revision=2.0),
        )
        for history in malformed:
            calls = []
            application = _Application(
                [self.fixture.make_prepared(history)], exact, calls
            )
            with self.subTest(history=history), tempfile.TemporaryDirectory() \
                    as temporary, self.assertRaises(
                        ReviewedSeamAnchorSetInputsError
                    ):
                prepare_current_head_reviewed_seam_anchor_set(
                    Path(temporary), self.fixture.address,
                    candidate_sha256=self.fixture.candidate.sha256,
                    revision=2, decision_sha256=self.second_sha,
                    application=application,
                )
            self.assertEqual(["prepare"], calls)

    def test_current_decision_must_supersede_previous_history_row(self):
        crosswired = json.loads(canonical_json_bytes(self.second))
        crosswired["review"]["supersedes_decision_sha256"] = "a" * 64
        crosswired_sha = seam_anchor_review_decision_sha256(crosswired)
        history = self.fixture.make_history([
            (self.fixture.decision_sha, READY), (crosswired_sha, READY),
        ])
        exact = ExactSeamAnchorReviewDecision(
            self.fixture.address, self.fixture.candidate.sha256,
            crosswired_sha, 2,
            canonical_json_bytes(crosswired).decode("utf-8"),
        )
        calls = []
        application = _Application(
            [self.fixture.make_prepared(history)], exact, calls
        )
        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(
            ReviewedSeamAnchorSetInputsError
        ):
            prepare_current_head_reviewed_seam_anchor_set(
                Path(temporary), self.fixture.address,
                candidate_sha256=self.fixture.candidate.sha256,
                revision=2, decision_sha256=crosswired_sha,
                application=application,
            )
        self.assertEqual(["prepare", "decision"], calls)


if __name__ == "__main__":
    unittest.main()
