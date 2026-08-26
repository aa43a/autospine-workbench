"""Trusted orchestration tests for the automatic P10 headless capture runner."""

from __future__ import annotations

from dataclasses import replace
import hashlib
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
    BrowserExecutableSnapshotError,
)
import autospine_workbench.p10_runtime_capture_runner as subject  # noqa: E402
from autospine_workbench.p10_preview_commands import (  # noqa: E402
    P10PreviewCommandResult,
)
from autospine_workbench.p10_preview_replay_spec import (  # noqa: E402
    P10PreviewReplaySpec,
)
from autospine_workbench.p10_runtime_capture_runner import (  # noqa: E402
    P10RuntimeCaptureRunnerError,
    run_p10_body_sway_runtime_capture,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    RuntimeCaptureFixture,
    capture_png,
    fake_runtime_profile,
)


class P10RuntimeCaptureRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = RuntimeCaptureFixture(cls.root)
        cls.png = capture_png()
        cls.browser = BrowserExecutableSnapshot(
            path=str(cls.root / "chrome.exe"),
            family="chromium", reported_version="128.0.6613.0",
            version_output_sha256=hashlib.sha256(
                b"Chromium 128.0.6613.0\n"
            ).hexdigest(),
            executable_sha256="b" * 64, size_bytes=4096,
        )
        preview = cls.fixture.preview
        source = preview.document["source"]
        dummy = "c" * 64
        spec = P10PreviewReplaySpec(
            state_root=cls.root,
            project_id=preview.document["project_id"],
            candidates_path=cls.root / "candidates.json",
            decision_path=cls.root / "decision.json",
            probe_report_path=cls.root / "report.json",
            layer_manifest_sha256=dummy,
            p3_rig_sha256=dummy,
            p3_bundle_sha256=dummy,
            motion_instance_sha256=dummy,
            motion_retarget_bundle_sha256=dummy,
            motion_instance_v2_sha256=dummy,
            reviewed_motion_bundle_sha256=dummy,
        )
        cls.preview_result = P10PreviewCommandResult(
            input_paths=(),
            idle_behavior_candidates_sha256=
                source["idle_behavior_candidates_sha256"],
            idle_behavior_decision_sha256=
                source["idle_behavior_decision_sha256"],
            body_sway_probe_report_sha256=
                source["body_sway_probe_report_sha256"],
            temporary_preview_sha256=preview.sha256,
            artifact_set_sha256=preview.artifact_set_sha256,
            _preview=preview,
            _inputs=cls.fixture.preview_fixture.preview_inputs,
            _replay_spec=spec,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_all_cases_require_collector_capture_and_final_rechecks(self):
        profiles, urls, cases = [], [], []

        def capture_case(browser, url, profile, collector, case_id):
            self.assertEqual(self.browser, browser)
            self.assertTrue(profile.is_dir())
            profiles.append(profile)
            urls.append(url)
            cases.append(case_id)
            collector.record_capture(case_id, self.png, device_pixel_ratio=1)

        with self._boundaries(capture_case) as mocks:
            actual_compile = subject.compile_body_sway_runtime_capture
            actual_replay = subject.require_exact_body_sway_runtime_capture

            def compile_locked(*args):
                self.assertTrue(mocks["lease"].active)
                return actual_compile(*args)

            def replay_locked(*args):
                self.assertTrue(mocks["lease"].active)
                return actual_replay(*args)

            with patch.object(
                subject, "compile_body_sway_runtime_capture",
                side_effect=compile_locked,
            ), patch.object(
                subject, "require_exact_body_sway_runtime_capture",
                side_effect=replay_locked,
            ):
                result = run_p10_body_sway_runtime_capture(
                    self.preview_result, runtime_root=self.root / "runtime",
                    browser_executable=self.root / "chrome.exe",
                    license_acknowledged=True,
                )
        self.assertEqual(19, result.case_count)
        self.assertEqual("captured_unreviewed", result.document["status"])
        self.assertEqual(
            self.fixture.preview.sha256, result.temporary_preview_sha256
        )
        self.assertEqual(19, mocks["driver"].call_count)
        self.assertEqual(20, mocks["browser_recheck"].call_count)
        self.assertEqual(2, mocks["preview_replay"].call_count)
        self.assertEqual(2, mocks["runtime_load"].call_count)
        self.assertEqual(list(self.fixture.sessions.case_ids), cases)
        self.assertEqual(19, len(set(urls)))
        self.assertTrue(all(url.startswith("http://127.0.0.1:") for url in urls))
        self.assertTrue(all(not path.exists() for path in profiles))
        self.assertTrue(mocks["lease"].closed)

    def test_process_success_without_post_is_not_success(self):
        with self._boundaries(lambda *_args: None), self.assertRaisesRegex(
            P10RuntimeCaptureRunnerError, "without the exact collector"
        ):
            run_p10_body_sway_runtime_capture(
                self.preview_result, runtime_root=self.root / "runtime",
                browser_executable=self.root / "chrome.exe",
                license_acknowledged=True,
            )

    def test_runtime_error_report_prevents_contract(self):
        def runtime_error(_browser, _url, _profile, collector, case_id):
            collector.record_error(case_id, "WebGL initialization failed")

        with self._boundaries(runtime_error), self.assertRaisesRegex(
            P10RuntimeCaptureRunnerError, "without the exact collector"
        ):
            run_p10_body_sway_runtime_capture(
                self.preview_result, runtime_root=self.root / "runtime",
                browser_executable=self.root / "chrome.exe",
                license_acknowledged=True,
            )

    def test_future_case_prepost_is_not_accepted_as_progress(self):
        called = False

        def prepost(_browser, _url, _profile, collector, case_id):
            nonlocal called
            collector.record_capture(case_id, self.png, device_pixel_ratio=1)
            if not called:
                called = True
                collector.record_capture(
                    collector.case_ids[1], self.png, device_pixel_ratio=1
                )

        with self._boundaries(prepost), self.assertRaisesRegex(
            P10RuntimeCaptureRunnerError, "exact completed prefix"
        ):
            run_p10_body_sway_runtime_capture(
                self.preview_result, runtime_root=self.root / "runtime",
                browser_executable=self.root / "chrome.exe",
                license_acknowledged=True,
            )

    def test_browser_or_persisted_inputs_changing_fail_closed(self):
        def capture_case(_browser, _url, _profile, collector, case_id):
            collector.record_capture(case_id, self.png, device_pixel_ratio=1)

        with self._boundaries(capture_case) as mocks:
            mocks["browser_recheck"].side_effect = (
                BrowserExecutableSnapshotError("changed")
            )
            with self.assertRaisesRegex(
                P10RuntimeCaptureRunnerError, "changed"
            ):
                run_p10_body_sway_runtime_capture(
                    self.preview_result, runtime_root=self.root / "runtime",
                    browser_executable=self.root / "chrome.exe",
                    license_acknowledged=True,
                )

        changed = replace(
            self.fixture.runtime, javascript_sha256="d" * 64
        )
        with self._boundaries(capture_case) as mocks:
            mocks["runtime_load"].side_effect = [
                self.fixture.runtime, changed,
            ]
            with self.assertRaisesRegex(
                P10RuntimeCaptureRunnerError, "runtime package changed"
            ):
                run_p10_body_sway_runtime_capture(
                    self.preview_result, runtime_root=self.root / "runtime",
                    browser_executable=self.root / "chrome.exe",
                    license_acknowledged=True,
                )

    def test_rejects_non_preview_command_result_before_side_effects(self):
        with self.assertRaises(P10RuntimeCaptureRunnerError):
            run_p10_body_sway_runtime_capture(
                {}, runtime_root=self.root / "runtime",
                browser_executable=self.root / "chrome.exe",
                license_acknowledged=True,
            )

    def test_license_rejection_precedes_every_boundary(self):
        boundaries = (
            "LockedBrowserExecutableLease",
            "require_exact_preview_for_mount",
            "require_runtime_package",
            "build_body_sway_runtime_capture_harness",
            "run_body_sway_headless_capture_case",
        )
        patches = [
            patch(
                f"autospine_workbench.p10_runtime_capture_runner.{name}"
            )
            for name in boundaries
        ]
        patches.extend([
            patch(
                "autospine_workbench.locked_browser_executable_lease."
                "snapshot_browser_executable"
            ),
            patch(
                "autospine_workbench.body_sway_headless_browser."
                "subprocess.Popen"
            ),
        ])
        mocks = [item.start() for item in patches]
        try:
            for value in (False, None, 1, "true"):
                with self.subTest(value=value), self.assertRaisesRegex(
                    P10RuntimeCaptureRunnerError,
                    "license acknowledgement",
                ):
                    run_p10_body_sway_runtime_capture(
                        object(), runtime_root=object(),
                        browser_executable=object(),
                        license_acknowledged=value,
                    )
            for boundary in mocks:
                boundary.assert_not_called()
        finally:
            for item in reversed(patches):
                item.stop()

    def test_non_windows_rejection_precedes_every_capture_boundary(self):
        boundaries = (
            "LockedBrowserExecutableLease",
            "require_exact_preview_for_mount",
            "require_runtime_package",
            "build_body_sway_runtime_capture_harness",
            "run_body_sway_headless_capture_case",
        )
        patches = [patch.object(subject, name) for name in boundaries]
        patches.extend([
            patch(
                "autospine_workbench.locked_browser_executable_lease."
                "snapshot_browser_executable"
            ),
            patch(
                "autospine_workbench.body_sway_headless_browser."
                "subprocess.Popen"
            ),
        ])
        mocks = [item.start() for item in patches]
        try:
            with patch.object(subject.os, "name", "posix"), \
                    self.assertRaisesRegex(
                        P10RuntimeCaptureRunnerError, "only on Windows"
                    ):
                run_p10_body_sway_runtime_capture(
                    self.preview_result,
                    runtime_root=self.root / "runtime",
                    browser_executable=self.root / "chrome.exe",
                    license_acknowledged=True,
                )
            for boundary in mocks:
                boundary.assert_not_called()
        finally:
            for item in reversed(patches):
                item.stop()

    def test_exact_preview_result_check_precedes_platform_check(self):
        with patch.object(subject.os, "name", "posix"), \
                self.assertRaisesRegex(
                    P10RuntimeCaptureRunnerError, "exact P10 preview"
                ):
            run_p10_body_sway_runtime_capture(
                {}, runtime_root=self.root / "runtime",
                browser_executable=self.root / "chrome.exe",
                license_acknowledged=True,
            )

    def _boundaries(self, capture_case):
        fixture, browser = self.fixture, self.browser

        class BoundaryContext:
            def __enter__(inner):
                inner.pin = fake_runtime_profile()
                inner.pin.__enter__()
                inner.lease = _BrowserLease(browser)

                def guarded_capture(*args):
                    if not inner.lease.active:
                        raise AssertionError(
                            "browser file lease is not active during capture"
                        )
                    return capture_case(*args)

                inner.stack = [
                    patch(
                        "autospine_workbench.p10_runtime_capture_runner."
                        "LockedBrowserExecutableLease",
                        return_value=inner.lease,
                    ),
                    patch(
                        "autospine_workbench.p10_runtime_capture_runner."
                        "require_exact_preview_for_mount",
                        side_effect=[fixture.preview, fixture.preview],
                    ),
                    patch(
                        "autospine_workbench.p10_runtime_capture_runner."
                        "require_runtime_package",
                        side_effect=[fixture.runtime, fixture.runtime],
                    ),
                    patch(
                        "autospine_workbench.p10_runtime_capture_runner."
                        "recheck_browser_executable", return_value=browser,
                    ),
                    patch(
                        "autospine_workbench.p10_runtime_capture_runner."
                        "run_body_sway_headless_capture_case",
                        side_effect=guarded_capture,
                    ),
                ]
                values = [item.start() for item in inner.stack]
                inner.mocks = dict(zip((
                    "browser_lease", "preview_replay", "runtime_load",
                    "browser_recheck", "driver",
                ), values, strict=True))
                inner.mocks["lease"] = inner.lease
                return inner.mocks

            def __exit__(inner, kind, value, traceback):
                for item in reversed(inner.stack):
                    item.stop()
                inner.pin.__exit__(kind, value, traceback)

        return BoundaryContext()


class _BrowserLease:
    def __init__(self, browser) -> None:
        self.browser = browser
        self.active = False
        self.closed = False

    def __enter__(self):
        self.active = True
        return self.browser

    def __exit__(self, kind, value, traceback):
        self.active = False
        self.closed = True


if __name__ == "__main__":
    unittest.main()
