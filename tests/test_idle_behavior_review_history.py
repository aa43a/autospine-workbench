"""Linear CAS and alias-safe P10.1 decision-history tests."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from autospine_workbench.idle_behavior_decision import (
    build_idle_behavior_decision,
)
from autospine_workbench.idle_behavior_review_history import (
    IdleBehaviorReviewHistoryError,
    IdleBehaviorReviewRevisionConflict,
    publish_idle_behavior_review_decision,
    snapshot_idle_behavior_review_history,
)
from tests.idle_behavior_decision_helpers import (
    adjust_decision,
    completed_review,
    terminal_decision,
)
from tests.test_idle_behavior_candidate_validation import valid_candidates


class IdleBehaviorReviewHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name) / "state"
        self.state.mkdir()
        self.candidates = valid_candidates()

    def decision(self, revision, action="adjust"):
        row = (
            adjust_decision(self.candidates)
            if action == "adjust"
            else terminal_decision(action, self.candidates)
        )
        return build_idle_behavior_decision(
            self.candidates,
            review=completed_review(revision),
            decisions=[row],
        )

    def test_append_readback_and_current_head_retry_are_deterministic(self):
        decision = self.decision(1)
        first = publish_idle_behavior_review_decision(
            self.state, decision, self.candidates,
            base_revision=0, previous_decision_sha256=None,
        )
        second = publish_idle_behavior_review_decision(
            self.state, decision, self.candidates,
            base_revision=0, previous_decision_sha256=None,
        )
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        snapshot = snapshot_idle_behavior_review_history(
            self.state, self.candidates,
        )
        self.assertEqual(1, snapshot.current_revision)
        self.assertEqual(decision.sha256, snapshot.head_decision_sha256)
        self.assertEqual("pending_probe", snapshot.rows[0].probe_status)
        self.assertEqual(
            decision.document["decisions"][0]["payload"],
            snapshot.rows[0].parameters,
        )
        snapshot.rows[0].parameters["cycles"] = 99
        self.assertNotEqual(99, snapshot.rows[0].parameters["cycles"])

    def test_stale_or_skipped_predecessor_is_a_conflict(self):
        first = self.decision(1)
        publish_idle_behavior_review_decision(
            self.state, first, self.candidates,
            base_revision=0, previous_decision_sha256=None,
        )
        with self.assertRaises(IdleBehaviorReviewRevisionConflict):
            publish_idle_behavior_review_decision(
                self.state, self.decision(2, "reject"), self.candidates,
                base_revision=1, previous_decision_sha256="f" * 64,
            )
        with self.assertRaises(IdleBehaviorReviewHistoryError):
            publish_idle_behavior_review_decision(
                self.state, self.decision(3), self.candidates,
                base_revision=2, previous_decision_sha256="f" * 64,
            )

    def test_old_identical_slot_is_not_reused_after_a_new_head(self):
        first = self.decision(1)
        publish_idle_behavior_review_decision(
            self.state, first, self.candidates,
            base_revision=0, previous_decision_sha256=None,
        )
        second = self.decision(2, "reject")
        publish_idle_behavior_review_decision(
            self.state, second, self.candidates,
            base_revision=1, previous_decision_sha256=first.sha256,
        )
        snapshot = snapshot_idle_behavior_review_history(
            self.state, self.candidates,
        )
        self.assertIsNone(snapshot.rows[1].parameters)
        with self.assertRaises(IdleBehaviorReviewRevisionConflict):
            publish_idle_behavior_review_decision(
                self.state, first, self.candidates,
                base_revision=0, previous_decision_sha256=None,
            )

    def test_extra_revision_inventory_entry_fails_closed(self):
        first = self.decision(1)
        publish_idle_behavior_review_decision(
            self.state, first, self.candidates,
            base_revision=0, previous_decision_sha256=None,
        )
        revision_dir = next(self.state.rglob("revisions"))
        (revision_dir / "private.txt").write_text("{}", encoding="utf-8")
        with self.assertRaises(IdleBehaviorReviewHistoryError):
            snapshot_idle_behavior_review_history(
                self.state, self.candidates,
            )


if __name__ == "__main__":
    unittest.main()
