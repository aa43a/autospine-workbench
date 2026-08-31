"""Package command tests for official Preview v2 execution publication."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import autospine_workbench.p10_runtime_capture_v2_commands as subject  # noqa: E402
from autospine_workbench.p10_runtime_capture_v2_commands import (  # noqa: E402
    P10RuntimeCaptureV2CommandError,
    execute_p10_runtime_capture_v2_for_package,
)
from autospine_workbench.project_store import ProjectStore  # noqa: E402


class P10RuntimeCaptureV2CommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.store = ProjectStore(root / "workspace", state_root=root / "state")
        self.preview_sha = "1" * 64
        self.artifact_sha = "2" * 64
        self.bundle_sha = "3" * 64
        self.execution_sha = "4" * 64
        self.capture_sha = "5" * 64
        self.expected_p10 = {
            "candidate_sha256": "6" * 64,
            "decision_sha256": "7" * 64,
            "revision": 1,
        }
        self.expected_framing = {
            "candidate_sha256": "8" * 64,
            "decision_sha256": "9" * 64,
            "revision": 2,
        }
        self.preview = SimpleNamespace(
            sha256=self.preview_sha,
            document={"source": {"current_p10_1_head": self.expected_p10}},
            capture_framing_candidate_sha256=
                self.expected_framing["candidate_sha256"],
            capture_framing_decision_sha256=
                self.expected_framing["decision_sha256"],
            capture_framing_revision=self.expected_framing["revision"],
        )
        self.execution = SimpleNamespace(
            sha256=self.execution_sha,
            document={"source": {
                "runtime_capture_v2_sha256": self.capture_sha,
            }},
        )
        self.capture = SimpleNamespace(
            execution=self.execution,
            project_id="project-001",
            clip_id="clip-001",
            temporary_preview_v2_sha256=self.preview_sha,
            runtime_execution_sha256=self.execution_sha,
            runtime_capture_v2_sha256=self.capture_sha,
            artifact_set_sha256=self.artifact_sha,
            browser_family="google-chrome",
            browser_reported_version="152.0.0.0",
            case_count=43,
        )
        self.published = SimpleNamespace(
            project_id="project-001",
            temporary_preview_v2_sha256=self.preview_sha,
            execution_sha256=self.execution_sha,
            runtime_capture_v2_sha256=self.capture_sha,
            artifact_set_sha256=self.artifact_sha,
            bundle_sha256=self.bundle_sha,
            reused=False,
        )
        self.verified = SimpleNamespace(
            project_id="project-001",
            temporary_preview_v2_sha256=self.preview_sha,
            bundle_sha256=self.bundle_sha,
            artifact_set_sha256=self.artifact_sha,
            execution=self.execution,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_exact_publish_and_readback_returns_path_free_addresses(self):
        with self._boundaries() as calls:
            result = execute_p10_runtime_capture_v2_for_package(
                self.store, "package-001", environment=object(),
                expected_p10_1=self.expected_p10,
                expected_framing=self.expected_framing,
                license_acknowledged=True, run_confirmed=True,
            )
        document = result.public_document()
        self.assertEqual("captured_unreviewed", document["status"])
        self.assertEqual(self.bundle_sha, document["addresses"]["bundle_sha256"])
        self.assertEqual(self.artifact_sha,
                         document["addresses"]["artifact_set_sha256"])
        self.assertNotIn("path", repr(document).lower())
        calls["runner"].assert_called_once()
        calls["publish"].assert_called_once_with(self.execution)
        calls["load"].assert_called_once_with(
            "project-001", self.preview_sha,
            self.bundle_sha, self.artifact_sha,
        )

    def test_divergent_readback_fails_closed(self):
        changed = SimpleNamespace(**vars(self.verified))
        changed.bundle_sha256 = "6" * 64
        with self._boundaries(verified=changed), self.assertRaisesRegex(
            P10RuntimeCaptureV2CommandError, "exact readback",
        ):
            execute_p10_runtime_capture_v2_for_package(
                self.store, "package-001", environment=object(),
                expected_p10_1=self.expected_p10,
                expected_framing=self.expected_framing,
                license_acknowledged=True, run_confirmed=True,
            )

    def test_head_drift_before_or_after_runner_fails_closed(self):
        stale = {**self.expected_framing, "decision_sha256": "0" * 64}
        with self._boundaries() as calls, self.assertRaisesRegex(
            P10RuntimeCaptureV2CommandError, "head is stale",
        ):
            execute_p10_runtime_capture_v2_for_package(
                self.store, "package-001", environment=object(),
                expected_p10_1=self.expected_p10,
                expected_framing=stale,
                license_acknowledged=True, run_confirmed=True,
            )
        calls["runner"].assert_not_called()

        with self._boundaries(current=SimpleNamespace(sha256="7" * 64)), \
                self.assertRaisesRegex(
                    P10RuntimeCaptureV2CommandError, "changed before",
                ):
            execute_p10_runtime_capture_v2_for_package(
                self.store, "package-001", environment=object(),
                expected_p10_1=self.expected_p10,
                expected_framing=self.expected_framing,
                license_acknowledged=True, run_confirmed=True,
            )

    def test_non_store_is_rejected_before_boundaries(self):
        with patch.object(subject, "compile_body_sway_preview_v2_for_package") \
                as compile_preview, self.assertRaises(
                    P10RuntimeCaptureV2CommandError,
                ):
            execute_p10_runtime_capture_v2_for_package(
                object(), "package-001", environment=object(),
                expected_p10_1=self.expected_p10,
                expected_framing=self.expected_framing,
                license_acknowledged=True, run_confirmed=True,
            )
        compile_preview.assert_not_called()

    def _boundaries(self, *, verified=None, current=None):
        test = self

        class Boundaries:
            def __enter__(inner):
                store_instance = SimpleNamespace()
                reader_instance = SimpleNamespace()
                inner.patches = (
                    patch.object(
                        subject, "compile_body_sway_preview_v2_for_package",
                        return_value=test.preview,
                    ),
                    patch.object(
                        subject, "run_p10_body_sway_runtime_capture_v2",
                        return_value=test.capture,
                    ),
                    patch.object(subject, "BodySwayRuntimeExecutionStore",
                                 return_value=store_instance),
                    patch.object(subject, "VerifiedBodySwayRuntimeExecutionReader",
                                 return_value=reader_instance),
                    patch.object(subject, "require_exact_preview_v2_for_mount",
                                 return_value=current or test.preview),
                )
                values = [item.start() for item in inner.patches]
                from unittest.mock import Mock
                store_instance.publish = Mock(return_value=test.published)
                reader_instance.load = Mock(return_value=verified or test.verified)
                inner.calls = {
                    "runner": values[1],
                    "publish": store_instance.publish,
                    "load": reader_instance.load,
                }
                return inner.calls

            def __exit__(inner, kind, value, traceback):
                for item in reversed(inner.patches):
                    item.stop()

        return Boundaries()


if __name__ == "__main__":
    unittest.main()
