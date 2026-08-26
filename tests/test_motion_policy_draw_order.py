"""Tests for reviewed pair-relation merging into full slot permutations."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_policy_draw_order import (  # noqa: E402
    MotionPolicyDrawOrderError,
    merge_draw_order_relations,
    pair_relation,
)


class MotionPolicyDrawOrderTests(unittest.TestCase):
    def test_setup_order_is_the_deterministic_tie_break(self):
        setup = ("back", "body", "arm", "face")
        relations = [pair_relation(("arm", "face"), "arm")]
        self.assertEqual(
            ("back", "body", "face", "arm"),
            merge_draw_order_relations(setup, relations),
        )

    def test_multiple_relations_form_one_full_permutation(self):
        setup = ("a", "b", "c", "d")
        relations = [
            {"back_slot": "d", "front_slot": "a"},
            {"back_slot": "c", "front_slot": "b"},
            {"back_slot": "b", "front_slot": "a"},
        ]
        result = merge_draw_order_relations(setup, relations)
        self.assertEqual(set(setup), set(result))
        self.assertLess(result.index("d"), result.index("a"))
        self.assertLess(result.index("c"), result.index("b"))
        self.assertLess(result.index("b"), result.index("a"))

    def test_cycle_duplicate_unknown_and_bad_pair_fail_closed(self):
        setup = ("a", "b", "c")
        cases = (
            lambda: merge_draw_order_relations(setup, [
                {"back_slot": "a", "front_slot": "b"},
                {"back_slot": "b", "front_slot": "c"},
                {"back_slot": "c", "front_slot": "a"},
            ]),
            lambda: merge_draw_order_relations(setup, [
                {"back_slot": "a", "front_slot": "b"},
                {"back_slot": "a", "front_slot": "b"},
            ]),
            lambda: merge_draw_order_relations(
                setup, [{"back_slot": "a", "front_slot": "missing"}]
            ),
            lambda: pair_relation(("a", "a"), "a"),
        )
        for call in cases:
            with self.assertRaises(MotionPolicyDrawOrderError):
                call()


if __name__ == "__main__":
    unittest.main()
