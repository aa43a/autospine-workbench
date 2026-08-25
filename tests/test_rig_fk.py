"""Setup-pose bone compilation and FK math tests."""

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

from autospine_workbench.rig_fk import (  # noqa: E402
    RigFkError,
    compile_setup_bones,
    evaluate_world_setup,
    local_to_world_point,
    world_to_local_point,
)


def skeleton_fixture() -> dict:
    return {
        "joints": [
            {"id": "a", "x": 10, "y": 20, "confidence": 0.9, "decision_kind": "manual_absolute"},
            {"id": "b", "x": 10, "y": 30, "confidence": 0.8, "decision_kind": "manual_absolute"},
            {"id": "c", "x": 0, "y": 30, "confidence": 0.7, "decision_kind": "manual_absolute"},
        ],
        "bones": [
            {
                "id": "child",
                "parent_id": "parent",
                "start_joint_id": "b",
                "end_joint_id": "c",
            },
            {
                "id": "parent",
                "parent_id": None,
                "start_joint_id": "a",
                "end_joint_id": "b",
            },
        ],
    }


class RigFkTests(unittest.TestCase):
    def test_rotated_parent_compiles_in_stable_topological_order(self) -> None:
        bones = compile_setup_bones(skeleton_fixture())
        self.assertEqual(["parent", "child"], [bone["id"] for bone in bones])
        self.assertAlmostEqual(90.0, bones[0]["setup"]["rotation_deg"])
        self.assertAlmostEqual(10.0, bones[1]["setup"]["x"])
        self.assertAlmostEqual(0.0, bones[1]["setup"]["y"])
        self.assertAlmostEqual(90.0, bones[1]["setup"]["rotation_deg"])

        worlds = evaluate_world_setup(bones)
        self.assert_point([10, 20], worlds["parent"]["origin_xy"])
        self.assert_point([10, 30], worlds["parent"]["endpoint_xy"])
        self.assert_point([10, 30], worlds["child"]["origin_xy"])
        self.assert_point([0, 30], worlds["child"]["endpoint_xy"])

    def test_world_local_roundtrip_supports_rotation_and_mirror_scale(self) -> None:
        point = (7.5, -2.25)
        world = local_to_world_point(point, (20, 30), -135, (-2, 0.5))
        restored = world_to_local_point(world, (20, 30), -135, (-2, 0.5))
        self.assert_point(point, restored)

        mirrored = {
            "joints": [
                {"id": "start", "x": 5, "y": 5, "confidence": 0.5, "source": "fallback"},
                {"id": "end", "x": -5, "y": 5, "confidence": 0.4, "source": "fallback"},
            ],
            "bones": [
                {"id": "leftward", "parent_id": None, "start_joint_id": "start", "end_joint_id": "end"}
            ],
        }
        bone = compile_setup_bones(mirrored)[0]
        self.assertEqual("template", bone["inference"]["method"])
        self.assertEqual(0.4, bone["inference"]["confidence"])
        self.assert_point([-5, 5], evaluate_world_setup([bone])["leftward"]["endpoint_xy"])

    def test_unreviewed_heuristic_is_not_labeled_manual_or_upscored(self) -> None:
        skeleton = skeleton_fixture()
        skeleton["joints"][1].pop("decision_kind")
        skeleton["joints"][1]["source"] = "audit-bbox-heuristic-v1"
        bones = compile_setup_bones(skeleton)
        by_id = {bone["id"]: bone for bone in bones}
        self.assertEqual("template", by_id["parent"]["inference"]["method"])
        self.assertEqual(0.8, by_id["parent"]["inference"]["confidence"])
        self.assertEqual("template", by_id["child"]["inference"]["method"])
        self.assertLess(by_id["child"]["inference"]["confidence"], 1.0)

    def test_source_contract_errors_fail_loudly(self) -> None:
        cases: list[tuple[str, dict]] = []
        duplicate_joint = skeleton_fixture()
        duplicate_joint["joints"].append(deepcopy(duplicate_joint["joints"][0]))
        cases.append(("duplicate joint", duplicate_joint))
        missing_joint = skeleton_fixture()
        missing_joint["bones"][0]["end_joint_id"] = "missing"
        cases.append(("missing joint", missing_joint))
        duplicate_bone = skeleton_fixture()
        duplicate_bone["bones"].append(deepcopy(duplicate_bone["bones"][0]))
        cases.append(("duplicate bone", duplicate_bone))
        missing_parent = skeleton_fixture()
        missing_parent["bones"][0]["parent_id"] = "missing"
        cases.append(("missing parent", missing_parent))
        cycle = skeleton_fixture()
        cycle["bones"][1]["parent_id"] = "child"
        cases.append(("cycle", cycle))
        zero = skeleton_fixture()
        zero["joints"][2]["x"], zero["joints"][2]["y"] = 10, 30
        cases.append(("zero", zero))
        non_finite = skeleton_fixture()
        non_finite["joints"][0]["x"] = math.nan
        cases.append(("non-finite", non_finite))
        for label, skeleton in cases:
            with self.subTest(label=label), self.assertRaises(RigFkError):
                compile_setup_bones(skeleton)

    def test_invalid_rig_setup_never_produces_nan(self) -> None:
        valid = compile_setup_bones(skeleton_fixture())
        cases = []
        missing_parent = deepcopy(valid)
        missing_parent[1]["parent"] = "missing"
        cases.append(missing_parent)
        cycle = deepcopy(valid)
        cycle[0]["parent"] = "child"
        cases.append(cycle)
        non_finite = deepcopy(valid)
        non_finite[0]["setup"]["rotation_deg"] = math.inf
        cases.append(non_finite)
        zero = deepcopy(valid)
        zero[0]["setup"]["length"] = 0
        cases.append(zero)
        for rig_bones in cases:
            with self.assertRaises(RigFkError):
                evaluate_world_setup(rig_bones)

    def assert_point(self, expected: object, actual: object) -> None:
        assert isinstance(expected, (list, tuple)) and isinstance(actual, (list, tuple))
        self.assertAlmostEqual(float(expected[0]), float(actual[0]), places=9)
        self.assertAlmostEqual(float(expected[1]), float(actual[1]), places=9)


if __name__ == "__main__":
    unittest.main()
