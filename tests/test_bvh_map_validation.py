"""Contract tests for explicit, guess-free BVH maps."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None

from autospine_workbench.bvh_map_validation import (  # noqa: E402
    BvhMapValidationError,
    require_bvh_map,
)
from autospine_workbench.bvh_parser import BvhDocument, BvhJoint  # noqa: E402


def _joint(name, parent, *, end=False):
    return BvhJoint(
        name=name,
        parent_index=parent,
        offset=(0.0, 1.0, 0.0),
        channels=("Xrotation", "Yrotation", "Zrotation"),
        rotation_order=("Xrotation", "Yrotation", "Zrotation"),
        end_site_offset=(0.0, 1.0, 0.0) if end else None,
    )


def source_bvh():
    joints = (
        _joint("Hips", None),
        _joint("Spine", 0),
        _joint("Chest", 1, end=True),
        _joint("LeftUpLeg", 0),
        _joint("LeftLeg", 3),
        _joint("LeftFoot", 4, end=True),
        _joint("RightUpLeg", 0),
        _joint("RightLeg", 6),
        _joint("RightFoot", 7, end=True),
    )
    return BvhDocument(
        source_sha256="0" * 64,
        source_byte_length=1,
        joints=joints,
        frame_count=0,
        frame_time_seconds=1 / 30,
        channel_count=0,
        frames=(),
    )


def bone(role, joint, *, aim_joint=None):
    aim = (
        {"kind": "joint", "joint_name": aim_joint}
        if aim_joint else {"kind": "end_site"}
    )
    return {
        "role": role,
        "joint_name": joint,
        "aim": aim,
        "rotation_policy": "projected_setup_local_delta",
    }


def mapping():
    return {
        "format": "autospine-bvh-map",
        "format_version": 1,
        "map_id": "mixamo.humanoid.front-v1",
        "clip": {"clip_id": "walk.front", "loop": True},
        "basis": {
            "screen_x": "+X",
            "screen_y": "-Y",
            "depth": "+Z",
            "rotation_convention": "bvh_declared_channel_postmultiply",
        },
        "root": {
            "joint_name": "Hips",
            "reference_length_source_units": 100.0,
            "translation_policy":
                "projected_frame0_delta_normalized_reference_length",
        },
        "bones": [
            bone("humanoid.root", "Hips", aim_joint="Spine"),
            bone("humanoid.spine.lower", "Spine", aim_joint="Chest"),
            bone("humanoid.spine.upper", "Chest"),
            bone("humanoid.leg.upper.left", "LeftUpLeg", aim_joint="LeftLeg"),
            bone("humanoid.leg.lower.left", "LeftLeg", aim_joint="LeftFoot"),
            bone("humanoid.leg.upper.right", "RightUpLeg", aim_joint="RightLeg"),
            bone("humanoid.leg.lower.right", "RightLeg", aim_joint="RightFoot"),
        ],
        "contact": {
            "enabled": True,
            "feet": [
                {"limb": "leg.left", "foot_joint_name": "LeftFoot"},
                {"limb": "leg.right", "foot_joint_name": "RightFoot"},
            ],
            "floor_height_source_units": 0.0,
            "height_threshold_source_units": 2.5,
            "speed_threshold_source_units_per_second": 4.0,
            "minimum_frames": 2,
            "gap_frames": 1,
            "height_policy":
                "absolute_signed_basis_screen_y_distance_to_floor",
            "speed_policy": "source_world_3d_euclidean",
            "mode": "annotation_only",
            "interval": "half_open",
        },
    }


class BvhMapSuccessTests(unittest.TestCase):
    def test_valid_map_passes_standalone_and_source_cross_validation(self):
        value = mapping()
        before = deepcopy(value)
        require_bvh_map(value)
        require_bvh_map(value, bvh=source_bvh())
        self.assertEqual(before, value)

    def test_contact_can_be_explicitly_disabled_without_threshold_placeholders(self):
        value = mapping()
        value["contact"] = {
            "enabled": False,
            "mode": "annotation_only",
            "interval": "half_open",
        }
        require_bvh_map(value, bvh=source_bvh())

    @unittest.skipUnless(Draft202012Validator, "jsonschema is optional")
    def test_json_schema_accepts_the_semantic_fixture_and_rejects_unknowns(self):
        schema = json.loads((ROOT / "schemas" / "bvh-map-v1.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        self.assertEqual([], list(validator.iter_errors(mapping())))
        changed = mapping()
        changed["basis"]["guessed_up"] = True
        self.assertTrue(list(validator.iter_errors(changed)))


class BvhMapRejectionTests(unittest.TestCase):
    def assert_invalid(self, value, *, bvh=None, message=None):
        context = (
            self.assertRaisesRegex(BvhMapValidationError, message)
            if message else self.assertRaises(BvhMapValidationError)
        )
        with context:
            require_bvh_map(value, bvh=bvh)

    def test_basis_requires_three_distinct_explicit_signed_source_axes(self):
        mutations = (
            lambda value: value["basis"].update(screen_x="X"),
            lambda value: value["basis"].update(screen_y="-X"),
            lambda value: value["basis"].update(
                rotation_convention="intrinsic_xyz_guess"
            ),
        )
        for mutate in mutations:
            value = mapping()
            mutate(value)
            with self.subTest(basis=value["basis"]):
                self.assert_invalid(value)

    def test_joint_root_aim_end_site_and_contact_tampering_fail_against_bvh(self):
        source = source_bvh()
        cases = []
        wrong_root = mapping()
        wrong_root["root"]["joint_name"] = "Spine"
        wrong_root["bones"][0]["joint_name"] = "Spine"
        wrong_root["bones"][1]["joint_name"] = "Hips"
        cases.append((wrong_root, source))
        missing_joint = mapping()
        missing_joint["bones"][2]["joint_name"] = "Missing"
        cases.append((missing_joint, source))
        missing_aim = mapping()
        missing_aim["bones"][0]["aim"]["joint_name"] = "Missing"
        cases.append((missing_aim, source))
        no_end = replace(
            source,
            joints=source.joints[:2] +
                (replace(source.joints[2], end_site_offset=None),) +
                source.joints[3:],
        )
        cases.append((mapping(), no_end))
        missing_foot = mapping()
        missing_foot["contact"]["feet"][0]["foot_joint_name"] = "ToeMissing"
        cases.append((missing_foot, source))
        for value, document in cases:
            with self.subTest(value=value):
                self.assert_invalid(value, bvh=document)

    def test_unknown_nonfinite_boolean_and_resource_values_fail_closed(self):
        mutations = (
            lambda value: value.update(extra=True),
            lambda value: value["clip"].update(loop=1),
            lambda value: value["root"].update(
                reference_length_source_units=math.nan
            ),
            lambda value: value["root"].update(
                reference_length_source_units=True
            ),
            lambda value: value["contact"].update(
                speed_threshold_source_units_per_second=math.inf
            ),
            lambda value: value["contact"].update(minimum_frames=True),
            lambda value: value["contact"].update(gap_frames=20_001),
            lambda value: value.update(bones=tuple(value["bones"])),
        )
        for mutate in mutations:
            value = mapping()
            mutate(value)
            with self.subTest(value=value):
                self.assert_invalid(value)

    def test_bones_require_canonical_sort_unique_roles_joints_and_aims(self):
        mutations = (
            lambda value: value["bones"].__setitem__(
                slice(0, 2), list(reversed(value["bones"][:2]))
            ),
            lambda value: value["bones"][1].update(role="humanoid.root"),
            lambda value: value["bones"][1].update(joint_name="Hips"),
            lambda value: value["bones"][0]["aim"].update(joint_name="Chest"),
            lambda value: value["bones"].pop(0),
        )
        for mutate in mutations:
            value = mapping()
            mutate(value)
            with self.subTest(bones=value["bones"]):
                self.assert_invalid(value)

    def test_source_aim_role_and_hierarchy_topology_are_not_inferred(self):
        source = source_bvh()
        sibling_aim = mapping()
        sibling_aim["bones"][3]["aim"]["joint_name"] = "RightUpLeg"
        self.assert_invalid(sibling_aim, bvh=source, message="aim must descend")

        crossed_role = mapping()
        crossed_role["bones"][4] = bone(
            "humanoid.leg.lower.left", "RightFoot"
        )
        self.assert_invalid(crossed_role, bvh=source, message="role topology")

        invalid_parent = replace(
            source,
            joints=source.joints[:7] +
                (replace(source.joints[7], parent_index=99),) +
                source.joints[8:],
        )
        self.assert_invalid(mapping(), bvh=invalid_parent, message="hierarchy")

    def test_contact_is_leg_only_sorted_unique_explicit_and_topology_bound(self):
        cases = []
        reversed_feet = mapping()
        reversed_feet["contact"]["feet"].reverse()
        cases.append((reversed_feet, None))
        arm = mapping()
        arm["contact"]["feet"][0]["limb"] = "arm.left"
        cases.append((arm, None))
        duplicate = mapping()
        duplicate["contact"]["feet"][1]["foot_joint_name"] = "LeftFoot"
        cases.append((duplicate, None))
        guessed_policy = mapping()
        guessed_policy["contact"]["height_policy"] = "infer_floor"
        cases.append((guessed_policy, None))
        crossed = mapping()
        crossed["contact"]["feet"] = [
            {"limb": "leg.left", "foot_joint_name": "RightFoot"}
        ]
        cases.append((crossed, source_bvh()))
        for value, document in cases:
            with self.subTest(contact=value["contact"]):
                self.assert_invalid(value, bvh=document)

    def test_joint_names_are_bounded_ascii_bvh_tokens(self):
        for name in ("Left Foot", "关节", "{" + "x" * 3, "x" * 257):
            value = mapping()
            value["bones"][3]["joint_name"] = name
            with self.subTest(name=name):
                self.assert_invalid(value)


if __name__ == "__main__":
    unittest.main()
