"""Semantic validation that JSON Schema cannot express for RigIR."""

from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKBENCH_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.rig_validation import (
    RigSemanticValidationError,
    RigSemanticValidator,
)
from autospine_workbench.cli import main as cli_main  # noqa: E402


SHA = "0" * 64


def valid_rig() -> dict:
    return {
        "format": "autospine-rig-ir",
        "format_version": 1,
        "source": {"layer_manifest_sha256": SHA},
        "canvas": {
            "width": 100,
            "height": 200,
            "origin": "top_left",
            "x_axis": "right",
            "y_axis": "down",
            "units": "pixel",
        },
        "capabilities": ["mesh_attachment", "bone_rotate", "setup_draw_order"],
        "unsupported_feature_policy": "fail",
        "bones": [
            {
                "id": "root",
                "parent": None,
                "setup": {"x": 0, "y": 0, "rotation_deg": 0, "scale_x": 1, "scale_y": 1, "length": 0},
                "inference": {"method": "manual", "confidence": 1},
            },
            {
                "id": "arm",
                "parent": "root",
                "setup": {"x": 1, "y": 2, "rotation_deg": 0, "scale_x": 1, "scale_y": 1, "length": 10},
                "inference": {"method": "landmark", "confidence": 0.8},
            },
        ],
        "slots": [
            {
                "id": "arm-slot",
                "bone": "arm",
                "setup_attachment": "arm-mesh",
                "setup_draw_order": 0,
                "blend": "normal",
                "color_rgba": "ffffffff",
            }
        ],
        "attachments": [
            {
                "id": "arm-mesh",
                "slot": "arm-slot",
                "type": "mesh",
                "image_path": "layers/arm.png",
                "image_sha256": SHA,
                "source_layer_ids": ["arm-layer"],
                "canvas_offset_xy": [0, 0],
                "pivot_xy": [1, 2],
                "vertices": [[0, 0], [10, 0], [0, 10]],
                "uvs": [[0, 0], [1, 0], [0, 1]],
                "triangles": [0, 1, 2],
                "weights": [
                    [{"bone": "root", "weight": 0.5}, {"bone": "arm", "weight": 0.5}],
                    [{"bone": "arm", "weight": 1.0}],
                    [{"bone": "arm", "weight": 1.0}],
                ],
            }
        ],
        "skins": {"default": {"arm-slot": ["arm-mesh"]}},
        "animations": [
            {
                "id": "probe",
                "duration": 1,
                "loop": False,
                "timelines": [
                    {
                        "bone": "arm",
                        "property": "rotate",
                        "keys": [{"time": 0, "value": 0}, {"time": 1, "value": 45}],
                    }
                ],
            }
        ],
        "qa": {"status": "passed", "checks": [], "manual_override_ids": []},
    }


class RigSemanticValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = RigSemanticValidator()

    def issue_codes(self, rig: dict) -> set[str]:
        return {issue.code for issue in self.validator.validate(rig)}

    def test_valid_mesh_and_animation_have_no_semantic_issues(self) -> None:
        self.assertEqual([], self.validator.validate(valid_rig()))

    def test_cross_references_and_bone_cycles_fail_loudly(self) -> None:
        rig = valid_rig()
        rig["bones"][0]["parent"] = "arm"
        rig["slots"][0]["bone"] = "missing"
        rig["attachments"][0]["slot"] = "missing-slot"
        rig["skins"]["default"] = {"arm-slot": ["missing-attachment"]}
        rig["animations"][0]["timelines"][0]["bone"] = "missing"
        codes = self.issue_codes(rig)
        self.assertTrue(
            {"bone_cycle", "missing_slot_bone", "missing_attachment_slot", "missing_skin_attachment", "missing_timeline_bone"}.issubset(codes)
        )
        with self.assertRaises(RigSemanticValidationError) as caught:
            self.validator.raise_for_errors(rig)
        self.assertGreaterEqual(len(caught.exception.issues), 5)

    def test_mesh_cardinality_triangle_and_weight_rules(self) -> None:
        rig = valid_rig()
        mesh = rig["attachments"][0]
        mesh["uvs"].pop()
        mesh["triangles"] = [0, 1, 99, 0]
        mesh["weights"][0] = [
            {"bone": "missing", "weight": 0.2},
            {"bone": "arm", "weight": 0.2},
            {"bone": "arm", "weight": 0.2},
            {"bone": "root", "weight": 0.2},
            {"bone": "arm", "weight": 0.2},
        ]
        codes = self.issue_codes(rig)
        self.assertTrue(
            {"mesh_cardinality", "triangle_arity", "triangle_index_out_of_range", "too_many_influences", "missing_weight_bone", "duplicate_weight_bone"}.issubset(codes)
        )

    def test_non_finite_values_weight_sum_and_capabilities_are_rejected(self) -> None:
        rig = deepcopy(valid_rig())
        rig["bones"][1]["setup"]["x"] = math.nan
        rig["attachments"][0]["vertices"][0][0] = math.inf
        rig["attachments"][0]["weights"][0] = [{"bone": "arm", "weight": 0.4}]
        rig["capabilities"] = []
        codes = self.issue_codes(rig)
        self.assertIn("non_finite_number", codes)
        self.assertIn("weight_sum", codes)
        self.assertIn("undeclared_capability", codes)

    def test_animation_time_and_property_value_semantics(self) -> None:
        rig = valid_rig()
        timeline = rig["animations"][0]["timelines"][0]
        timeline["keys"] = [
            {"time": 0.8, "value": [0, 1]},
            {"time": 0.2, "value": 10},
            {"time": 1.2, "value": 20},
        ]
        codes = self.issue_codes(rig)
        self.assertIn("invalid_rotate_value", codes)
        self.assertIn("key_time_order", codes)
        self.assertIn("key_after_duration", codes)

    def test_validate_rig_cli_returns_machine_readable_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            rig_path = Path(directory) / "rig.json"
            rig_path.write_text(json.dumps(valid_rig()), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                result = cli_main(["validate-rig", str(rig_path)])
        self.assertEqual(0, result)
        self.assertEqual({"valid": True, "issues": []}, json.loads(output.getvalue()))


if __name__ == "__main__":
    unittest.main()
