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
from autospine_workbench.body_sway_headless_browser import (
    BodySwayHeadlessBrowserError,
    run_body_sway_headless_capture_case,
)
from autospine_workbench.body_sway_runtime_capture_profile import (
    BROWSER_FIXED_ARGUMENTS,
)
from autospine_workbench.windows_process_job import (
    KillOnCloseProcessJob,
    WindowsProcessJobError,
)
from autospine_workbench.windows_process_image import WindowsProcessImageError
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


class _OwnedJob(KillOnCloseProcessJob):
    def __init__(self, process, close_error=None):
        super().__init__(1, object())
        self.process = process
        self.close_error = close_error
        self.closed = False

    def close(self):
        self.closed = True
        if self.close_error:
            raise self.close_error
        self.process.return_code = -1
        self.process.stop_event.set()
        self._handle = None


class _SlowExitOwnedJob(_OwnedJob):
    """Close the owned tree, but model a late-signalling Chromium root."""

    def close(self):
        self.closed = True
        self._handle = None


class BodySwayHeadlessBrowserTests(HeadlessBrowserFixture, unittest.TestCase):
    def test_launches_fixed_loopback_case_with_fresh_profile(self):
        process = FakeProcess(b"bounded merged browser output")
        result, launch = self.run_case(process, collector(PENDING, CAPTURED))

        self.assertIsNone(result)
        command = launch.call_args.args[0]
        self.assertEqual(self.browser.path, command[0])
        self.assertEqual(
            list(BROWSER_FIXED_ARGUMENTS),
            command[1 : 1 + len(BROWSER_FIXED_ARGUMENTS)],
        )
        self.assertIn(f"--user-data-dir={self.profile}", command)
        self.assertEqual(["--dump-dom", URL], command[-2:])
        options = launch.call_args.kwargs
        self.assertIs(subject.subprocess.DEVNULL, options["stdin"])
        self.assertIs(subject.subprocess.PIPE, options["stdout"])
        self.assertIs(subject.subprocess.STDOUT, options["stderr"])
        self.assertFalse(options["shell"])
        self.assertTrue(options["close_fds"])
        self.assertIn("creationflags", options)
        self.assertIn("--no-proxy-server", command)
        self.assertIn("--no-sandbox", command)
        self.assertTrue(process.terminated)
        self.assertFalse(process.killed)

    def test_job_is_attached_before_reader_and_closed_before_return(self):
        process = FakeProcess()
        job = _OwnedJob(process)
        events = []

        def attach(actual_process):
            self.assertIs(process, actual_process)
            events.append("attach")
            return job

        class RecordingThread(subject.threading.Thread):
            def start(self):
                events.append("reader")
                return super().start()

        with patch.object(subject.subprocess, "Popen", return_value=process), \
                patch.object(
                    subject, "attach_kill_on_close_process_job", side_effect=attach
                ), patch.object(
                    subject,
                    "verify_suspended_browser_image",
                    side_effect=lambda process, browser: events.append("image"),
                ), patch.object(
                    subject,
                    "resume_suspended_primary_thread",
                    side_effect=lambda process: events.append("resume"),
                ), patch.object(subject.threading, "Thread", RecordingThread):
            run_body_sway_headless_capture_case(
                self.browser,
                URL,
                self.profile,
                collector(PENDING, CAPTURED),
                CASE_ID,
            )

        self.assertEqual(["attach", "image", "resume", "reader"], events)
        self.assertTrue(job.closed)
        self.assertFalse(process.terminated)
        self.assertEqual([subject.KILL_GRACE_SECONDS], process.wait_timeouts)

    def test_late_root_exit_after_capture_recovers_with_bounded_kill(self):
        process = FakeProcess()
        job = _SlowExitOwnedJob(process)
        with patch.object(subject.subprocess, "Popen", return_value=process), \
                patch.object(
                    subject, "attach_kill_on_close_process_job", return_value=job
                ), patch.object(
                    subject, "verify_suspended_browser_image"
                ), patch.object(
                    subject, "resume_suspended_primary_thread"
                ):
            run_body_sway_headless_capture_case(
                self.browser,
                URL,
                self.profile,
                collector(PENDING, CAPTURED),
                CASE_ID,
            )

        self.assertTrue(job.closed)
        self.assertTrue(process.killed)
        self.assertEqual(
            [subject.KILL_GRACE_SECONDS, subject.KILL_GRACE_SECONDS],
            process.wait_timeouts,
        )

    def test_job_assignment_failure_is_explicit_and_root_is_stopped(self):
        process = FakeProcess()
        with patch.object(subject.subprocess, "Popen", return_value=process), \
                patch.object(
                    subject,
                    "attach_kill_on_close_process_job",
                    side_effect=WindowsProcessJobError("inner assignment denied"),
                ):
            with self.assertRaisesRegex(
                BodySwayHeadlessBrowserError, "inner assignment denied"
            ):
                run_body_sway_headless_capture_case(
                    self.browser, URL, self.profile, collector(PENDING), CASE_ID
                )
        self.assertTrue(process.terminated)

    def test_post_launch_image_change_closes_job_without_resuming(self):
        process = FakeProcess()
        job = _OwnedJob(process)
        with patch.object(subject.subprocess, "Popen", return_value=process), \
                patch.object(
                    subject, "attach_kill_on_close_process_job", return_value=job
                ), patch.object(
                    subject,
                    "verify_suspended_browser_image",
                    side_effect=WindowsProcessImageError("image changed"),
                ), patch.object(
                    subject, "resume_suspended_primary_thread"
                ) as resume:
            with self.assertRaisesRegex(
                BodySwayHeadlessBrowserError, "image changed"
            ):
                run_body_sway_headless_capture_case(
                    self.browser, URL, self.profile, collector(PENDING), CASE_ID
                )
        self.assertTrue(job.closed)
        resume.assert_not_called()

    def test_job_cleanup_error_does_not_mask_runtime_error(self):
        process = FakeProcess()
        job = _OwnedJob(process, WindowsProcessJobError("close failed"))
        with patch.object(subject.subprocess, "Popen", return_value=process), \
                patch.object(
                    subject, "attach_kill_on_close_process_job", return_value=job
                ), patch.object(
                    subject, "verify_suspended_browser_image"
                ), patch.object(
                    subject, "resume_suspended_primary_thread"
                ):
            with self.assertRaisesRegex(
                BodySwayHeadlessBrowserError, "runtime reported"
            ) as raised:
                run_body_sway_headless_capture_case(
                    self.browser,
                    URL,
                    self.profile,
                    collector(PENDING, RUNTIME_ERROR),
                    CASE_ID,
                )
        self.assertTrue(
            any("close failed" in note for note in raised.exception.__notes__)
        )

    def test_output_close_error_is_not_lost_behind_runtime_error(self):
        process = FakeProcess()
        with patch.object(subject.subprocess, "Popen", return_value=process), \
                patch.object(
                    subject,
                    "attach_kill_on_close_process_job",
                    return_value=KillOnCloseProcessJob(None, None),
                ), patch.object(
                    subject, "verify_suspended_browser_image"
                ), patch.object(
                    subject, "resume_suspended_primary_thread"
                ), patch.object(
                    subject, "close_browser_output", return_value=False
                ):
            with self.assertRaisesRegex(
                BodySwayHeadlessBrowserError, "runtime reported"
            ) as raised:
                run_body_sway_headless_capture_case(
                    self.browser,
                    URL,
                    self.profile,
                    collector(PENDING, RUNTIME_ERROR),
                    CASE_ID,
                )
        self.assertTrue(
            any("output could not be read" in note
                for note in raised.exception.__notes__)
        )

    def test_job_cleanup_error_fails_an_otherwise_successful_capture(self):
        process = FakeProcess()
        job = _OwnedJob(process, WindowsProcessJobError("close failed"))
        with patch.object(subject.subprocess, "Popen", return_value=process), \
                patch.object(
                    subject, "attach_kill_on_close_process_job", return_value=job
                ), patch.object(
                    subject, "verify_suspended_browser_image"
                ), patch.object(
                    subject, "resume_suspended_primary_thread"
                ):
            with self.assertRaisesRegex(
                BodySwayHeadlessBrowserError, "process-tree cleanup failed"
            ):
                run_body_sway_headless_capture_case(
                    self.browser,
                    URL,
                    self.profile,
                    collector(PENDING, CAPTURED),
                    CASE_ID,
                )

    def test_suspended_isolation_flag_matches_the_host_platform(self):
        creation_flags = subject._hidden_window_options()["creationflags"]
        breakaway = getattr(
            subject.subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000
        )
        suspended = getattr(subject.subprocess, "CREATE_SUSPENDED", 0x00000004)
        expected = suspended if subject.os.name == "nt" else 0
        self.assertEqual(expected, creation_flags & suspended)
        self.assertEqual(0, creation_flags & breakaway)


if __name__ == "__main__":
    unittest.main()
