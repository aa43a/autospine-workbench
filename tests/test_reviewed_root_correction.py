"""P9.4 reviewed root-correction projection tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import math
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_policy_decision import (  # noqa: E402
    build_motion_policy_decision,
)
from autospine_workbench.reviewed_root_correction import (  # noqa: E402
    ReviewedRootCorrectionError,
    compile_reviewed_root_correction,
)
from tests.motion_policy_decision_helpers import (  # noqa: E402
    MotionPolicyDecisionFixture,
    approved_review,
)


class ReviewedRootCorrectionTests(unittest.TestCase):
    def fixture(self, **kwargs) -> MotionPolicyDecisionFixture:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return MotionPolicyDecisionFixture(Path(temporary.name), **kwargs)

    def decision(self, fixture, decisions, *, releases=None, depth=None):
        selected_depth = fixture.depth if depth is None else depth
        return build_motion_policy_decision(
            fixture.foot,
            selected_depth,
            review=approved_review(),
            decisions=decisions,
            root_release_keys=[] if releases is None else releases,
            draw_order_loop_reset={"mode": "explicit", "approved": False},
        ).document

    def test_accept_adjust_reject_and_unobservable_projection(self):
        fixture = self.fixture()
        inventory = fixture.inventory()
        foot_ids = [
            row.candidate_id for row in inventory.candidates
            if row.kind == "foot_lock"
        ]
        by_tick = {
            row.tick: row.candidate_id for row in inventory.candidates
            if row.kind == "foot_lock"
        }
        constrained = [
            row for row in fixture.foot["samples"]
            if row["state"] != "unconstrained"
        ]
        self.assertGreaterEqual(len(foot_ids), 2)
        cases = (
            ("accept", None, constrained[1]["correction_candidate_px"]),
            ("adjust", {"final_correction_xy_px": [1.1234567896, -2.5]},
             [1.12345679, -2.5]),
            ("reject", None, [0.0, 0.0]),
            ("unobservable", None, [0.0, 0.0]),
        )
        selected = foot_ids[1]
        selected_tick = next(
            tick for tick, candidate_id in by_tick.items()
            if candidate_id == selected
        )
        for action, payload, expected in cases:
            decisions = fixture.accept_all()
            row = next(item for item in decisions
                       if item["candidate_id"] == selected)
            row.update({"action": action, "payload": payload})
            document = self.decision(fixture, decisions)
            keys = compile_reviewed_root_correction(
                document, fixture.foot, fixture.depth
            )
            actual = next(item for item in keys if item["tick"] == selected_tick)
            with self.subTest(action=action):
                self.assertEqual(expected, actual["correction_xy_px"])
                self.assertEqual("linear", actual["incoming_interpolation"])
                self.assertEqual(
                    [row["tick"] for row in fixture.foot["samples"]],
                    [row["tick"] for row in keys],
                )

    def test_explicit_release_replaces_unconstrained_default(self):
        fixture = self.fixture()
        tick = fixture.inventory().unconstrained_foot_ticks[0]
        release = {
            "tick": tick,
            "correction_xy_px": [3.1234567896, -4.0],
            "incoming_interpolation": "linear",
            "reason_code": "reviewed-release",
        }
        decision = self.decision(
            fixture, fixture.accept_all(), releases=[release]
        )
        keys = compile_reviewed_root_correction(
            decision, fixture.foot, fixture.depth
        )
        actual = next(row for row in keys if row["tick"] == tick)
        self.assertEqual([3.12345679, -4.0], actual["correction_xy_px"])
        self.assertEqual("linear", actual["incoming_interpolation"])

        stepped = deepcopy(release)
        stepped["incoming_interpolation"] = "stepped"
        unsupported = self.decision(
            fixture, fixture.accept_all(), releases=[stepped]
        )
        with self.assertRaisesRegex(
            ReviewedRootCorrectionError, "only supports linear"
        ):
            compile_reviewed_root_correction(
                unsupported, fixture.foot, fixture.depth
            )

    def test_loop_requires_zero_linear_start_and_duration(self):
        fixture = self.fixture()
        loop_depth = deepcopy(fixture.depth)
        loop_depth["timing"]["loop"] = True
        baseline = self.decision(
            fixture, fixture.accept_all(depth=loop_depth), depth=loop_depth
        )
        keys = compile_reviewed_root_correction(
            baseline, fixture.foot, loop_depth
        )
        self.assertEqual([0, loop_depth["timing"]["duration_ticks"]],
                         [keys[0]["tick"], keys[-1]["tick"]])

        end_tick = loop_depth["timing"]["duration_ticks"]
        releases = [{
            "tick": end_tick,
            "correction_xy_px": [1.0, 0.0],
            "incoming_interpolation": "linear",
            "reason_code": "bad-loop-release",
        }]
        changed = self.decision(
            fixture,
            fixture.accept_all(depth=loop_depth),
            releases=releases,
            depth=loop_depth,
        )
        with self.assertRaisesRegex(ReviewedRootCorrectionError, "endpoints"):
            compile_reviewed_root_correction(
                changed, fixture.foot, loop_depth
            )

        first_id = next(
            row.candidate_id for row in fixture.inventory(depth=loop_depth).candidates
            if row.kind == "foot_lock" and row.tick == 0
        )
        decisions = fixture.accept_all(depth=loop_depth)
        first = next(row for row in decisions
                     if row["candidate_id"] == first_id)
        first.update({
            "action": "adjust",
            "payload": {"final_correction_xy_px": [0.0, 1.0]},
        })
        changed = self.decision(fixture, decisions, depth=loop_depth)
        with self.assertRaisesRegex(ReviewedRootCorrectionError, "endpoints"):
            compile_reviewed_root_correction(
                changed, fixture.foot, loop_depth
            )

    def test_deterministic_isolated_output_and_bad_numbers_fail(self):
        fixture = self.fixture()
        decision = self.decision(fixture, fixture.accept_all())
        first = compile_reviewed_root_correction(
            decision, fixture.foot, fixture.depth
        )
        second = compile_reviewed_root_correction(
            deepcopy(decision), deepcopy(fixture.foot), deepcopy(fixture.depth)
        )
        self.assertEqual(first, second)
        first[0]["correction_xy_px"][0] = 99.0
        self.assertNotEqual(first, compile_reviewed_root_correction(
            decision, fixture.foot, fixture.depth
        ))

        inventory = fixture.inventory()
        candidate = next(row for row in inventory.candidates
                         if row.kind == "foot_lock")
        decisions = fixture.accept_all()
        row = next(item for item in decisions
                   if item["candidate_id"] == candidate.candidate_id)
        row.update({
            "action": "adjust",
            "payload": {"final_correction_xy_px": [math.nan, 0.0]},
        })
        invalid = {
            **decision,
            "decisions": decisions,
        }
        with self.assertRaises(ReviewedRootCorrectionError):
            compile_reviewed_root_correction(
                invalid, fixture.foot, fixture.depth
            )


if __name__ == "__main__":
    unittest.main()
