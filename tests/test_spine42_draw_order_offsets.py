"""Tests for full permutation to Spine 4.2 draworder offset conversion."""

from __future__ import annotations

from itertools import permutations
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.spine42_draw_order_offsets import (  # noqa: E402
    Spine42DrawOrderOffsetError,
    apply_spine42_draw_order_offsets,
    encode_spine42_draw_order_offsets,
)


class Spine42DrawOrderOffsetTests(unittest.TestCase):
    def test_setup_order_uses_reset_frame_without_offsets(self):
        setup = ("back", "body", "face")
        self.assertEqual([], encode_spine42_draw_order_offsets(setup, setup))
        self.assertEqual(setup, apply_spine42_draw_order_offsets(setup, []))

    def test_arbitrary_permutations_roundtrip_losslessly(self):
        setup = ("a", "b", "c", "d")
        targets = (
            ("d", "c", "b", "a"),
            ("b", "d", "a", "c"),
            ("a", "c", "d", "b"),
        )
        for target in targets:
            with self.subTest(target=target):
                offsets = encode_spine42_draw_order_offsets(setup, target)
                self.assertEqual(len(setup), len(offsets))
                self.assertEqual(
                    target, apply_spine42_draw_order_offsets(setup, offsets)
                )

    def test_every_permutation_through_seven_slots_roundtrips(self):
        for count in range(1, 8):
            setup = tuple(chr(ord("a") + index) for index in range(count))
            for target in permutations(setup):
                offsets = encode_spine42_draw_order_offsets(setup, target)
                self.assertEqual(
                    target, apply_spine42_draw_order_offsets(setup, offsets)
                )

    def test_offsets_are_canonical_setup_order_and_integer_deltas(self):
        setup, target = ("a", "b", "c"), ("c", "a", "b")
        self.assertEqual(
            [
                {"slot": "a", "offset": 1},
                {"slot": "b", "offset": 1},
                {"slot": "c", "offset": -2},
            ],
            encode_spine42_draw_order_offsets(setup, target),
        )

    def test_rejects_inventory_duplicate_order_and_destination_errors(self):
        cases = (
            lambda: encode_spine42_draw_order_offsets(("a", "b"), ("a", "c")),
            lambda: encode_spine42_draw_order_offsets(("a", "a"), ("a", "a")),
            lambda: apply_spine42_draw_order_offsets(
                ("a", "b"), [{"slot": "b", "offset": -1}, {"slot": "a", "offset": 1}]
            ),
            lambda: apply_spine42_draw_order_offsets(
                ("a", "b"), [{"slot": "a", "offset": 3}]
            ),
        )
        for call in cases:
            with self.assertRaises(Spine42DrawOrderOffsetError):
                call()


if __name__ == "__main__":
    unittest.main()
