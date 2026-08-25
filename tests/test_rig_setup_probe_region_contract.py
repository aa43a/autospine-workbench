"""Exact manifest-to-slot contract checks for region setup probes."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.rig_fk import compile_setup_bones  # noqa: E402
from autospine_workbench.rig_setup_probe_regions import run_region_checks  # noqa: E402


def skeleton_fixture(*, ambiguous_legacy: bool = False) -> dict:
    joints = [
        {"id": "a", "x": 0, "y": 0, "confidence": 1.0, "decision_kind": "manual_absolute"},
        {"id": "b", "x": 10, "y": 0, "confidence": 1.0, "decision_kind": "manual_absolute"},
        {"id": "c", "x": 0, "y": 10, "confidence": 1.0, "decision_kind": "manual_absolute"},
        {"id": "d", "x": 10, "y": 10, "confidence": 1.0, "decision_kind": "manual_absolute"},
    ]
    bones = [
        {
            "id": "arm",
            "parent_id": None,
            "start_joint_id": "a",
            "end_joint_id": "b",
        },
        {
            "id": "other",
            "parent_id": None,
            "start_joint_id": "c",
            "end_joint_id": "d",
        },
    ]
    if ambiguous_legacy:
        bones.append(
            {
                "id": "arm-alternate",
                "parent_id": None,
                "start_joint_id": "c",
                "end_joint_id": "b",
            }
        )
    return {"joints": joints, "bones": bones}


def manifest_fixture(candidate_bone: str = "arm") -> dict:
    return {
        "layers": [
            {
                "layer_id": "arm-layer",
                "source": {
                    "visible": True,
                    "opacity": 0.5,
                    "blend_mode": "multiply",
                },
                "raster": {
                    "artifact_path": "layers/arm-layer.png",
                    "sha256": "a" * 64,
                    "canvas_size": [20, 20],
                    "canvas_offset_xy": [0, 0],
                    "crop_bbox_xywh": [0, 0, 1, 1],
                },
                "rig_hint": {
                    "attachment_kind": "region",
                    "candidate_bone": candidate_bone,
                    "pivot": {"xy": [5, 0], "method": "manual"},
                    "setup_draw_order": 7,
                },
            }
        ]
    }


def rig_fixture(skeleton: dict) -> dict:
    return {
        "capabilities": ["region_attachment"],
        "bones": compile_setup_bones(skeleton),
        "slots": [
            {
                "id": "arm-layer",
                "bone": "arm",
                "setup_attachment": "arm-layer",
                "setup_draw_order": 7,
                "blend": "multiply",
                "color_rgba": "ffffff80",
            }
        ],
        "attachments": [
            {
                "id": "arm-layer",
                "slot": "arm-layer",
                "type": "region",
                "image_path": "layers/arm-layer.png",
                "image_sha256": "a" * 64,
                "source_layer_ids": ["arm-layer"],
                "canvas_offset_xy": [0, 0],
                "pivot_xy": [5, 0],
                "size": [1, 1],
            }
        ],
        "skins": {"default": {"arm-layer": ["arm-layer"]}},
    }


def checks(rig: dict, manifest: dict, skeleton: dict) -> dict:
    return {
        check["id"]: check
        for check in run_region_checks(rig, manifest, {"skeleton": skeleton})
    }


class RegionProbeContractTests(unittest.TestCase):
    def test_direct_and_unique_legacy_bone_hints_pass(self) -> None:
        skeleton = skeleton_fixture()
        rig = rig_fixture(skeleton)
        direct = checks(rig, manifest_fixture("arm"), skeleton)
        legacy = checks(rig, manifest_fixture("b"), skeleton)
        self.assertEqual("passed", direct["attachments.region-bindings"]["status"])
        self.assertEqual("passed", legacy["attachments.region-bindings"]["status"])

    def test_wrong_existing_slot_bone_is_rejected(self) -> None:
        skeleton = skeleton_fixture()
        rig = rig_fixture(skeleton)
        rig["slots"][0]["bone"] = "other"
        binding = checks(rig, manifest_fixture(), skeleton)["attachments.region-bindings"]
        self.assertEqual("rejected", binding["status"])
        self.assertIn("bone does not match manifest layer", binding["message"])

    def test_ambiguous_legacy_end_joint_is_rejected(self) -> None:
        skeleton = skeleton_fixture(ambiguous_legacy=True)
        binding = checks(
            rig_fixture(skeleton), manifest_fixture("b"), skeleton
        )["attachments.region-bindings"]
        self.assertEqual("rejected", binding["status"])
        self.assertIn("ambiguous legacy joint", binding["message"])

    def test_slot_style_and_exact_draw_order_are_checked(self) -> None:
        skeleton = skeleton_fixture()
        rig = rig_fixture(skeleton)
        slot = rig["slots"][0]
        slot.update({"blend": "normal", "color_rgba": "ffffffff", "setup_draw_order": 8})
        result = checks(rig, manifest_fixture(), skeleton)
        binding = result["attachments.region-bindings"]
        self.assertEqual("rejected", binding["status"])
        self.assertIn("blend does not match", binding["message"])
        self.assertIn("color does not match", binding["message"])
        draw_order = result["slots.draw-order"]
        self.assertEqual("rejected", draw_order["status"])
        self.assertIn("draw order does not match manifest", draw_order["message"])


if __name__ == "__main__":
    unittest.main()
