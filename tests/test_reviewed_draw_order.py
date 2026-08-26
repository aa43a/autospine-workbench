"""P9.4 reviewed depth-decision projection tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.depth_order_candidate_validation import (  # noqa: E402
    require_depth_order_candidates,
)
from autospine_workbench.depth_order_schmitt import (  # noqa: E402
    evaluate_depth_pair,
    quantize_depth_score,
)
from autospine_workbench.motion_policy_candidate_inventory import (  # noqa: E402
    derive_motion_policy_candidates,
)
from autospine_workbench.motion_policy_decision import (  # noqa: E402
    build_motion_policy_decision,
)
from autospine_workbench.reviewed_draw_order import (  # noqa: E402
    ReviewedDrawOrderError,
    compile_reviewed_slot_order,
)
from tests.motion_policy_decision_helpers import (  # noqa: E402
    MotionPolicyDecisionFixture,
    approved_review,
)


class ReviewedDrawOrderTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return MotionPolicyDecisionFixture(Path(temporary.name))

    def decision(self, fixture, depth, *, action="accept", reset=False):
        decisions = []
        for candidate in derive_motion_policy_candidates(
            fixture.foot, depth
        ).candidates:
            selected = action if candidate.kind == "depth_order" else "accept"
            payload = None
            if selected == "adjust":
                payload = {"final_front_slot": candidate.depth_slots[0]}
            decisions.append({
                "candidate_id": candidate.candidate_id,
                "action": selected,
                "reason_code": "reviewed-test-choice",
                "payload": payload,
            })
        return build_motion_policy_decision(
            fixture.foot,
            depth,
            review=approved_review(),
            decisions=decisions,
            root_release_keys=[],
            draw_order_loop_reset={"mode": "explicit", "approved": reset},
        ).document

    def test_accept_reject_unobservable_and_adjust_are_absolute(self):
        fixture = self.fixture()
        setup = ["leg", "face"]
        accepted = compile_reviewed_slot_order(
            self.decision(fixture, fixture.depth),
            fixture.foot, fixture.depth, setup,
        )
        self.assertEqual([
            {"tick": 0, "slot_ids": setup},
            {"tick": 66667, "slot_ids": ["face", "leg"]},
        ], accepted["keys"])
        for action in ("reject", "unobservable", "adjust"):
            with self.subTest(action=action):
                result = compile_reviewed_slot_order(
                    self.decision(fixture, fixture.depth, action=action),
                    fixture.foot, fixture.depth, setup,
                )
                self.assertEqual(
                    {"setup_slot_ids": setup,
                     "keys": [{"tick": 0, "slot_ids": setup}]},
                    result,
                )

    def test_same_tick_updates_are_atomic_and_pair_order_independent(self):
        fixture = self.fixture()
        setup = ["a", "b", "c", "d"]
        first = self.synthetic_depth(fixture.depth, [
            ("aa", ("a", "b"), "b", "a"),
            ("zz", ("c", "d"), "d", "c"),
        ])
        second = self.synthetic_depth(fixture.depth, [
            ("aa", ("c", "d"), "d", "c"),
            ("zz", ("a", "b"), "b", "a"),
        ])
        outputs = [compile_reviewed_slot_order(
            self.decision(fixture, depth), fixture.foot, depth, setup
        ) for depth in (first, second)]
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual([0, 66667], [row["tick"] for row in outputs[0]["keys"]])
        self.assertEqual(["b", "a", "d", "c"], outputs[0]["keys"][-1]["slot_ids"])

    def test_cycle_unknown_slot_and_repeated_event_fail_closed(self):
        fixture = self.fixture()
        cycle = self.synthetic_depth(fixture.depth, [
            ("ab", ("a", "b"), "b", "a"),
            ("ac", ("a", "c"), "c", None),
            ("bc", ("b", "c"), "c", "b"),
        ])
        with self.assertRaisesRegex(ReviewedDrawOrderError, "cycle"):
            compile_reviewed_slot_order(
                self.decision(fixture, cycle), fixture.foot, cycle,
                ["a", "b", "c"],
            )
        with self.assertRaises(ReviewedDrawOrderError):
            compile_reviewed_slot_order(
                self.decision(fixture, fixture.depth),
                fixture.foot, fixture.depth, ["face", "unknown"],
            )
        duplicated = deepcopy(fixture.depth)
        duplicated["pairs"][0]["events"].append(
            deepcopy(duplicated["pairs"][0]["events"][0])
        )
        duplicated["summary"]["event_count"] += 1
        with self.assertRaises(ReviewedDrawOrderError):
            compile_reviewed_slot_order(
                self.decision(fixture, fixture.depth),
                fixture.foot, duplicated, ["leg", "face"],
            )

    def test_tick_zero_switch_cannot_replace_setup_key(self):
        fixture = self.fixture()
        changed = deepcopy(fixture.depth)
        changed["hysteresis"]["minimum_hold_frames"] = 1
        pair = self.pair(
            changed, "face-vs-leg", ("face", "leg"), "face", "leg", 0
        )
        changed["pairs"] = [pair]
        changed["summary"] = {
            "status": "candidate_only", "pair_count": 1,
            "sample_count": len(pair["samples"]),
            "event_count": len(pair["events"]),
            "collapsed_sample_count": 0,
        }
        require_depth_order_candidates(changed)
        with self.assertRaises(ReviewedDrawOrderError):
            compile_reviewed_slot_order(
                self.decision(fixture, changed), fixture.foot, changed,
                ["leg", "face"],
            )

    def test_loop_reset_requires_authority_and_a_free_duration_tick(self):
        fixture = self.fixture()
        early = deepcopy(fixture.depth)
        early["hysteresis"]["minimum_hold_frames"] = 1
        early = self.synthetic_depth(early, [
            ("face-vs-leg", ("face", "leg"), "face", "leg"),
        ])
        early["timing"]["loop"] = True
        require_depth_order_candidates(early)
        with self.assertRaisesRegex(ReviewedDrawOrderError, "approval"):
            compile_reviewed_slot_order(
                self.decision(fixture, early), fixture.foot, early,
                ["leg", "face"],
            )
        result = compile_reviewed_slot_order(
            self.decision(fixture, early, reset=True),
            fixture.foot, early, ["leg", "face"],
        )
        self.assertEqual([0, 33333, 66667], [
            row["tick"] for row in result["keys"]
        ])
        self.assertEqual(["leg", "face"], result["keys"][-1]["slot_ids"])

        conflict = deepcopy(fixture.depth)
        conflict["timing"]["loop"] = True
        with self.assertRaisesRegex(ReviewedDrawOrderError, "conflicts"):
            compile_reviewed_slot_order(
                self.decision(fixture, conflict, reset=True),
                fixture.foot, conflict, ["leg", "face"],
            )

    def synthetic_depth(self, template, specs):
        document = deepcopy(template)
        pairs = [self.pair(document, *spec) for spec in specs]
        pairs.sort(key=lambda row: row["pair_id"])
        document["pairs"] = pairs
        document["summary"] = {
            "status": "candidate_only",
            "pair_count": len(pairs),
            "sample_count": sum(len(row["samples"]) for row in pairs),
            "event_count": sum(len(row["events"]) for row in pairs),
            "collapsed_sample_count": 0,
        }
        require_depth_order_candidates(document)
        return document

    def pair(
        self, document, pair_id, slots, setup_front, switch_front,
        switch_from_index=1,
    ):
        ticks = [0, 33333, 66667]
        sign = document["projection"]["front_score_sign"]
        scores = []
        for index, tick in enumerate(ticks):
            values = {slot: 0.0 for slot in slots}
            if switch_front is not None and index >= switch_from_index:
                values[switch_front] = 0.1
            scores.append({
                "source_frame_index": index, "tick": tick, "scores": values,
            })
        states, events = evaluate_depth_pair(
            scores,
            slot_ids=slots,
            setup_front_slot=setup_front,
            enter_threshold=document["hysteresis"]["enter_threshold"],
            exit_threshold=document["hysteresis"]["exit_threshold"],
            minimum_hold_frames=document["hysteresis"]["minimum_hold_frames"],
        )
        role = {slots[0]: "humanoid.head", slots[1]: "humanoid.leg.upper.left"}
        samples = []
        for source, state in zip(scores, states):
            score_rows = [{
                "slot_id": slot,
                "depth_role": role[slot],
                "midpoint_depth_root_relative_normalized":
                    quantize_depth_score(source["scores"][slot] / sign),
                "front_score": source["scores"][slot],
            } for slot in slots]
            samples.append({
                "source_frame_index": source["source_frame_index"],
                "tick": source["tick"],
                "scores": score_rows,
                "score_delta_first_minus_second": quantize_depth_score(
                    source["scores"][slots[0]] - source["scores"][slots[1]]
                ),
                **state,
            })
        return {
            "pair_id": pair_id,
            "slots": [{"slot_id": slot, "depth_role": role[slot]} for slot in slots],
            "setup_front_slot": setup_front,
            "samples": samples,
            "events": events,
        }


if __name__ == "__main__":
    unittest.main()
