"""Pinned COCO17 input and canonical adapter tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.coco17_adapter import (  # noqa: E402
    Coco17AdapterError,
    adapt_coco17_detections,
)
from autospine_workbench.coco17_detections import (  # noqa: E402
    Coco17DetectionError,
    load_coco17_detections,
)
from autospine_workbench.pose_observations import load_pose_observations  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None


def detection_fixture() -> dict:
    return {
        "format": "autospine-coco17-detections",
        "format_version": 1,
        "project_id": "sample-a",
        "source": {
            "image_kind": "composite",
            "image_sha256": "a" * 64,
            "canvas_size": [100, 200],
        },
        "detector": {
            "id": "fixture-coco17",
            "version": "1.2.0",
            "model_revision": "upstream-commit-123",
            "model_sha256": "b" * 64,
            "config_sha256": "c" * 64,
            "runtime": "onnxruntime-1.22-cpu",
        },
        "coordinate_system": {
            "origin": "top_left",
            "x_axis": "right",
            "y_axis": "down",
            "units": "pixel",
            "side_naming": "coco_character_side",
            "image_space": "project_canvas",
        },
        "detected_count": 1,
        "detections": [
            {
                "keypoints": [[10.12345678 + index, 20 + index] for index in range(17)],
                "keypoint_scores": [round(0.1 + index * 0.04, 4) for index in range(17)],
                "bbox_xywh": [5, 10, 40, 100],
                "instance_score": 0.88,
            }
        ],
    }


class Coco17AdapterTests(unittest.TestCase):
    def _load(self, document: dict):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "detections.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return load_coco17_detections(
                path,
                expected_project_id="sample-a",
                expected_image_sha256="a" * 64,
                expected_canvas_size=(100, 200),
            )

    def _adapt(self, document: dict, **overrides):
        arguments = {
            "selected_index": None,
            "selection_method": None,
            "side_mapping": "as_reported",
            "view_orientation": "front",
            "mirror_state": "not_mirrored",
        }
        arguments.update(overrides)
        return adapt_coco17_detections(self._load(document), **arguments)

    def test_identity_mapping_preserves_native_score_and_emits_loadable_v2(self) -> None:
        output = self._adapt(detection_fixture())
        self.assertEqual(2, output["format_version"])
        self.assertEqual([15.123457, 25.0], output["joints"]["shoulder.left"]["xy"])
        self.assertEqual(0.3, output["joints"]["shoulder.left"]["detector_score"])
        self.assertEqual("unknown", output["joints"]["shoulder.left"]["visibility"])
        self.assertEqual("identity", output["adapter"]["coordinate_transform"])
        self.assertNotIn("confidence", json.dumps(output))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pose.json"
            path.write_text(json.dumps(output), encoding="utf-8")
            loaded = load_pose_observations(
                path,
                expected_project_id="sample-a",
                expected_image_sha256="a" * 64,
                expected_canvas_size=(100, 200),
            )
        self.assertEqual("as_reported", loaded.adapter["side_mapping"])
        self.assertEqual(12, len(loaded.joints))

    def test_side_swap_and_coordinate_unmirror_are_independent(self) -> None:
        document = detection_fixture()
        document["coordinate_system"]["image_space"] = (
            "horizontally_mirrored_project_canvas"
        )
        output = self._adapt(document, side_mapping="swap_left_right")
        self.assertEqual([83.876543, 25.0], output["joints"]["shoulder.right"]["xy"])
        self.assertEqual([82.876543, 26.0], output["joints"]["shoulder.left"]["xy"])
        self.assertEqual("unmirror_x", output["adapter"]["coordinate_transform"])
        self.assertEqual("swap_left_right", output["adapter"]["side_mapping"])

    def test_multiple_subjects_require_reproducible_selection(self) -> None:
        document = detection_fixture()
        second = copy.deepcopy(document["detections"][0])
        second["bbox_xywh"] = [10, 20, 60, 120]
        document["detections"].append(second)
        document["detected_count"] = 2
        with self.assertRaises(Coco17AdapterError):
            self._adapt(document)
        with self.assertRaises(Coco17AdapterError):
            self._adapt(document, selected_index=0, selection_method="largest_area")
        selected = self._adapt(
            document, selected_index=1, selection_method="largest_area"
        )
        self.assertEqual(1, selected["subject"]["selected_index"])
        manual = self._adapt(document, selected_index=0, selection_method="manual")
        self.assertEqual("manual", manual["subject"]["selection_method"])

    def test_wrong_source_shape_bounds_and_unknown_fields_fail_loudly(self) -> None:
        mutations = []
        wrong_hash = detection_fixture()
        wrong_hash["source"]["image_sha256"] = "d" * 64
        mutations.append(wrong_hash)
        wrong_count = detection_fixture()
        wrong_count["detected_count"] = 2
        mutations.append(wrong_count)
        wrong_shape = detection_fixture()
        wrong_shape["detections"][0]["keypoints"].pop()
        mutations.append(wrong_shape)
        outside = detection_fixture()
        outside["detections"][0]["keypoints"][5] = [100, 30]
        mutations.append(outside)
        unknown = detection_fixture()
        unknown["detections"][0]["category_id"] = 1
        mutations.append(unknown)
        for document in mutations:
            with self.subTest(document=document), self.assertRaises(Coco17DetectionError):
                self._load(document)

    def test_adapter_output_is_deterministic_and_requires_orientation_choices(self) -> None:
        first = self._adapt(detection_fixture())
        second = self._adapt(detection_fixture())
        self.assertEqual(first, second)
        with self.assertRaises(Coco17AdapterError):
            self._adapt(detection_fixture(), view_orientation="")
        with self.assertRaises(Coco17AdapterError):
            self._adapt(detection_fixture(), mirror_state="")

    @unittest.skipIf(Draft202012Validator is None, "install the 'test' extra")
    def test_documents_validate_against_schemas(self) -> None:
        raw = detection_fixture()
        output = self._adapt(raw)
        for name, document in (
            ("coco17-detections-v1.schema.json", raw),
            ("pose-observations-v2.schema.json", output),
        ):
            schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(document)


if __name__ == "__main__":
    unittest.main()
