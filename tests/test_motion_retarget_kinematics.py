"""Animated-ancestor sampling and analytic IK retarget tests."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_builtin import build_builtin_motion  # noqa: E402
from autospine_workbench.motion_retarget_kinematics import (  # noqa: E402
    MotionRetargetKinematicsError,
    sample_motion_pose,
    solve_motion_ik_track,
)
from autospine_workbench.motion_target_profile import (  # noqa: E402
    compile_motion_target_profile,
)
from tests.test_motion_target_profile import pair  # noqa: E402


def profile():
    return compile_motion_target_profile(*pair()).document


class MotionRetargetKinematicsTests(unittest.TestCase):
    def test_wave_samples_animated_clavicle_before_solving_ik(self) -> None:
        motion = build_builtin_motion("wave.left").document
        target = profile()
        solved = solve_motion_ik_track(motion, target, "arm.left")
        handle = next(item for item in target["ik_handles"] if item["id"] == "arm.left")

        self.assertEqual("upper-arm.left", solved.proximal_bone_id)
        self.assertEqual("forearm.left", solved.distal_bone_id)
        self.assertEqual([0, 400_000, 800_000, 1_200_000, 1_600_000, 2_000_000], [
            item.tick for item in solved.samples
        ])
        self.assertAlmostEqual(0.0, solved.samples[0].proximal_rotation_delta_deg)
        self.assertAlmostEqual(0.0, solved.samples[0].distal_rotation_delta_deg)
        animated = sample_motion_pose(motion, target, 400_000)
        self.assertNotEqual(
            tuple(handle["root_xy"]),
            tuple(animated["upper-arm.left"]["origin_xy"]),
        )
        self.assertTrue(all(item.reach_state == "reachable" for item in solved.samples))

    def test_every_reachable_solution_reconstructs_requested_effector(self) -> None:
        motion = build_builtin_motion("wave.left").document
        target = profile()
        solved = solve_motion_ik_track(motion, target, "arm.left")
        handle = next(item for item in target["ik_handles"] if item["id"] == "arm.left")
        distal_setup = handle["setup_angles_deg"]["distal_local"]
        for sample in solved.samples:
            pose = sample_motion_pose(motion, target, sample.tick)
            base = pose[solved.proximal_bone_id]["rotation_deg"]
            proximal = math.radians(base + sample.proximal_rotation_delta_deg)
            distal = math.radians(
                base + sample.proximal_rotation_delta_deg
                + distal_setup + sample.distal_rotation_delta_deg
            )
            endpoint = (
                sample.root_xy[0]
                + math.cos(proximal) * handle["proximal_length_px"]
                + math.cos(distal) * handle["distal_length_px"],
                sample.root_xy[1]
                + math.sin(proximal) * handle["proximal_length_px"]
                + math.sin(distal) * handle["distal_length_px"],
            )
            with self.subTest(tick=sample.tick):
                self.assertAlmostEqual(sample.requested_target_xy[0], endpoint[0], places=8)
                self.assertAlmostEqual(sample.requested_target_xy[1], endpoint[1], places=8)

    def test_setup_sentinel_preserves_chain_under_animated_ancestor(self) -> None:
        motion = build_builtin_motion("wave.left").document
        track = next(item for item in motion["tracks"] if item["target_kind"] == "ik_handle")
        track["keys"][1]["value"] = "setup"
        solved = solve_motion_ik_track(motion, profile(), "arm.left")
        sample = solved.samples[1]
        self.assertEqual("setup", sample.source_value)
        self.assertAlmostEqual(0.0, sample.proximal_rotation_delta_deg, places=9)
        self.assertAlmostEqual(0.0, sample.distal_rotation_delta_deg, places=9)

    def test_idle_root_translation_uses_target_reference_length(self) -> None:
        motion = build_builtin_motion("idle").document
        target = profile()
        setup_root = target["bones"][0]["setup_local"]
        world = sample_motion_pose(motion, target, 1_000_000)
        reference = target["reference_length"]["value_px"]
        self.assertAlmostEqual(setup_root["x"], world["root-pelvis"]["origin_xy"][0])
        self.assertAlmostEqual(
            setup_root["y"] - 0.005 * reference,
            world["root-pelvis"]["origin_xy"][1],
        )

    def test_unreachable_key_is_reported_without_silent_clamping(self) -> None:
        motion = build_builtin_motion("wave.left").document
        track = next(item for item in motion["tracks"] if item["target_kind"] == "ik_handle")
        track["keys"][2]["value"] = [2.0, 2.0]
        solved = solve_motion_ik_track(motion, profile(), "arm.left")
        sample = solved.samples[2]
        self.assertEqual("unreachable_too_far", sample.reach_state)
        self.assertNotEqual(sample.requested_target_xy, sample.resolved_target_xy)

    def test_missing_handle_and_invalid_profile_fail_closed(self) -> None:
        motion = build_builtin_motion("wave.left").document
        with self.assertRaises(MotionRetargetKinematicsError):
            solve_motion_ik_track(motion, profile(), "arm.right")
        changed = deepcopy(profile())
        changed["reference_length"]["value_px"] = math.nan
        with self.assertRaises(MotionRetargetKinematicsError):
            solve_motion_ik_track(motion, changed, "arm.left")


if __name__ == "__main__":
    unittest.main()
