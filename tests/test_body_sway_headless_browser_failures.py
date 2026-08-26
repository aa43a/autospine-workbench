from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import autospine_workbench.body_sway_headless_browser as subject
import autospine_workbench.body_sway_headless_browser_inputs as inputs
from autospine_workbench.body_sway_headless_browser import (
    BodySwayHeadlessBrowserError,
    run_body_sway_headless_capture_case,
)
from tests.body_sway_headless_browser_support import (
    CAPTURED,
    CASE_ID,
    PENDING,
    RUNTIME_ERROR,
    URL,
    FakeProcess,
    HeadlessBrowserFixture,
    collector,
)


class BodySwayHeadlessBrowserFailureTests(
    HeadlessBrowserFixture, unittest.TestCase
):
    def test_process_zero_without_post_is_not_success(self):
        process = FakeProcess(return_code=0)
        with self.assertRaisesRegex(
            BodySwayHeadlessBrowserError, "without posting"
        ):
            self.run_case(process, collector(PENDING, PENDING))
        self.assertFalse(process.terminated)

    def test_zero_exit_rechecks_a_concurrent_capture_post(self):
        process = FakeProcess(return_code=0)
        self.run_case(process, collector(PENDING, PENDING, CAPTURED))
        self.assertFalse(process.terminated)

    def test_nonzero_exit_is_failure_even_after_capture_post(self):
        process = FakeProcess(return_code=7)
        with self.assertRaisesRegex(
            BodySwayHeadlessBrowserError, "non-zero"
        ):
            self.run_case(process, collector(PENDING, CAPTURED))

    def test_runtime_error_is_terminal_failure_and_process_is_stopped(self):
        process = FakeProcess()
        with self.assertRaisesRegex(
            BodySwayHeadlessBrowserError, "runtime reported"
        ):
            self.run_case(process, collector(PENDING, RUNTIME_ERROR))
        self.assertTrue(process.terminated)

    def test_timeout_is_bounded_and_process_is_stopped(self):
        process = FakeProcess()
        with patch.object(subject, "CAPTURE_TIMEOUT_SECONDS", 0.0):
            with self.assertRaisesRegex(
                BodySwayHeadlessBrowserError, "timed out"
            ):
                self.run_case(process, collector(PENDING, PENDING))
        self.assertTrue(process.terminated)

    def test_combined_output_overflow_kills_and_fails(self):
        process = FakeProcess(
            b"x" * (subject.MAX_BROWSER_OUTPUT_BYTES + 1)
        )
        with self.assertRaisesRegex(
            BodySwayHeadlessBrowserError, "output exceeded"
        ):
            self.run_case(process, collector(PENDING, PENDING))
        self.assertTrue(process.killed)

    def test_capture_then_delayed_output_overflow_is_still_failure(self):
        process = FakeProcess(
            b"x" * (subject.MAX_BROWSER_OUTPUT_BYTES + 1),
            delayed_output=True,
        )
        with self.assertRaisesRegex(
            BodySwayHeadlessBrowserError, "output exceeded"
        ):
            self.run_case(process, collector(PENDING, CAPTURED))
        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)

    def test_stubborn_success_process_is_killed_after_terminate_grace(self):
        process = FakeProcess(terminate_stalls=True)
        self.run_case(process, collector(PENDING, CAPTURED))
        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)
        self.assertEqual(
            [subject.TERMINATE_GRACE_SECONDS, subject.KILL_GRACE_SECONDS],
            process.wait_timeouts,
        )

    def test_primary_error_is_not_masked_by_cleanup_failure(self):
        process = FakeProcess(terminate_stalls=True, kill_stalls=True)
        with self.assertRaisesRegex(
            BodySwayHeadlessBrowserError, "runtime reported"
        ):
            self.run_case(process, collector(PENDING, RUNTIME_ERROR))
        self.assertTrue(process.killed)

    def test_launch_error_is_normalized(self):
        with patch.object(subject.subprocess, "Popen", side_effect=OSError("no")):
            with self.assertRaisesRegex(
                BodySwayHeadlessBrowserError, "could not be started"
            ):
                run_body_sway_headless_capture_case(
                    self.browser,
                    URL,
                    self.profile,
                    collector(PENDING),
                    CASE_ID,
                )

    def test_rejects_non_loopback_or_wrong_case_url_before_launch(self):
        invalid = (
            "https://127.0.0.1:49152/capture/setup",
            "http://example.com:49152/capture/setup",
            "http://127.0.0.1:49152/capture/combined",
            "http://127.0.0.1:49152/capture/setup?q=1",
        )
        for url in invalid:
            with self.subTest(url=url), patch.object(
                subject.subprocess, "Popen"
            ) as launch:
                with self.assertRaises(BodySwayHeadlessBrowserError):
                    run_body_sway_headless_capture_case(
                        self.browser,
                        url,
                        self.profile,
                        collector(PENDING),
                        CASE_ID,
                    )
                launch.assert_not_called()

    def test_rejects_reused_profile_and_preterminal_case(self):
        (self.profile / "used").write_text("state", encoding="utf-8")
        with patch.object(subject.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(
                BodySwayHeadlessBrowserError, "fresh and empty"
            ):
                run_body_sway_headless_capture_case(
                    self.browser,
                    URL,
                    self.profile,
                    collector(PENDING),
                    CASE_ID,
                )
            launch.assert_not_called()
        (self.profile / "used").unlink()
        with self.assertRaisesRegex(
            BodySwayHeadlessBrowserError, "already has a terminal"
        ):
            run_body_sway_headless_capture_case(
                self.browser,
                URL,
                self.profile,
                collector(CAPTURED),
                CASE_ID,
            )

    def test_rejects_aliased_profile_parent_before_launch(self):
        real_alias_check = inputs._is_alias

        def parent_is_alias(path, metadata):
            return path == self.profile.parent or real_alias_check(path, metadata)

        with patch.object(
            inputs, "_is_alias", side_effect=parent_is_alias
        ), patch.object(subject.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(
                BodySwayHeadlessBrowserError, "parent directories"
            ):
                run_body_sway_headless_capture_case(
                    self.browser,
                    URL,
                    self.profile,
                    collector(PENDING),
                    CASE_ID,
                )
            launch.assert_not_called()

    def test_timeout_constant_never_exceeds_forty_seconds(self):
        self.assertGreater(subject.CAPTURE_TIMEOUT_SECONDS, 0)
        self.assertLessEqual(subject.CAPTURE_TIMEOUT_SECONDS, 40)


if __name__ == "__main__":
    unittest.main()
