"""Numerical contract tests for analytic two-bone IK."""

from __future__ import annotations

from dataclasses import astuple
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.two_bone_ik import (  # noqa: E402
    TwoBoneIkError,
    solve_two_bone_ik,
)


class TwoBoneIkTests(unittest.TestCase):
    def test_reachable_target_honors_explicit_bend_direction(self) -> None:
        positive = self.solve(5, 5, (6, 0), "positive")
        negative = self.solve(5, 5, (6, 0), "negative")

        self.assertEqual("reachable", positive.reach_state)
        self.assert_point((3, 4), positive.elbow_xy)
        self.assert_point((3, -4), negative.elbow_xy)
        self.assert_point((6, 0), positive.resolved_target_xy)
        self.assertAlmostEqual(53.13010235415598, positive.proximal_rotation_deg)
        self.assertAlmostEqual(-106.26020470831196, positive.elbow_rotation_deg)
        self.assertGreater(self.cross_to_elbow(positive), 0.0)
        self.assertLess(self.cross_to_elbow(negative), 0.0)

    def test_targets_outside_both_reach_limits_are_clamped(self) -> None:
        too_far = self.solve(3, 2, (10, 0), "positive")
        self.assertEqual("unreachable_too_far", too_far.reach_state)
        self.assertEqual(10.0, too_far.requested_distance)
        self.assertEqual(5.0, too_far.resolved_distance)
        self.assert_point((3, 0), too_far.elbow_xy)
        self.assert_point((5, 0), too_far.resolved_target_xy)

        too_near = self.solve(5, 2, (1, 0), "negative")
        self.assertEqual("unreachable_too_near", too_near.reach_state)
        self.assertEqual(3.0, too_near.minimum_reach)
        self.assertEqual(3.0, too_near.resolved_distance)
        self.assert_point((5, 0), too_near.elbow_xy)
        self.assert_point((3, 0), too_near.resolved_target_xy)

    def test_reach_boundaries_remain_reachable(self) -> None:
        inner = self.solve(5, 2, (3, 0), "positive")
        outer = self.solve(5, 2, (7, 0), "negative")
        self.assertEqual("reachable", inner.reach_state)
        self.assertEqual("reachable", outer.reach_state)
        self.assert_point((5, 0), inner.elbow_xy)
        self.assert_point((5, 0), outer.elbow_xy)

    def test_mirror_flips_bend_sign_and_preserves_geometry(self) -> None:
        original = solve_two_bone_ik(
            (2, 1),
            proximal_length=5,
            distal_length=4,
            target_xy=(8, 5),
            bend_direction="positive",
        )
        mirrored = solve_two_bone_ik(
            (-2, 1),
            proximal_length=5,
            distal_length=4,
            target_xy=(-8, 5),
            bend_direction="negative",
        )
        self.assert_point((-original.elbow_xy[0], original.elbow_xy[1]), mirrored.elbow_xy)
        self.assert_point(
            (-original.resolved_target_xy[0], original.resolved_target_xy[1]),
            mirrored.resolved_target_xy,
        )
        self.assertEqual(original.reach_state, mirrored.reach_state)

    def test_coincident_target_uses_fallback_for_equal_lengths(self) -> None:
        positive = solve_two_bone_ik(
            (10, 20),
            proximal_length=2,
            distal_length=2,
            target_xy=(10, 20),
            bend_direction="positive",
            fallback_direction_xy=(2, 0),
        )
        negative = solve_two_bone_ik(
            (10, 20),
            proximal_length=2,
            distal_length=2,
            target_xy=(10, 20),
            bend_direction="negative",
            fallback_direction_xy=(2, 0),
        )
        self.assertTrue(positive.used_fallback_direction)
        self.assertEqual("reachable", positive.reach_state)
        self.assert_point((10, 22), positive.elbow_xy)
        self.assert_point((10, 18), negative.elbow_xy)
        self.assert_point((10, 20), positive.resolved_target_xy)

    def test_coincident_unbalanced_chain_clamps_along_fallback(self) -> None:
        solution = solve_two_bone_ik(
            (4, 5),
            proximal_length=5,
            distal_length=2,
            target_xy=(4, 5),
            bend_direction="positive",
            fallback_direction_xy=(0, 8),
        )
        self.assertEqual("unreachable_too_near", solution.reach_state)
        self.assert_point((4, 8), solution.resolved_target_xy)
        self.assert_point((4, 10), solution.elbow_xy)

    def test_zero_and_extremely_short_lengths_are_finite(self) -> None:
        cases = (
            self.solve(0, 0, (9, 4), "positive"),
            self.solve(0, 3, (3, 0), "positive"),
            self.solve(3, 0, (3, 0), "negative"),
            self.solve(1e-200, 1e-200, (1e-200, 0), "positive"),
        )
        self.assertEqual("unreachable_too_far", cases[0].reach_state)
        self.assert_point((0, 0), cases[0].resolved_target_xy)
        self.assert_point((0, 0), cases[1].elbow_xy)
        self.assert_point((3, 0), cases[2].elbow_xy)
        for solution in cases:
            self.assert_finite(solution)

    def test_geometry_invariants_hold_across_scales_and_directions(self) -> None:
        for scale in (1e-150, 1e-12, 1.0, 1e120):
            for angle_deg in (-173, -91, -7, 43, 179):
                angle = math.radians(angle_deg)
                target = (
                    4.25 * scale * math.cos(angle),
                    4.25 * scale * math.sin(angle),
                )
                for bend in ("positive", "negative"):
                    with self.subTest(scale=scale, angle=angle_deg, bend=bend):
                        solution = self.solve(3 * scale, 2 * scale, target, bend)
                        proximal_actual = math.dist(solution.root_xy, solution.elbow_xy)
                        distal_actual = math.dist(
                            solution.elbow_xy, solution.resolved_target_xy
                        )
                        self.assertTrue(
                            math.isclose(proximal_actual, 3 * scale, rel_tol=2e-14)
                        )
                        self.assertTrue(
                            math.isclose(distal_actual, 2 * scale, rel_tol=2e-14)
                        )
                        self.assert_finite(solution)

    def test_invalid_inputs_fail_closed(self) -> None:
        valid = {
            "root_xy": (0, 0),
            "proximal_length": 2,
            "distal_length": 2,
            "target_xy": (2, 0),
            "bend_direction": "positive",
        }
        cases = (
            {"root_xy": (math.nan, 0)},
            {"target_xy": (math.inf, 0)},
            {"target_xy": (1, 2, 3)},
            {"proximal_length": -1},
            {"proximal_length": True},
            {"distal_length": "2"},
            {"bend_direction": "clockwise"},
            {"fallback_direction_xy": (0, 0)},
            {"fallback_direction_xy": (math.inf, 0)},
        )
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(TwoBoneIkError):
                solve_two_bone_ik(**(valid | changes))

        with self.assertRaises(TwoBoneIkError):
            self.solve(1e308, 1e308, (0, 0), "positive")
        with self.assertRaises(TwoBoneIkError):
            solve_two_bone_ik(
                (1e308, 0),
                proximal_length=1,
                distal_length=1,
                target_xy=(-1e308, 0),
                bend_direction="positive",
            )

    def test_result_is_deterministic_and_all_numeric_fields_are_finite(self) -> None:
        args = {
            "root_xy": (11.25, -7.5),
            "proximal_length": 8.125,
            "distal_length": 4.75,
            "target_xy": (-2.5, 5.125),
            "bend_direction": "negative",
            "fallback_direction_xy": (0.25, 3.5),
        }
        first = solve_two_bone_ik(**args)
        for _ in range(10):
            self.assertEqual(first, solve_two_bone_ik(**args))
        self.assert_finite(first)

    @staticmethod
    def solve(proximal, distal, target, bend):
        return solve_two_bone_ik(
            (0, 0),
            proximal_length=proximal,
            distal_length=distal,
            target_xy=target,
            bend_direction=bend,
        )

    @staticmethod
    def cross_to_elbow(solution) -> float:
        direction = solution.aim_direction_xy
        elbow = (
            solution.elbow_xy[0] - solution.root_xy[0],
            solution.elbow_xy[1] - solution.root_xy[1],
        )
        return direction[0] * elbow[1] - direction[1] * elbow[0]

    def assert_point(self, expected, actual) -> None:
        self.assertAlmostEqual(float(expected[0]), float(actual[0]), places=12)
        self.assertAlmostEqual(float(expected[1]), float(actual[1]), places=12)

    def assert_finite(self, solution) -> None:
        for value in astuple(solution):
            values = value if isinstance(value, tuple) else (value,)
            for item in values:
                if isinstance(item, float):
                    self.assertTrue(math.isfinite(item), repr(solution))


if __name__ == "__main__":
    unittest.main()
