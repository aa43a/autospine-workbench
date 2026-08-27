"""Pinned Spine 4.2 JSON adapter coordinate, mesh, and motion tests."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.rig_fk import (  # noqa: E402
    evaluate_world_setup,
    local_to_world_point,
)
from autospine_workbench.motion_target_profile import (  # noqa: E402
    compile_motion_target_profile,
)
from autospine_workbench.spine42_contract import (  # noqa: E402
    SPINE_RUNTIME_PACKAGE,
    SPINE_RUNTIME_VERSION,
    Spine42ContractError,
    canonical_spine42_json,
    spine42_json_sha256,
    spine42_target_profile,
)
from autospine_workbench.spine42_json_adapter import (  # noqa: E402
    build_spine42_json,
    build_spine42_json_bytes,
)
from tests.test_mesh_rig import compile_a  # noqa: E402
from tests.test_motion_instance_contract import instance_fixture  # noqa: E402
from tests.test_motion_target_profile import full_rig, pair  # noqa: E402


def rig_fixture() -> dict:
    rig = full_rig()
    for bone in rig["bones"]:
        bone["inference"] = {"method": "manual", "confidence": 1.0}
    rig.update({
        "source": {
            "run_manifest_sha256": "1" * 64,
            "layer_manifest_sha256": "2" * 64,
            "override_patch_sha256": "3" * 64,
        },
        "capabilities": [
            "region_attachment", "mesh_attachment", "setup_draw_order",
        ],
        "unsupported_feature_policy": "fail",
        "slots": [
            {
                "id": "face", "bone": "neck-head",
                "setup_attachment": "face-image", "setup_draw_order": 1,
                "blend": "normal", "color_rgba": "ffffffff",
            },
            {
                "id": "leg", "bone": "thigh.left",
                "setup_attachment": "leg-mesh", "setup_draw_order": 0,
                "blend": "normal", "color_rgba": "ffffffff",
            },
        ],
        "attachments": [
            {
                "id": "face-image", "slot": "face", "type": "region",
                "image_path": "layers/face.png", "image_sha256": "4" * 64,
                "source_layer_ids": ["face-layer"],
                "canvas_offset_xy": [185, 20], "pivot_xy": [10, 15],
                "size": [20, 30],
            },
            {
                "id": "leg-mesh", "slot": "leg", "type": "mesh",
                "image_path": "layers/leg.png", "image_sha256": "5" * 64,
                "source_layer_ids": ["leg-layer"],
                "canvas_offset_xy": [120, 250], "pivot_xy": [10, 20],
                "vertices": [[0, 0], [20, 0], [10, 40]],
                "uvs": [[0, 0], [1, 0], [0.5, 1]],
                "triangles": [0, 1, 2],
                "weights": [
                    [{"bone": "thigh.left", "weight": 1.0}],
                    [
                        {"bone": "calf.left", "weight": 0.75},
                        {"bone": "thigh.left", "weight": 0.25},
                    ],
                    [{"bone": "calf.left", "weight": 1.0}],
                ],
            },
        ],
        "skins": {
            "default": {
                "face": ["face-image"], "leg": ["leg-mesh"],
            },
        },
        "animations": [],
        "qa": {"status": "passed", "checks": [], "manual_override_ids": []},
    })
    return rig


def motion_pair(rig: dict) -> tuple[dict, dict]:
    target = compile_motion_target_profile(*pair(rig=rig)).document
    return target, instance_fixture(target)


def attachment(document: dict, slot: str, name: str) -> dict:
    return document["skins"][0]["attachments"][slot][name]


def decode_vertices(values: list, count: int) -> list[list[tuple[int, float, float, float]]]:
    cursor, result = 0, []
    for _ in range(count):
        influences = []
        influence_count = values[cursor]
        cursor += 1
        for _ in range(influence_count):
            bone, x, y, weight = values[cursor:cursor + 4]
            influences.append((bone, x, y, weight))
            cursor += 4
        result.append(influences)
    if cursor != len(values):
        raise AssertionError("trailing weighted vertex data")
    return result


class Spine42JsonAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rig = rig_fixture()

    def test_profile_and_skeleton_are_exactly_version_locked(self) -> None:
        profile = spine42_target_profile()
        self.assertEqual("4.2", profile["spine_major_minor"])
        self.assertEqual("json", profile["skeleton_format"])
        self.assertEqual(SPINE_RUNTIME_PACKAGE, profile["runtime"]["package"])
        self.assertEqual(SPINE_RUNTIME_VERSION, profile["runtime"]["version"])

        result = build_spine42_json(self.rig)
        self.assertEqual("4.2", result["skeleton"]["spine"])
        bones = {item["name"]: item for item in result["bones"]}
        root = bones["root-pelvis"]
        self.assertEqual((200.0, 40.0, 90.0), (
            root["x"], root["y"], root["rotation"],
        ))
        child = bones["pelvis-spine"]
        self.assertEqual((20.0, 0.0, 0.0), (
            child["x"], child["y"], child["rotation"],
        ))

    def test_real_p3_compiler_shape_enters_adapter_without_translation(self) -> None:
        p3 = compile_a().rig
        result = build_spine42_json(p3)
        kinds = [
            value["type"]
            for attachments in result["skins"][0]["attachments"].values()
            for value in attachments.values()
        ]
        self.assertEqual(["mesh", "mesh", "region"], kinds)
        self.assertEqual(
            [bone["id"] for bone in p3["bones"]],
            [bone["name"] for bone in result["bones"]],
        )

    def test_region_setup_and_draw_order_reconstruct_exactly(self) -> None:
        result = build_spine42_json(self.rig)
        self.assertEqual(["leg", "face"], [slot["name"] for slot in result["slots"]])
        self.assertIsInstance(result["skins"], list)
        self.assertEqual("default", result["skins"][0]["name"])
        region = attachment(result, "face", "face-image")
        self.assertEqual("face-image", region["path"])

        source_world = evaluate_world_setup(self.rig["bones"])["neck-head"]
        reflected_origin = (
            source_world["origin_xy"][0],
            self.rig["canvas"]["height"] - source_world["origin_xy"][1],
        )
        center = local_to_world_point(
            [region["x"], region["y"]], reflected_origin,
            -source_world["rotation_deg"],
        )
        self.assertAlmostEqual(195.0, center[0], places=9)
        self.assertAlmostEqual(365.0, center[1], places=9)
        self.assertAlmostEqual(
            0.0, -source_world["rotation_deg"] + region["rotation"], places=9
        )

    def test_weighted_mesh_preserves_uv_winding_and_reflected_setup(self) -> None:
        result = build_spine42_json(self.rig)
        mesh = attachment(result, "leg", "leg-mesh")
        self.assertEqual([0.0, 0.0, 1.0, 0.0, 0.5, 1.0], mesh["uvs"])
        self.assertEqual([0, 1, 2], mesh["triangles"])
        decoded = decode_vertices(mesh["vertices"], 3)
        self.assertEqual([1, 2, 1], [len(items) for items in decoded])
        names = [bone["name"] for bone in result["bones"]]
        worlds = evaluate_world_setup(self.rig["bones"])
        for vertex, influences in zip(self.rig["attachments"][1]["vertices"], decoded):
            expected = (120 + vertex[0], 400 - (250 + vertex[1]))
            for bone_index, x, y, _weight in influences:
                frame = worlds[names[bone_index]]
                actual = local_to_world_point(
                    [x, y],
                    [frame["origin_xy"][0], 400 - frame["origin_xy"][1]],
                    -frame["rotation_deg"],
                )
                self.assertAlmostEqual(expected[0], actual[0], places=9)
                self.assertAlmostEqual(expected[1], actual[1], places=9)

    def test_motion_deltas_and_contact_annotations_are_projected(self) -> None:
        target, instance = motion_pair(self.rig)
        result = build_spine42_json(
            self.rig, motion_instance=instance, target_profile=target
        )
        animation = result["animations"]["wave.left"]
        self.assertEqual(
            20.0, animation["bones"]["forearm.left"]["rotate"][1]["value"]
        )
        root_middle = animation["bones"]["root-pelvis"]["translate"][1]
        self.assertEqual((1.5, 2.0), (root_middle["x"], root_middle["y"]))
        self.assertEqual(
            -15.0, animation["bones"]["upper-arm.left"]["rotate"][1]["value"]
        )
        self.assertEqual({
            "contact.leg.left.start", "contact.leg.left.end",
            "contact.leg.right.start", "contact.leg.right.end",
        }, set(result["events"]))
        self.assertEqual(4, len(animation["events"]))

    def test_canonical_bytes_are_deterministic_and_inputs_are_immutable(self) -> None:
        before = deepcopy(self.rig)
        first = build_spine42_json(self.rig)
        reversed_keys = {key: self.rig[key] for key in reversed(self.rig)}
        second = build_spine42_json(reversed_keys)
        self.assertEqual(first, second)
        self.assertEqual(self.rig, before)
        self.assertEqual(canonical_spine42_json(first), build_spine42_json_bytes(self.rig))
        self.assertEqual(64, len(spine42_json_sha256(first)))
        self.assertEqual(first, json.loads(canonical_spine42_json(first)))

    def test_unsupported_or_unsafe_inputs_fail_closed(self) -> None:
        cases = []
        scaled = deepcopy(self.rig)
        scaled["bones"][0]["setup"]["scale_x"] = 2.0
        cases.append(scaled)
        nonfinite = deepcopy(self.rig)
        nonfinite["bones"][0]["setup"]["x"] = math.nan
        cases.append(nonfinite)
        bad_triangle = deepcopy(self.rig)
        bad_triangle["attachments"][1]["triangles"][2] = 99
        cases.append(bad_triangle)
        missing_bone = deepcopy(self.rig)
        missing_bone["slots"][0]["bone"] = "missing"
        cases.append(missing_bone)
        embedded_animation = deepcopy(self.rig)
        embedded_animation["animations"] = [{"id": "legacy"}]
        cases.append(embedded_animation)
        for index, invalid in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(Spine42ContractError):
                build_spine42_json(invalid)

        target, instance = motion_pair(self.rig)
        with self.assertRaisesRegex(Spine42ContractError, "together"):
            build_spine42_json(self.rig, motion_instance=instance)
        stale = deepcopy(target)
        stale["source"]["p3"]["rig_sha256"] = "f" * 64
        with self.assertRaises(Spine42ContractError):
            build_spine42_json(
                self.rig, motion_instance=instance, target_profile=stale
            )


if __name__ == "__main__":
    unittest.main()
