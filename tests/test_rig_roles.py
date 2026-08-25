"""Canonical humanoid-v1 region attachment role mapping."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.rig_roles import region_bone_for_role  # noqa: E402


class RegionBoneRoleTests(unittest.TestCase):
    def test_center_body_and_head_roles_use_existing_skeleton_bones(self) -> None:
        self.assertEqual("neck-head", region_bone_for_role("face.base", "center"))
        self.assertEqual("neck-head", region_bone_for_role("hair.front", "center"))
        self.assertEqual("chest-neck", region_bone_for_role("body.neck", "center"))
        self.assertEqual("spine-chest", region_bone_for_role("body.torso", "center"))
        self.assertEqual("pelvis-spine", region_bone_for_role("body.pelvis", "center"))

    def test_limb_roles_choose_the_deforming_segment_for_character_side(self) -> None:
        cases = {
            ("body.arm.upper", "left"): "upper-arm.left",
            ("body.arm.lower", "right"): "forearm.right",
            ("body.hand", "left"): "forearm.left",
            ("body.leg.upper", "right"): "thigh.right",
            ("body.leg.lower", "left"): "calf.left",
            ("body.foot", "right"): "calf.right",
        }
        for (role, side), expected in cases.items():
            with self.subTest(role=role, side=side):
                self.assertEqual(expected, region_bone_for_role(role, side))

    def test_bilateral_or_unknown_deforming_layers_remain_unresolved(self) -> None:
        for role in ("body.hand", "body.foot", "body.arm", "body.leg"):
            with self.subTest(role=role):
                self.assertIsNone(region_bone_for_role(role, "bilateral"))
                self.assertIsNone(region_bone_for_role(role, "unknown"))

    def test_general_accessory_uses_root_while_unknown_semantics_fail_closed(self) -> None:
        self.assertEqual(
            "root-pelvis", region_bone_for_role("accessory.object", "unknown")
        )
        self.assertIsNone(region_bone_for_role("unclassified.layer", "unknown"))


if __name__ == "__main__":
    unittest.main()
