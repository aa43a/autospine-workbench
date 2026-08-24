"""Canonical external pose observation boundary tests."""

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

from autospine_workbench.pose_observations import (  # noqa: E402
    PoseObservationError,
    load_pose_observations,
)

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None


def observation_fixture() -> dict:
    return {
        "format": "autospine-pose-observations",
        "format_version": 1,
        "project_id": "sample-a",
        "source": {
            "image_kind": "composite",
            "image_sha256": "a" * 64,
            "canvas_size": [100, 200],
        },
        "detector": {
            "id": "anime-pose-onnx",
            "version": "1.2.0",
            "model_revision": "upstream-commit-123",
            "model_sha256": "b" * 64,
            "config_sha256": "c" * 64,
            "runtime": "onnxruntime-1.22-cpu",
        },
        "subject": {
            "detected_count": 1,
            "selected_index": 0,
            "selection_method": "single",
        },
        "coordinate_system": {
            "origin": "top_left",
            "x_axis": "right",
            "y_axis": "down",
            "units": "pixel",
            "side_naming": "character_side",
        },
        "joints": {
            "elbow.left": {
                "xy": [20.5, 60.25],
                "detector_score": 0.82,
                "visibility": "visible",
            }
        },
    }


class PoseObservationTests(unittest.TestCase):
    def _load(self, document: dict):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pose.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return load_pose_observations(
                path,
                expected_project_id="sample-a",
                expected_image_sha256="a" * 64,
                expected_canvas_size=(100, 200),
            )

    def test_valid_document_is_pinned_and_detector_score_stays_native(self) -> None:
        first = self._load(observation_fixture())
        second = self._load(observation_fixture())
        self.assertEqual(first.document_sha256, second.document_sha256)
        self.assertEqual(first.joints["elbow.left"].detector_score, 0.82)
        self.assertFalse(hasattr(first.joints["elbow.left"], "confidence"))

    def test_project_image_canvas_and_unknown_fields_fail_loudly(self) -> None:
        mutations = []
        wrong_project = copy.deepcopy(observation_fixture())
        wrong_project["project_id"] = "sample-b"
        mutations.append(wrong_project)
        wrong_image = copy.deepcopy(observation_fixture())
        wrong_image["source"]["image_sha256"] = "d" * 64
        mutations.append(wrong_image)
        wrong_canvas = copy.deepcopy(observation_fixture())
        wrong_canvas["source"]["canvas_size"] = [101, 200]
        mutations.append(wrong_canvas)
        unknown = copy.deepcopy(observation_fixture())
        unknown["detector"]["confidence"] = 1
        mutations.append(unknown)
        for document in mutations:
            with self.subTest(document=document), self.assertRaises(PoseObservationError):
                self._load(document)

    def test_non_finite_out_of_bounds_and_ambiguous_subject_fail(self) -> None:
        invalid_score = copy.deepcopy(observation_fixture())
        invalid_score["joints"]["elbow.left"]["detector_score"] = float("nan")
        with self.assertRaises(PoseObservationError):
            self._load(invalid_score)
        outside = copy.deepcopy(observation_fixture())
        outside["joints"]["elbow.left"]["xy"] = [101, 20]
        with self.assertRaises(PoseObservationError):
            self._load(outside)
        ambiguous = copy.deepcopy(observation_fixture())
        ambiguous["subject"]["detected_count"] = 2
        with self.assertRaises(PoseObservationError):
            self._load(ambiguous)

    @unittest.skipIf(Draft202012Validator is None, "install the 'test' extra")
    def test_fixture_validates_against_schema(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "pose-observations-v1.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(observation_fixture())


if __name__ == "__main__":
    unittest.main()
