"""Focused predecessor-resolution tests for the P10.3c v2 app support."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_visual_review_application_support_v2 import (  # noqa: E402
    load_previous_visual_review_decision_v2,
)
from autospine_workbench.body_sway_visual_review_errors_v2 import (  # noqa: E402
    BodySwayVisualReviewRevisionV2Conflict,
)


SHA = lambda value: value * 64


class PreviousVisualReviewDecisionV2Tests(unittest.TestCase):
    def setUp(self):
        self.store = Mock(spec_set=["load_decision"])
        self.candidate = SimpleNamespace(
            document={"project_id": "sample-a"}, sha256=SHA("1"),
        )
        self.execution = object()
        self.preview = object()
        self.previous_sha = SHA("2")
        self.history = SimpleNamespace(
            current_revision=1, head_decision_sha256=self.previous_sha,
            rows=(SimpleNamespace(decision_sha256=self.previous_sha),),
        )

    def load(self, submission):
        return load_previous_visual_review_decision_v2(
            self.store, submission, self.candidate,
            self.execution, self.preview, self.history,
        )

    def test_zero_base_has_no_predecessor_and_never_reads_store(self):
        submission = SimpleNamespace(
            base_revision=0, previous_decision_sha256=None,
        )
        self.assertIsNone(self.load(submission))
        self.store.load_decision.assert_not_called()

    def test_exact_predecessor_is_loaded_with_all_authoritative_inputs(self):
        previous = SimpleNamespace(document={"review": {"revision": 1}})
        self.store.load_decision.return_value = previous
        submission = SimpleNamespace(
            base_revision=1, previous_decision_sha256=self.previous_sha,
        )

        self.assertIs(previous, self.load(submission))
        self.store.load_decision.assert_called_once_with(
            "sample-a", self.candidate.sha256, self.previous_sha,
            candidates=self.candidate, execution=self.execution,
            preview=self.preview,
        )

    def test_history_mismatch_is_typed_conflict_before_store_read(self):
        submission = SimpleNamespace(
            base_revision=1, previous_decision_sha256=SHA("3"),
        )
        with self.assertRaises(BodySwayVisualReviewRevisionV2Conflict) as caught:
            self.load(submission)

        self.store.load_decision.assert_not_called()
        self.assertEqual((2, 1, SHA("3"), self.previous_sha), (
            caught.exception.requested_revision,
            caught.exception.current_revision,
            caught.exception.requested_head,
            caught.exception.current_head,
        ))

    def test_loaded_predecessor_revision_mismatch_is_typed_conflict(self):
        self.store.load_decision.return_value = SimpleNamespace(
            document={"review": {"revision": 2}},
        )
        submission = SimpleNamespace(
            base_revision=1, previous_decision_sha256=self.previous_sha,
        )

        with self.assertRaises(BodySwayVisualReviewRevisionV2Conflict):
            self.load(submission)
        self.store.load_decision.assert_called_once()


if __name__ == "__main__":
    unittest.main()
