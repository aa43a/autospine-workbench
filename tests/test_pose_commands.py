"""Pose adapter command integration tests."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.cli import build_parser  # noqa: E402
from autospine_workbench.pose_commands import import_pose  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


class PoseImportCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.directory.name))
        self.input_path = Path(self.directory.name) / "coco17.json"
        self.input_path.write_text(json.dumps(self._input_document()), encoding="utf-8")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _input_document(self) -> dict:
        return {
            "format": "autospine-coco17-detections",
            "format_version": 1,
            "project_id": "fixture-project",
            "source": {
                "image_kind": "composite",
                "image_sha256": hashlib.sha256(
                    self.fixture.composite.read_bytes()
                ).hexdigest(),
                "canvas_size": [512, 768],
            },
            "detector": {
                "id": "fixture-coco17",
                "version": "1",
                "model_revision": "fixture-model-revision",
                "config_sha256": "d" * 64,
                "runtime": "unittest",
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
                    "keypoints": [[100 + index, 200 + index] for index in range(17)],
                    "keypoint_scores": [0.75] * 17,
                }
            ],
        }

    def _run(self) -> tuple[int, dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            status = import_pose(
                "fixture-project",
                self.input_path,
                self.fixture.workspace,
                self.fixture.state,
                selected_index=None,
                selection_method=None,
                side_mapping="as_reported",
                view_orientation="front",
                mirror_state="not_mirrored",
            )
        return status, json.loads(output.getvalue())

    def test_import_publishes_pinned_input_and_canonical_pose(self) -> None:
        status, response = self._run()
        self.assertEqual(0, status)
        self.assertTrue(response["ok"])
        input_path = Path(response["input_artifact_path"])
        pose_path = Path(response["pose_artifact_path"])
        self.assertTrue(input_path.is_file())
        self.assertTrue(pose_path.is_file())
        self.assertEqual(response["input_artifact_sha256"], input_path.stem)
        self.assertEqual(response["pose_artifact_sha256"], pose_path.stem)
        self.assertEqual("pose-adapter-inputs", input_path.parent.name)
        self.assertEqual("pose-observations", pose_path.parent.name)
        pose = json.loads(pose_path.read_text(encoding="utf-8"))
        self.assertEqual(2, pose["format_version"])
        self.assertEqual(input_path.stem, pose["adapter"]["input_document_sha256"])

        _, repeated = self._run()
        self.assertEqual(response["input_artifact_path"], repeated["input_artifact_path"])
        self.assertEqual(response["pose_artifact_path"], repeated["pose_artifact_path"])

    def test_mismatched_input_does_not_publish(self) -> None:
        document = self._input_document()
        document["source"]["image_sha256"] = "f" * 64
        self.input_path.write_text(json.dumps(document), encoding="utf-8")
        status, response = self._run()
        self.assertEqual(2, status)
        self.assertFalse(response["ok"])
        self.assertFalse((self.fixture.state / "analysis").exists())

    def test_cli_requires_side_view_and_mirror_declarations(self) -> None:
        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            build_parser().parse_args(
                ["import-pose", "fixture-project", str(self.input_path)]
            )
        self.assertIn("--side-mapping", errors.getvalue())
        parsed = build_parser().parse_args(
            [
                "import-pose",
                "fixture-project",
                str(self.input_path),
                "--side-mapping",
                "as_reported",
                "--view-orientation",
                "unknown",
                "--mirror-state",
                "unknown",
            ]
        )
        self.assertEqual("unknown", parsed.view_orientation)


if __name__ == "__main__":
    unittest.main()
