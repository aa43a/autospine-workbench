"""Setup-local rotation adapter tests for P4 analytic IK."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.ik_setup_local import solve_setup_local_ik  # noqa: E402


class SetupLocalIkTests(unittest.TestCase):
    def test_setup_target_reconstructs_hinge_and_zero_deltas(self) -> None:
        root = (12.0, -4.0)
        proximal_length, distal_length = 5.0, 4.0
        proximal_world, distal_local = 30.0, -60.0
        hinge = self.endpoint(root, proximal_length, proximal_world)
        target = self.endpoint(
            hinge, distal_length, proximal_world + distal_local
        )
        cross = self.cross(root, target, hinge)

        solved = solve_setup_local_ik(
            root,
            proximal_length=proximal_length,
            distal_length=distal_length,
            target_xy=target,
            bend_direction="positive" if cross > 0 else "negative",
            fallback_direction_xy=(target[0] - root[0], target[1] - root[1]),
            setup_proximal_world_rotation_deg=proximal_world,
            setup_distal_local_rotation_deg=distal_local,
        )

        self.assert_point(hinge, solved.world.elbow_xy)
        self.assert_point(target, solved.world.resolved_target_xy)
        self.assertAlmostEqual(0.0, solved.proximal_rotation_delta_deg, places=12)
        self.assertAlmostEqual(0.0, solved.distal_rotation_delta_deg, places=12)

    def test_moved_and_unreachable_targets_return_finite_local_deltas(self) -> None:
        cases = ((4.0, 3.0), (100.0, 0.0), (0.0, 0.0))
        for target in cases:
            with self.subTest(target=target):
                solved = solve_setup_local_ik(
                    (0.0, 0.0),
                    proximal_length=5.0,
                    distal_length=3.0,
                    target_xy=target,
                    bend_direction="positive",
                    fallback_direction_xy=(1.0, 0.0),
                    setup_proximal_world_rotation_deg=20.0,
                    setup_distal_local_rotation_deg=-40.0,
                )
                self.assertTrue(math.isfinite(solved.proximal_rotation_delta_deg))
                self.assertTrue(math.isfinite(solved.distal_rotation_delta_deg))

    def test_angle_wrap_is_setup_local_and_deterministic(self) -> None:
        args = {
            "root_xy": (0.0, 0.0),
            "proximal_length": 5.0,
            "distal_length": 5.0,
            "target_xy": (-8.0, -1.0),
            "bend_direction": "negative",
            "fallback_direction_xy": (-1.0, 0.0),
            "setup_proximal_world_rotation_deg": 181.0,
            "setup_distal_local_rotation_deg": -181.0,
        }
        first = solve_setup_local_ik(**args)
        self.assertEqual(first, solve_setup_local_ik(**args))
        self.assertGreaterEqual(first.proximal_rotation_delta_deg, -180.0)
        self.assertLess(first.proximal_rotation_delta_deg, 180.0)
        self.assertGreaterEqual(first.distal_rotation_delta_deg, -180.0)
        self.assertLess(first.distal_rotation_delta_deg, 180.0)

    def test_non_finite_setup_angles_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "finite"):
            solve_setup_local_ik(
                (0, 0),
                proximal_length=2,
                distal_length=2,
                target_xy=(2, 0),
                bend_direction="positive",
                fallback_direction_xy=(1, 0),
                setup_proximal_world_rotation_deg=float("nan"),
                setup_distal_local_rotation_deg=0,
            )

    @staticmethod
    def endpoint(origin, length, rotation_deg):
        angle = math.radians(rotation_deg)
        return (
            origin[0] + length * math.cos(angle),
            origin[1] + length * math.sin(angle),
        )

    @staticmethod
    def cross(root, target, elbow):
        return (
            (target[0] - root[0]) * (elbow[1] - root[1])
            - (target[1] - root[1]) * (elbow[0] - root[0])
        )

    def assert_point(self, expected, actual):
        self.assertAlmostEqual(expected[0], actual[0], places=12)
        self.assertAlmostEqual(expected[1], actual[1], places=12)


if __name__ == "__main__":
    unittest.main()
