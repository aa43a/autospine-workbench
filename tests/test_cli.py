"""Offline command integration tests."""

from __future__ import annotations

from contextlib import redirect_stdout
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

from autospine_workbench.cli import _analyze_joints  # noqa: E402
from tests.png_helpers import write_rgba  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


TRANSPARENT = (0, 0, 0, 0)
VISIBLE = (50, 60, 70, 255)


class JointAnalysisCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.directory.name))
        self.fixture.audit["canvas"] = [100, 100]
        layer = self.fixture.audit["layers"][0]
        layer["name"] = "hand-l"
        layer["bbox"] = [10, 20, 30, 40]
        layer["width"] = 20
        layer["height"] = 20
        self.fixture.write_audit()
        write_rgba(self.fixture.composite, [[VISIBLE]])
        write_rgba(self.fixture.embedded, [[VISIBLE]])
        rows = [[TRANSPARENT for _ in range(20)] for _ in range(20)]
        for y in range(4, 16):
            for x in range(2, 12):
                rows[y][x] = VISIBLE
        write_rgba(self.fixture.layer_image, rows)
        self.pose_path = Path(self.directory.name) / "pose.json"
        self.pose_path.write_text(json.dumps(self._pose_document()), encoding="utf-8")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _pose_document(self) -> dict:
        composite_sha = hashlib.sha256(self.fixture.composite.read_bytes()).hexdigest()
        return {
            "format": "autospine-pose-observations",
            "format_version": 1,
            "project_id": "fixture-project",
            "source": {
                "image_kind": "composite",
                "image_sha256": composite_sha,
                "canvas_size": [100, 100],
            },
            "detector": {
                "id": "fixture-pose",
                "version": "1",
                "model_revision": "fixture-model-revision",
                "config_sha256": "d" * 64,
                "runtime": "unittest",
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
                    "xy": [8, 25],
                    "detector_score": 0.8,
                    "visibility": "visible",
                }
            },
        }

    def test_pose_alpha_cli_publishes_a_valid_content_addressed_artifact(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = _analyze_joints(
                "fixture-project",
                self.fixture.workspace,
                self.fixture.state,
                provider_name="pose-alpha",
                pose_path=self.pose_path,
                alpha_threshold=8,
            )
        response = json.loads(output.getvalue())
        self.assertEqual(0, status)
        self.assertTrue(response["ok"])
        self.assertEqual("pose-alpha-limb-fusion", response["provider"])
        artifact = Path(response["artifact_path"])
        self.assertTrue(artifact.is_file())
        self.assertEqual(response["artifact_sha256"], artifact.stem)

    def test_provider_specific_arguments_fail_without_publishing(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = _analyze_joints(
                "fixture-project",
                self.fixture.workspace,
                self.fixture.state,
                provider_name="pose-alpha",
            )
        self.assertEqual(2, status)
        self.assertFalse(json.loads(output.getvalue())["ok"])


if __name__ == "__main__":
    unittest.main()
