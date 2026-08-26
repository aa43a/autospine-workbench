"""P10.1 strict human idle decision builder tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import unittest

from autospine_workbench.idle_behavior_candidate_validation import (
    idle_behavior_candidates_sha256,
)
from autospine_workbench.idle_behavior_decision import (
    IdleBehaviorDecisionError,
    build_idle_behavior_decision,
)
from autospine_workbench.idle_behavior_decision_validation import (
    idle_behavior_decision_sha256,
    require_idle_behavior_decision,
)
from tests.idle_behavior_decision_helpers import (
    adjust_decision,
    candidates_without_candidate,
    completed_review,
    terminal_decision,
)
from tests.test_idle_behavior_candidate_validation import valid_candidates


class IdleBehaviorDecisionBuilderTests(unittest.TestCase):
    def build(self, *, candidates=None, review=None, decisions=None):
        selected = valid_candidates() if candidates is None else candidates
        rows = [adjust_decision(selected)] if decisions is None else decisions
        return build_idle_behavior_decision(
            selected,
            review=completed_review() if review is None else review,
            decisions=rows,
        )

    def test_deterministic_frozen_non_mutating_canonical_value(self):
        candidates = valid_candidates()
        review = completed_review(3)
        decisions = [adjust_decision(candidates)]
        before = deepcopy((candidates, review, decisions))
        first = self.build(
            candidates=candidates, review=review, decisions=decisions,
        )
        second = self.build(
            candidates=deepcopy(candidates), review=deepcopy(review),
            decisions=deepcopy(decisions),
        )
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(before, (candidates, review, decisions))
        self.assertEqual(first.sha256,
                         idle_behavior_decision_sha256(first.document))
        changed = first.document
        changed["summary"]["adjust_count"] = 0
        self.assertEqual(1, first.document["summary"]["adjust_count"])
        with self.assertRaises(FrozenInstanceError):
            first._canonical_json = "{}"  # type: ignore[misc]

    def test_source_timing_and_candidate_inventory_are_exactly_bound(self):
        candidates = valid_candidates()
        document = self.build(candidates=candidates).document
        self.assertEqual(candidates["project_id"], document["project_id"])
        self.assertEqual(candidates["clip_id"], document["clip_id"])
        self.assertEqual(candidates["timing"], document["timing"])
        self.assertEqual(
            idle_behavior_candidates_sha256(candidates),
            document["source"]["idle_behavior_candidates_sha256"],
        )
        self.assertEqual(
            candidates["source"]["p5"]["target_profile_sha256"],
            document["source"]["target_profile_sha256"],
        )
        self.assertEqual(
            candidates["source"]["p9"]["motion_instance_v2_sha256"],
            document["source"]["motion_instance_v2_sha256"],
        )
        self.assertEqual(
            candidates["source"]["p9"]["bundle_sha256"],
            document["source"]["reviewed_motion_bundle_sha256"],
        )
        require_idle_behavior_decision(document, candidates=candidates)

    def test_review_is_completed_human_work_not_runtime_approval(self):
        for review in (
            {"method": "automatic", "status": "completed", "revision": 1},
            {"method": "human", "status": "approved", "revision": 1},
            {"method": "human", "status": "completed", "revision": 0},
            {"method": "human", "status": "completed", "revision": True},
            {"method": "human", "status": "completed", "revision": 2 ** 31},
        ):
            with self.subTest(review=review), self.assertRaises(
                IdleBehaviorDecisionError
            ):
                self.build(review=review)

    def test_accept_is_forbidden_and_adjust_remains_pending_probe(self):
        accepted = adjust_decision()
        accepted["action"] = "accept"
        with self.assertRaisesRegex(IdleBehaviorDecisionError, "unsupported"):
            self.build(decisions=[accepted])
        document = self.build().document
        self.assertEqual("pending_probe", document["decisions"][0]["probe_status"])
        self.assertFalse(document["semantics"]["runtime_timeline_emitted"])
        self.assertFalse(document["semantics"]["safe_range_claimed"])
        self.assertFalse(document["semantics"]["automatic_acceptance"])
        self.assertFalse(any(key in document for key in (
            "timeline", "tracks", "safe_range", "generated_raster",
        )))

    def test_reject_and_unobservable_are_explicit_terminal_choices(self):
        for action in ("reject", "unobservable"):
            result = self.build(decisions=[terminal_decision(action)])
            row = result.document["decisions"][0]
            self.assertIsNone(row["payload"])
            self.assertEqual("not_applicable", row["probe_status"])
            self.assertEqual(1, result.document["summary"][f"{action}_count"])
            self.assertEqual(0, result.document["summary"]["pending_probe_count"])

    def test_no_candidate_requires_and_accepts_empty_decisions(self):
        candidates = candidates_without_candidate()
        result = self.build(candidates=candidates, decisions=[])
        self.assertEqual([], result.document["decisions"])
        self.assertEqual({
            "candidate_count": 0, "decision_count": 0, "adjust_count": 0,
            "reject_count": 0, "unobservable_count": 0,
            "pending_probe_count": 0,
        }, result.document["summary"])
        with self.assertRaisesRegex(IdleBehaviorDecisionError, "not exhaustive"):
            self.build(candidates=candidates,
                       decisions=[terminal_decision("reject")])

    def test_builder_rejects_non_json_input_without_mutation(self):
        decisions = [adjust_decision()]
        decisions[0]["payload"]["cycles"] = object()
        before = decisions[0]["candidate_id"]
        with self.assertRaises(IdleBehaviorDecisionError):
            self.build(decisions=decisions)
        self.assertEqual(before, decisions[0]["candidate_id"])
        for rows in ([None], ["not-a-decision"], {"not": "an-array"}):
            with self.subTest(rows=rows), self.assertRaises(
                IdleBehaviorDecisionError
            ):
                self.build(decisions=rows)


if __name__ == "__main__":
    unittest.main()
