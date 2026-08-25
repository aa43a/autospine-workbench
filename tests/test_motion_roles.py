"""Canonical humanoid-v1 MotionIR role mapping tests."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_roles import (  # noqa: E402
    CANONICAL_BONE_ID_BY_ROLE,
    CANONICAL_BONE_ROLE_BY_ID,
    CANONICAL_BONE_ROLES,
    CANONICAL_IK_HANDLES,
    CONTACT_LIMBS,
)


class MotionRoleTests(unittest.TestCase):
    def test_exact_humanoid_v1_inventory_and_bidirectional_mapping(self):
        expected = {
            "humanoid.root": "root-pelvis",
            "humanoid.spine.lower": "pelvis-spine",
            "humanoid.spine.upper": "spine-chest",
            "humanoid.neck": "chest-neck",
            "humanoid.head": "neck-head",
        }
        for side in ("left", "right"):
            expected.update({
                f"humanoid.clavicle.{side}": f"chest-shoulder.{side}",
                f"humanoid.arm.upper.{side}": f"upper-arm.{side}",
                f"humanoid.arm.lower.{side}": f"forearm.{side}",
                f"humanoid.hip.{side}": f"pelvis-hip.{side}",
                f"humanoid.leg.upper.{side}": f"thigh.{side}",
                f"humanoid.leg.lower.{side}": f"calf.{side}",
            })
        self.assertEqual(17, len(expected))
        self.assertEqual(expected, dict(CANONICAL_BONE_ID_BY_ROLE))
        self.assertEqual(set(expected), CANONICAL_BONE_ROLES)
        self.assertEqual(
            {bone_id: role for role, bone_id in expected.items()},
            dict(CANONICAL_BONE_ROLE_BY_ID),
        )

    def test_role_maps_and_canonical_ik_contact_set_are_immutable(self):
        with self.assertRaises(TypeError):
            CANONICAL_BONE_ID_BY_ROLE["new"] = "bone"  # type: ignore[index]
        with self.assertRaises(TypeError):
            CANONICAL_BONE_ROLE_BY_ID["new"] = "role"  # type: ignore[index]
        self.assertEqual(
            ("arm.left", "arm.right", "leg.left", "leg.right"),
            CANONICAL_IK_HANDLES,
        )
        self.assertEqual(set(CANONICAL_IK_HANDLES), CONTACT_LIMBS)


if __name__ == "__main__":
    unittest.main()
