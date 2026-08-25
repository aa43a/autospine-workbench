"""Target-specific MotionInstance sampling and FK tests."""

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

from autospine_workbench.motion_instance_sampling import (  # noqa: E402
    MotionInstanceSamplingError,
    SAMPLE_STEP_TICKS,
    instance_sample_ticks,
    sample_instance_deltas,
    sample_instance_pose,
)
from tests.test_motion_instance_contract import (  # noqa: E402
    instance_fixture,
    target_fixture,
)


class MotionInstanceSamplingTests(unittest.TestCase):
    def setUp(self):
        self.target = target_fixture()
        self.instance = instance_fixture(self.target)

    def test_schedule_is_pinned_sorted_and_contains_every_authored_key(self):
        ticks = instance_sample_ticks(
            self.instance, target_profile=self.target
        )
        self.assertEqual(0, ticks[0])
        self.assertEqual(self.instance["timing"]["duration_ticks"], ticks[-1])
        self.assertEqual(tuple(sorted(set(ticks))), ticks)
        self.assertIn(SAMPLE_STEP_TICKS, ticks)
        authored = {
            key["tick"]
            for track in self.instance["tracks"] for key in track["keys"]
        }
        self.assertTrue(authored <= set(ticks))

    def test_midpoint_deltas_and_root_translation_are_linear(self):
        rotations, translation = sample_instance_deltas(
            self.instance, target_profile=self.target, tick=250_000
        )
        self.assertAlmostEqual(-10.0, rotations["forearm.left"])
        self.assertAlmostEqual(7.5, rotations["upper-arm.left"])
        self.assertEqual((0.75, -1.0), translation)

    def test_fk_applies_additive_rotation_and_translation_without_mutation(self):
        before = deepcopy((self.instance, self.target))
        pose = sample_instance_pose(
            self.instance, target_profile=self.target, tick=500_000
        )
        root_setup = self.target["bones"][0]["setup_local"]
        self.assertEqual(
            [root_setup["x"] + 1.5, root_setup["y"] - 2.0],
            pose["root-pelvis"]["origin_xy"],
        )
        forearm = next(
            row for row in self.target["bones"]
            if row["bone_id"] == "forearm.left"
        )
        upper = next(
            row for row in self.target["bones"]
            if row["bone_id"] == "upper-arm.left"
        )
        expected = (
            pose["chest-shoulder.left"]["rotation_deg"]
            + upper["setup_local"]["rotation_deg"] + 15.0
            + forearm["setup_local"]["rotation_deg"] - 20.0
        )
        self.assertAlmostEqual(expected, pose["forearm.left"]["rotation_deg"])
        self.assertEqual(before, (self.instance, self.target))

    def test_boundary_ticks_are_finite_and_loop_closes(self):
        start = sample_instance_pose(
            self.instance, target_profile=self.target, tick=0
        )
        end = sample_instance_pose(
            self.instance, target_profile=self.target,
            tick=self.instance["timing"]["duration_ticks"],
        )
        self.assertEqual(start, end)
        self.assertTrue(all(
            math.isfinite(value)
            for row in start.values()
            for field in ("origin_xy", "endpoint_xy")
            for value in row[field]
        ))

    def test_invalid_tick_instance_or_target_fails_closed(self):
        for tick in (-1, 1_000_001, 0.5, True):
            with self.subTest(tick=tick), self.assertRaises(
                MotionInstanceSamplingError
            ):
                sample_instance_pose(
                    self.instance, target_profile=self.target, tick=tick
                )
        changed = deepcopy(self.instance)
        changed["tracks"][0]["keys"][1]["value"] = math.nan
        with self.assertRaises(MotionInstanceSamplingError):
            instance_sample_ticks(changed, target_profile=self.target)
        stale = deepcopy(self.target)
        stale["reference_length"]["value_px"] += 1
        with self.assertRaises(MotionInstanceSamplingError):
            sample_instance_deltas(
                self.instance, target_profile=stale, tick=0
            )


if __name__ == "__main__":
    unittest.main()
