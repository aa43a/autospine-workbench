"""Fail-closed tests for standard and Kimodo-style BVH logical roots."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.bvh_motion_root import (  # noqa: E402
    BvhMotionRootError,
    SINGLE_ROOT_PROFILE,
    ZERO_WRAPPER_PROFILE,
    require_bvh_motion_root,
)
from autospine_workbench.bvh_parser import parse_bvh  # noqa: E402
from tests.fixtures.kimodo_soma77_fixture import (  # noqa: E402
    ROOT_CHANNELS,
    build_soma77_bvh,
)


class BvhMotionRootTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kimodo = parse_bvh(build_soma77_bvh())

    def test_standard_root_and_zero_wrapper_profiles_are_explicit(self):
        standard_raw = (ROOT / "tests" / "fixtures" / "minimal_motion.bvh").read_bytes()
        standard = require_bvh_motion_root(parse_bvh(standard_raw), "Hips")
        logical = require_bvh_motion_root(self.kimodo, "Hips")

        self.assertEqual((0, None, SINGLE_ROOT_PROFILE), (
            standard.joint_index, standard.wrapper_index, standard.profile,
        ))
        self.assertEqual((1, 0, ZERO_WRAPPER_PROFILE), (
            logical.joint_index, logical.wrapper_index, logical.profile,
        ))
        with self.assertRaises(FrozenInstanceError):
            logical.joint_index = 0  # type: ignore[misc]

    def test_wrapper_must_be_zero_offset_single_child_and_zero_motion(self):
        joints = list(self.kimodo.joints)
        bad_offset = replace(
            self.kimodo, joints=(replace(joints[0], offset=(1.0, 0.0, 0.0)), *joints[1:])
        )
        right_leg = next(
            index for index, joint in enumerate(joints) if joint.name == "RightLeg"
        )
        sibling_joints = list(joints)
        sibling_joints[right_leg] = replace(joints[right_leg], parent_index=0)
        sibling = replace(self.kimodo, joints=tuple(sibling_joints))
        frames = list(self.kimodo.frames)
        frames[1] = (1.0,) + frames[1][1:]
        moving = replace(self.kimodo, frames=tuple(frames))

        for document in (bad_offset, sibling, moving):
            with self.subTest(document=document), self.assertRaises(
                BvhMotionRootError
            ):
                require_bvh_motion_root(document, "Hips")

    def test_only_root_and_one_logical_child_may_have_position_channels(self):
        joints = list(self.kimodo.joints)
        spine = next(
            index for index, joint in enumerate(joints) if joint.name == "Spine1"
        )
        joints[spine] = replace(
            joints[spine], channels=ROOT_CHANNELS,
            rotation_order=("Zrotation", "Yrotation", "Xrotation"),
        )
        extra_six_dof = replace(self.kimodo, joints=tuple(joints))

        with self.assertRaises(BvhMotionRootError):
            require_bvh_motion_root(extra_six_dof, "Hips")
        with self.assertRaises(BvhMotionRootError):
            require_bvh_motion_root(self.kimodo, "Spine1")
        with self.assertRaises(BvhMotionRootError):
            require_bvh_motion_root(self.kimodo, "Root")


if __name__ == "__main__":
    unittest.main()
