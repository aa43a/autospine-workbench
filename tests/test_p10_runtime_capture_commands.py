"""Strong application boundary tests for licensed runtime capture."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_runtime_capture import (  # noqa: E402
    BodySwayRuntimeCapture,
)
from autospine_workbench.p10_runtime_capture_commands import (  # noqa: E402
    P10RuntimeCaptureCommandError,
    capture_body_sway_runtime_command,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    fake_runtime_profile,
)
from tests.p10_runtime_capture_command_support import (  # noqa: E402
    RuntimeCaptureCommandFixture,
)


SHA = {str(index): str(index) * 64 for index in range(1, 8)}


class P10RuntimeCaptureCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = RuntimeCaptureCommandFixture()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.close()

    def call(self, *, acknowledged=True, project_id=None):
        with fake_runtime_profile():
            return capture_body_sway_runtime_command(
                Path("state"), project_id or self.fixture.project_id,
                Path("candidates.json"), Path("decision.json"),
                Path("report.json"),
                layer_manifest_sha256=SHA["1"],
                p3_rig_sha256=SHA["2"],
                p3_bundle_sha256=SHA["3"],
                motion_instance_sha256=SHA["4"],
                motion_retarget_bundle_sha256=SHA["5"],
                motion_instance_v2_sha256=SHA["6"],
                reviewed_motion_bundle_sha256=SHA["7"],
                runtime_root=Path("licensed-runtime"),
                browser_executable=Path("chrome.exe"),
                license_acknowledged=acknowledged,
            )

    @patch("autospine_workbench.p10_runtime_capture_commands.BodySwayRuntimeCaptureStore")
    @patch("autospine_workbench.p10_runtime_capture_commands.run_p10_body_sway_runtime_capture")
    @patch("autospine_workbench.p10_runtime_capture_commands.compile_body_sway_preview_command")
    def test_license_rejection_precedes_all_services(
        self, compile_preview, run_capture, store_type,
    ):
        with self.assertRaisesRegex(
            P10RuntimeCaptureCommandError, "license acknowledgement",
        ):
            self.call(acknowledged=False)
        compile_preview.assert_not_called()
        run_capture.assert_not_called()
        store_type.assert_not_called()

    @patch("autospine_workbench.p10_runtime_capture_commands.BodySwayRuntimeCaptureStore")
    @patch("autospine_workbench.p10_runtime_capture_commands.run_p10_body_sway_runtime_capture")
    @patch("autospine_workbench.p10_runtime_capture_commands.compile_body_sway_preview_command")
    def test_keyword_only_capture_publishes_bound_private_evidence(
        self, compile_preview, run_capture, store_type,
    ):
        capture = self.fixture.runner_result()
        preview = Mock(
            temporary_preview_sha256=capture.temporary_preview_sha256
        )
        compile_preview.return_value = preview
        run_capture.return_value = capture
        store_type.return_value.publish.return_value = (
            self.fixture.publication()
        )

        result = self.call()

        compile_preview.assert_called_once_with(
            Path("state"), self.fixture.project_id,
            Path("candidates.json"), Path("decision.json"),
            Path("report.json"),
            layer_manifest_sha256=SHA["1"],
            p3_rig_sha256=SHA["2"],
            p3_bundle_sha256=SHA["3"],
            motion_instance_sha256=SHA["4"],
            motion_retarget_bundle_sha256=SHA["5"],
            motion_instance_v2_sha256=SHA["6"],
            reviewed_motion_bundle_sha256=SHA["7"],
        )
        run_capture.assert_called_once_with(
            preview,
            runtime_root=Path("licensed-runtime"),
            browser_executable=Path("chrome.exe"),
            license_acknowledged=True,
        )
        store_type.assert_called_once_with(Path("state"))
        store_type.return_value.publish.assert_called_once_with(
            self.fixture.capture
        )
        self.assertEqual("blocked", result.release_gate_status)
        self.assertTrue(result.release_gate_reason_codes)

    @patch("autospine_workbench.p10_runtime_capture_commands.BodySwayRuntimeCaptureStore")
    @patch("autospine_workbench.p10_runtime_capture_commands.run_p10_body_sway_runtime_capture")
    @patch("autospine_workbench.p10_runtime_capture_commands.compile_body_sway_preview_command")
    def test_all_public_fields_are_rebound_before_store(
        self, compile_preview, run_capture, store_type,
    ):
        base = self.fixture.runner_result()
        preview = Mock(temporary_preview_sha256=base.temporary_preview_sha256)
        compile_preview.return_value = preview
        crosswires = (
            {"runtime_capture_sha256": "0" * 64},
            {"artifact_set_sha256": "0" * 64},
            {"temporary_preview_sha256": "0" * 64},
            {"case_count": base.case_count - 1},
            {"browser_family": "google-chrome"},
            {"browser_reported_version": "140.0.0.2"},
            {"browser_reported_version": "140.0.1"},
        )
        for changes in crosswires:
            with self.subTest(changes=changes):
                run_capture.return_value = self.fixture.runner_result(**changes)
                with self.assertRaises(P10RuntimeCaptureCommandError):
                    self.call()
                store_type.assert_not_called()

    @patch("autospine_workbench.p10_runtime_capture_commands.BodySwayRuntimeCaptureStore")
    @patch("autospine_workbench.p10_runtime_capture_commands.run_p10_body_sway_runtime_capture")
    @patch("autospine_workbench.p10_runtime_capture_commands.compile_body_sway_preview_command")
    def test_private_status_and_project_crosswires_are_rejected(
        self, compile_preview, run_capture, store_type,
    ):
        base = self.fixture.runner_result()
        preview = Mock(temporary_preview_sha256=base.temporary_preview_sha256)
        compile_preview.return_value = preview
        document = self.fixture.capture.document
        document["status"] = "reviewed"
        tampered = BodySwayRuntimeCapture(
            json.dumps(document, sort_keys=True, separators=(",", ":")),
            tuple(self.fixture.capture.capture_bytes.items()),
        )
        run_capture.return_value = self.fixture.runner_result(
            _capture=tampered
        )
        with self.assertRaises(P10RuntimeCaptureCommandError):
            self.call()
        store_type.assert_not_called()

        run_capture.return_value = base
        with self.assertRaises(P10RuntimeCaptureCommandError):
            self.call(project_id="other-project")
        store_type.assert_not_called()

    @patch("autospine_workbench.p10_runtime_capture_commands.BodySwayRuntimeCaptureStore")
    @patch("autospine_workbench.p10_runtime_capture_commands.run_p10_body_sway_runtime_capture")
    @patch("autospine_workbench.p10_runtime_capture_commands.compile_body_sway_preview_command")
    def test_crosswired_publication_is_rejected(
        self, compile_preview, run_capture, store_type,
    ):
        base = self.fixture.runner_result()
        compile_preview.return_value = Mock(
            temporary_preview_sha256=base.temporary_preview_sha256
        )
        run_capture.return_value = base
        store_type.return_value.publish.return_value = (
            self.fixture.publication(manifest_sha256="0" * 64)
        )
        with self.assertRaisesRegex(
            P10RuntimeCaptureCommandError, "identity differs",
        ):
            self.call()


if __name__ == "__main__":
    unittest.main()
