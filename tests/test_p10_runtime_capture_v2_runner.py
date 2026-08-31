"""Trusted orchestration tests for package-centric Preview v2 capture."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.browser_executable_snapshot import (  # noqa: E402
    BrowserExecutableSnapshot,
)
from autospine_workbench.browser_version_identity import (  # noqa: E402
    browser_version_identity_sha256,
)
from autospine_workbench.p10_preview_v2_commands import (  # noqa: E402
    P10PreviewV2CommandResult,
)
from autospine_workbench.p10_runtime_capture_v2_runner import (  # noqa: E402
    P10RuntimeCaptureV2RunnerError,
    run_p10_body_sway_runtime_capture_v2,
)
from autospine_workbench.p10_runtime_environment import (  # noqa: E402
    P10RuntimeEnvironment,
)
import autospine_workbench.p10_runtime_capture_v2_runner as subject  # noqa: E402
from autospine_workbench.temporary_body_sway_preview_v2 import (  # noqa: E402
    compile_temporary_body_sway_preview_v2,
)
from tests.body_sway_preview_v2_helpers import PreviewV2Fixture  # noqa: E402
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    RUNTIME_CSS_SHA,
    RUNTIME_JS_SHA,
    capture_png,
    fake_runtime,
)
from tests.test_temporary_body_sway_preview_v2 import (  # noqa: E402
    _patched_source,
    _source_images,
)


@contextmanager
def _runtime_profile():
    modules = (
        "autospine_workbench.body_sway_runtime_capture_session_v2",
        "autospine_workbench.body_sway_runtime_capture_session_v2_validation",
        "autospine_workbench.body_sway_runtime_capture_v2_fields",
    )
    patches = []
    for module in modules:
        patches.extend((
            patch(module + ".SPINE_PLAYER_JAVASCRIPT_SHA256", RUNTIME_JS_SHA),
            patch(module + ".SPINE_PLAYER_STYLESHEET_SHA256", RUNTIME_CSS_SHA),
        ))
    for item in patches:
        item.start()
    try:
        yield
    finally:
        for item in reversed(patches):
            item.stop()


class P10RuntimeCaptureV2RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        fixture = PreviewV2Fixture(cls.root / "preview")
        inputs = fixture.admit()
        with _patched_source(_source_images(fixture.fixture.mesh.rig)):
            cls.preview = compile_temporary_body_sway_preview_v2(
                inputs, fixture.fixture.mesh,
            )
        source = cls.preview.document["source"]
        cls.preview_result = P10PreviewV2CommandResult(
            package_id="package-001",
            project_id=cls.preview.document["project_id"],
            clip_id=cls.preview.document["clip_id"],
            temporary_preview_v2_sha256=cls.preview.sha256,
            artifact_set_sha256=cls.preview.artifact_set_sha256,
            capture_framing_candidate_sha256=
                source["capture_framing_candidate_sha256"],
            capture_framing_decision_sha256=
                source["capture_framing_decision_sha256"],
            capture_framing_revision=source["capture_framing_revision"],
            case_count=len(cls.preview.document["capture_plan"]["cases"]),
            _preview=cls.preview,
            _workspace_root=cls.root,
            _state_root=cls.root,
        )
        runtime = replace(
            fake_runtime(cls.root / "runtime"),
            package_json_sha256="a" * 64,
            license_sha256="b" * 64,
        )
        version = "128.0.6613.0"
        cls.browser = BrowserExecutableSnapshot(
            path=str(cls.root / "chrome.exe"),
            family="chromium", reported_version=version,
            version_output_sha256=browser_version_identity_sha256(
                "chromium", version,
            ),
            executable_sha256="c" * 64, size_bytes=4096,
        )
        cls.environment = P10RuntimeEnvironment(runtime, cls.browser)
        cls.png = capture_png()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_all_cases_emit_progress_and_produce_outer_execution(self):
        progress, cases = [], []

        def capture(_browser, _url, _profile, collector, case_id):
            cases.append(case_id)
            collector.record_capture(case_id, self.png, device_pixel_ratio=1)

        with self._boundaries(capture) as mocks, _runtime_profile():
            result = run_p10_body_sway_runtime_capture_v2(
                self.preview_result,
                environment=self.environment,
                license_acknowledged=True,
                run_confirmed=True,
                on_progress=progress.append,
            )
        self.assertEqual(self.preview_result.case_count, result.case_count)
        self.assertEqual("captured_unreviewed", result.execution.document["status"])
        self.assertTrue(result.execution.document["runtime"]["license_acknowledged"])
        self.assertEqual(self.preview_result.case_count, len(cases))
        self.assertEqual("running", progress[0].state)
        self.assertEqual(0, progress[0].completed_case_count)
        self.assertEqual("completed", progress[-1].state)
        self.assertEqual(result.case_count, progress[-1].completed_case_count)
        self.assertEqual(result.case_count + 2, len(progress))
        self.assertEqual(result.case_count + 1, mocks["recheck"].call_count)
        self.assertTrue(mocks["lease"].closed)

    def test_missing_confirmations_precede_every_execution_boundary(self):
        names = (
            "LockedBrowserExecutableLease", "require_exact_preview_v2_for_mount",
            "require_runtime_package", "build_body_sway_runtime_capture_harness_v2",
            "run_body_sway_headless_capture_case",
        )
        patches = [patch.object(subject, name) for name in names]
        mocks = [item.start() for item in patches]
        try:
            for license_value, run_value in ((False, True), (True, False)):
                with self.subTest(
                    license=license_value, run=run_value,
                ), self.assertRaises(P10RuntimeCaptureV2RunnerError):
                    run_p10_body_sway_runtime_capture_v2(
                        object(), environment=object(),
                        license_acknowledged=license_value,
                        run_confirmed=run_value,
                    )
            for boundary in mocks:
                boundary.assert_not_called()
        finally:
            for item in reversed(patches):
                item.stop()

    def test_process_success_without_callback_and_cancellation_fail_closed(self):
        with self._boundaries(lambda *_args: None), _runtime_profile(), \
                self.assertRaisesRegex(
                    P10RuntimeCaptureV2RunnerError, "completed collector prefix",
                ):
            run_p10_body_sway_runtime_capture_v2(
                self.preview_result, environment=self.environment,
                license_acknowledged=True, run_confirmed=True,
            )

        stopped = False

        def capture(_browser, _url, _profile, collector, case_id):
            nonlocal stopped
            collector.record_capture(case_id, self.png, device_pixel_ratio=1)
            stopped = True

        with self._boundaries(capture), _runtime_profile(), \
                self.assertRaisesRegex(
                    P10RuntimeCaptureV2RunnerError, "cancelled",
                ):
            run_p10_body_sway_runtime_capture_v2(
                self.preview_result, environment=self.environment,
                license_acknowledged=True, run_confirmed=True,
                is_cancelled=lambda: stopped,
            )

    def _boundaries(self, capture_case):
        test = self

        class Boundaries:
            def __enter__(inner):
                inner.lease = _BrowserLease(test.browser)
                inner.patches = (
                    patch.object(subject, "LockedBrowserExecutableLease",
                                 return_value=inner.lease),
                    patch.object(subject, "require_exact_preview_v2_for_mount",
                                 side_effect=[test.preview, test.preview]),
                    patch.object(subject, "require_runtime_package",
                                 side_effect=[test.environment.runtime,
                                              test.environment.runtime]),
                    patch.object(subject, "recheck_browser_executable",
                                 return_value=test.browser),
                    patch.object(subject, "run_body_sway_headless_capture_case",
                                 side_effect=capture_case),
                )
                values = [item.start() for item in inner.patches]
                inner.mocks = dict(zip((
                    "lease_factory", "preview", "runtime", "recheck", "driver",
                ), values, strict=True))
                inner.mocks["lease"] = inner.lease
                return inner.mocks

            def __exit__(inner, kind, value, traceback):
                for item in reversed(inner.patches):
                    item.stop()

        return Boundaries()


class _BrowserLease:
    def __init__(self, browser):
        self.browser = browser
        self.closed = False

    def __enter__(self):
        return self.browser

    def __exit__(self, kind, value, traceback):
        self.closed = True


if __name__ == "__main__":
    unittest.main()
