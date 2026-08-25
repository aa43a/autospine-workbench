"""True 3D declared-channel BVH FK and signed-basis projection tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.bvh_fk import (  # noqa: E402
    BvhFkError,
    project_bvh_frames,
)
from autospine_workbench.bvh_parser import parse_bvh  # noqa: E402


STANDARD_ROOT = (
    "Xposition", "Yposition", "Zposition",
    "Zrotation", "Xrotation", "Yrotation",
)


def two_joint_bvh(
    frames, *, root_channels=STANDARD_ROOT, frame_time="0.0333333",
    child_offset=(0, 1, 1), end_offset=(1, 0, 0),
):
    rows = "\n".join(" ".join(str(value) for value in row) for row in frames)
    source = f"""HIERARCHY
ROOT Hips
{{
  OFFSET 0 0 0
  CHANNELS 6 {' '.join(root_channels)}
  JOINT Child
  {{
    OFFSET {' '.join(str(value) for value in child_offset)}
    CHANNELS 3 Xrotation Yrotation Zrotation
    End Site
    {{
      OFFSET {' '.join(str(value) for value in end_offset)}
    }}
  }}
}}
MOTION
Frames: {len(frames)}
Frame Time: {frame_time}
{rows}
"""
    return parse_bvh(source.encode("ascii"))


def chain_bvh(frames, *, frame_time="0.0333333"):
    rows = "\n".join(" ".join(str(value) for value in row) for row in frames)
    source = f"""HIERARCHY
ROOT Hips
{{
  OFFSET 0 0 0
  CHANNELS 6 {' '.join(STANDARD_ROOT)}
  JOINT Spine
  {{
    OFFSET 1 0 0
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT Chest
    {{
      OFFSET 1 0 0
      CHANNELS 3 Zrotation Xrotation Yrotation
      End Site
      {{
        OFFSET 1 0 0
      }}
    }}
  }}
}}
MOTION
Frames: {len(frames)}
Frame Time: {frame_time}
{rows}
"""
    return parse_bvh(source.encode("ascii"))


def bvh_map(*, loop=False, basis=None, reference=100.0, bones=None):
    return {
        "format": "autospine-bvh-map",
        "format_version": 1,
        "map_id": "test.explicit-v1",
        "clip": {"clip_id": "test.clip", "loop": loop},
        "basis": basis or {
            "screen_x": "+X", "screen_y": "+Y", "depth": "+Z",
            "rotation_convention": "bvh_declared_channel_postmultiply",
        },
        "root": {
            "joint_name": "Hips",
            "reference_length_source_units": reference,
            "translation_policy":
                "projected_frame0_delta_normalized_reference_length",
        },
        "bones": bones or [{
            "role": "humanoid.root",
            "joint_name": "Hips",
            "aim": {"kind": "joint", "joint_name": "Child"},
            "rotation_policy": "projected_setup_local_delta",
        }],
        "contact": {
            "enabled": False, "mode": "annotation_only", "interval": "half_open",
        },
    }


def segment(frame, role):
    return {value.role: value for value in frame.segments}[role]


class BvhFkTransformTests(unittest.TestCase):
    def test_mixed_xyz_euler_order_is_non_commutative_and_preserves_depth(self):
        first = two_joint_bvh([
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
            (0, 0, 0, 90, 90, 0, 0, 0, 0),
        ], root_channels=(
            "Xposition", "Yposition", "Zposition",
            "Xrotation", "Yrotation", "Zrotation",
        ))
        second = two_joint_bvh([
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
            (0, 0, 0, 90, 90, 0, 0, 0, 0),
        ], root_channels=(
            "Xposition", "Yposition", "Zposition",
            "Yrotation", "Xrotation", "Zrotation",
        ))

        first_child = dict(project_bvh_frames(first, bvh_map()).frames[1].joints)["Child"]
        second_child = dict(project_bvh_frames(second, bvh_map()).frames[1].joints)["Child"]

        self.assertEqual((1.0, 0.0, 1.0), first_child.world_xyz)
        self.assertEqual((1.0, -1.0, 0.0), second_child.world_xyz)
        self.assertNotEqual(first_child, second_child)

    def test_position_channels_are_postmultiplied_at_their_declared_location(self):
        channels = (
            "Zrotation", "Xposition", "Yposition", "Zposition",
            "Xrotation", "Yrotation",
        )
        document = two_joint_bvh([
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
            (90, 10, 0, 0, 0, 0, 0, 0, 0),
        ], root_channels=channels)
        output = project_bvh_frames(document, bvh_map(reference=100))

        root = dict(output.frames[1].joints)["Hips"]
        self.assertEqual((0.0, 10.0, 0.0), root.world_xyz)
        self.assertEqual((0.0, 0.1), output.frames[1].root_translation_normalized)

    def test_signed_basis_projects_world_xyz_and_root_frame0_delta_explicitly(self):
        document = two_joint_bvh([
            (10, 20, 30, 0, 0, 0, 0, 0, 0),
            (14, 14, 33, 0, 0, 0, 0, 0, 0),
        ])
        basis = {
            "screen_x": "-Z", "screen_y": "+X", "depth": "-Y",
            "rotation_convention": "bvh_declared_channel_postmultiply",
        }
        output = project_bvh_frames(
            document, bvh_map(basis=basis, reference=2)
        )
        setup = dict(output.frames[0].joints)["Hips"]
        moved = dict(output.frames[1].joints)["Hips"]

        self.assertEqual((-30.0, 10.0), setup.screen_xy)
        self.assertEqual(-20.0, setup.depth)
        self.assertEqual((-33.0, 14.0), moved.screen_xy)
        self.assertEqual((-1.5, 2.0), output.frames[1].root_translation_normalized)
        self.assertEqual(
            ("Hips", (10.0, 20.0, 30.0)), output.world_xyz_by_joint[0][0]
        )
        self.assertIsInstance(output.world_xyz_by_joint, tuple)

    def test_end_site_world_and_projected_points_are_exposed(self):
        document = two_joint_bvh([
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
        ])
        output = project_bvh_frames(document, bvh_map())
        end = dict(output.frames[0].end_sites)["Child"]

        self.assertEqual((1.0, 1.0, 1.0), end.world_xyz)
        self.assertEqual((1.0, 1.0), end.screen_xy)
        self.assertEqual(1.0, end.depth)


class BvhFkRotationContractTests(unittest.TestCase):
    def test_missing_canonical_parent_uses_world_change_without_nearest_guess(self):
        document = chain_bvh([
            (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            (0, 0, 0, 10, 0, 0, 0, 0, 0, 30, 0, 0),
        ])
        bones = [
            {
                "role": "humanoid.root", "joint_name": "Hips",
                "aim": {"kind": "joint", "joint_name": "Spine"},
                "rotation_policy": "projected_setup_local_delta",
            },
            {
                "role": "humanoid.spine.upper", "joint_name": "Chest",
                "aim": {"kind": "end_site"},
                "rotation_policy": "projected_setup_local_delta",
            },
        ]
        output = project_bvh_frames(document, bvh_map(bones=bones))
        upper = segment(output.frames[1], "humanoid.spine.upper")

        self.assertEqual(40.0, upper.projected_world_angle_deg)
        self.assertEqual(40.0, upper.setup_local_additive_delta_deg)
        self.assertIsNone(upper.delta_parent_role)

    def test_mapped_canonical_parent_change_is_subtracted_exactly(self):
        document = chain_bvh([
            (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            (0, 0, 0, 10, 0, 0, 20, 0, 0, 30, 0, 0),
        ])
        bones = [
            {
                "role": "humanoid.root", "joint_name": "Hips",
                "aim": {"kind": "joint", "joint_name": "Spine"},
                "rotation_policy": "projected_setup_local_delta",
            },
            {
                "role": "humanoid.spine.lower", "joint_name": "Spine",
                "aim": {"kind": "joint", "joint_name": "Chest"},
                "rotation_policy": "projected_setup_local_delta",
            },
            {
                "role": "humanoid.spine.upper", "joint_name": "Chest",
                "aim": {"kind": "end_site"},
                "rotation_policy": "projected_setup_local_delta",
            },
        ]
        output = project_bvh_frames(document, bvh_map(bones=bones))
        upper = segment(output.frames[1], "humanoid.spine.upper")

        self.assertEqual(60.0, upper.projected_world_angle_deg)
        self.assertEqual(30.0, upper.setup_local_additive_delta_deg)
        self.assertEqual("humanoid.spine.lower", upper.delta_parent_role)


class BvhFkTimeLoopAndSafetyTests(unittest.TestCase):
    def test_decimal_half_up_ticks_loop_endpoints_and_frozen_output(self):
        document = two_joint_bvh([
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
            (1, 0, 0, 0, 0, 0, 0, 0, 0),
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
        ], frame_time="0.0000015")
        output = project_bvh_frames(document, bvh_map(loop=True))

        self.assertEqual((0, 2, 3), tuple(frame.tick for frame in output.frames))
        self.assertEqual(3, output.duration_ticks)
        with self.assertRaises(FrozenInstanceError):
            output.duration_ticks = 9  # type: ignore[misc]
        with self.assertRaises(TypeError):
            output.frames[0].joints[0] = ()  # type: ignore[index]

    def test_loop_mismatch_fails_but_sub_precision_endpoint_noise_quantizes(self):
        mismatch = two_joint_bvh([
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
            (1, 0, 0, 0, 0, 0, 0, 0, 0),
            (2, 0, 0, 0, 0, 0, 0, 0, 0),
        ])
        with self.assertRaisesRegex(BvhFkError, "endpoints differ"):
            project_bvh_frames(mismatch, bvh_map(loop=True))

        quantized = two_joint_bvh([
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
            (1, 0, 0, 0, 0, 0, 0, 0, 0),
            (0.0000000000004, 0, 0, 0, 0, 0, 0, 0, 0),
        ])
        output = project_bvh_frames(quantized, bvh_map(loop=True))
        self.assertEqual(output.frames[0].joints, output.frames[-1].joints)

    def test_duplicate_ticks_degenerate_projection_and_bad_frames_fail_closed(self):
        baseline = two_joint_bvh([
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
        ])
        tiny_step = two_joint_bvh([
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
        ], frame_time="0.0000004")
        degenerate = two_joint_bvh([
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
        ], child_offset=(0, 0, 1))
        near_depth = two_joint_bvh([
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
        ], child_offset=(1e-10, 0, 1))
        one_frame = replace(baseline, frame_count=1, frames=baseline.frames[:1])
        wrong_count = replace(baseline, channel_count=baseline.channel_count + 1)
        short = replace(baseline, frames=(baseline.frames[0][:-1], baseline.frames[1]))
        nonfinite = replace(
            baseline,
            frames=((math.nan,) + baseline.frames[0][1:], baseline.frames[1]),
        )
        for document in (
            tiny_step, degenerate, near_depth, one_frame,
            wrong_count, short, nonfinite,
        ):
            with self.subTest(document=document):
                with self.assertRaises(BvhFkError):
                    project_bvh_frames(document, bvh_map())

    def test_frame_resource_limit_and_input_map_revalidation(self):
        document = two_joint_bvh([
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
        ])
        with patch("autospine_workbench.bvh_fk.MAX_BVH_FRAMES", 1):
            with self.assertRaises(BvhFkError):
                project_bvh_frames(document, bvh_map())

        invalid_map = deepcopy(bvh_map())
        invalid_map["basis"]["screen_y"] = "+X"
        with self.assertRaises(ValueError):
            project_bvh_frames(document, invalid_map)

    def test_numeric_outputs_are_quantized_to_twelve_decimal_places(self):
        document = two_joint_bvh([
            (0, 0, 0, 0, 0, 0, 0, 0, 0),
            (1.1234567890128, 0, 0, 0, 0, 0, 0, 0, 0),
        ])
        point = dict(project_bvh_frames(document, bvh_map()).frames[1].joints)["Hips"]
        self.assertEqual(1.123456789013, point.world_xyz[0])


if __name__ == "__main__":
    unittest.main()
