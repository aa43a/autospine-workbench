"""Lifecycle regressions for the collector-terminal P10.3 v2 driver."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import autospine_workbench.body_sway_headless_browser_v2 as subject  # noqa: E402
from autospine_workbench.body_sway_runtime_execution_profile import (  # noqa: E402
    BROWSER_FIXED_ARGUMENTS,
)
from autospine_workbench.windows_process_job import (  # noqa: E402
    KillOnCloseProcessJob,
)
from tests.body_sway_headless_browser_support import (  # noqa: E402
    CAPTURED,
    CASE_ID,
    PENDING,
    URL,
    FakeProcess,
    HeadlessBrowserFixture,
    collector,
)


class _OwnedJob(KillOnCloseProcessJob):
    def __init__(self, process):
        super().__init__(1, object())
        self.process = process
        self.closed = False

    def close(self):
        self.closed = True
        self._handle = None
        self.process.return_code = -1
        self.process.stop_event.set()


class _TeardownReadError:
    def __init__(self, stop_event):
        self._stop_event = stop_event
        self.closed = False

    def read(self, _size):
        self._stop_event.wait(2)
        raise ValueError("pipe closed by owned teardown")

    def close(self):
        self.closed = True


class _ImmediateReadError:
    closed = False

    def read(self, _size):
        raise OSError("pipe failed before capture")

    def close(self):
        self.closed = True


class _InlineThread:
    """Run the output reader before the first collector poll."""

    def __init__(self, *, target, args, **_kwargs):
        self._target = target
        self._args = args

    def start(self):
        self._target(*self._args)

    def join(self, _timeout=None):
        return None

    def is_alive(self):
        return False


class BodySwayHeadlessBrowserV2Tests(
    HeadlessBrowserFixture, unittest.TestCase,
):
    def test_command_has_collector_terminal_lifetime(self):
        process = FakeProcess()
        with self._boundaries(process) as launch:
            subject.run_body_sway_headless_capture_case(
                self.browser, URL, self.profile,
                collector(PENDING, CAPTURED), CASE_ID,
            )

        command = launch.call_args.args[0]
        self.assertEqual(self.browser.path, command[0])
        self.assertEqual(URL, command[-1])
        self.assertNotIn("--dump-dom", command)
        self.assertFalse(any(
            value.startswith("--virtual-time-budget=") for value in command
        ))
        self.assertEqual(
            list(BROWSER_FIXED_ARGUMENTS),
            command[1:1 + len(BROWSER_FIXED_ARGUMENTS)],
        )

    def test_intentional_teardown_read_error_after_commit_is_not_failure(self):
        process = FakeProcess()
        process.stdout = _TeardownReadError(process.stop_event)
        job = _OwnedJob(process)
        with self._boundaries(process, job=job):
            subject.run_body_sway_headless_capture_case(
                self.browser, URL, self.profile,
                collector(PENDING, CAPTURED), CASE_ID,
            )

        self.assertTrue(job.closed)
        self.assertTrue(process.stdout.closed)

    def test_output_read_failure_before_commit_remains_fail_closed(self):
        process = FakeProcess()
        process.stdout = _ImmediateReadError()
        with self._boundaries(process), patch.object(
            subject.threading, "Thread", _InlineThread,
        ), self.assertRaisesRegex(
            subject.BodySwayHeadlessBrowserError, "could not be read",
        ):
            subject.run_body_sway_headless_capture_case(
                self.browser, URL, self.profile,
                collector(PENDING), CASE_ID,
            )

    def test_exact_commit_wins_simultaneous_teardown_read_failure(self):
        process = FakeProcess()
        process.stdout = _ImmediateReadError()
        with self._boundaries(process), patch.object(
            subject.threading, "Thread", _InlineThread,
        ):
            subject.run_body_sway_headless_capture_case(
                self.browser, URL, self.profile,
                collector(PENDING, CAPTURED), CASE_ID,
            )

        self.assertTrue(process.stdout.closed)

    def test_nonzero_exit_wins_simultaneous_commit_and_read_failure(self):
        process = FakeProcess(return_code=7)
        process.stdout = _ImmediateReadError()
        with self._boundaries(process), patch.object(
            subject.threading, "Thread", _InlineThread,
        ), self.assertRaisesRegex(
            subject.BodySwayHeadlessBrowserError, "non-zero status 7",
        ):
            subject.run_body_sway_headless_capture_case(
                self.browser, URL, self.profile,
                collector(PENDING, CAPTURED), CASE_ID,
            )

    def test_runtime_error_wins_simultaneous_commit_and_read_failure(self):
        process = FakeProcess()
        process.stdout = _ImmediateReadError()
        captured_and_failed = {
            "captured_case_ids": [CASE_ID],
            "error_case_ids": [CASE_ID],
        }
        with self._boundaries(process), patch.object(
            subject.threading, "Thread", _InlineThread,
        ), self.assertRaisesRegex(
            subject.BodySwayHeadlessBrowserError,
            "runtime reported a terminal capture error",
        ):
            subject.run_body_sway_headless_capture_case(
                self.browser, URL, self.profile,
                collector(PENDING, captured_and_failed), CASE_ID,
            )

    def test_delayed_output_overflow_after_commit_remains_failure(self):
        process = FakeProcess(
            b"x" * (subject.MAX_BROWSER_OUTPUT_BYTES + 1),
            delayed_output=True,
        )
        with self._boundaries(process), self.assertRaisesRegex(
            subject.BodySwayHeadlessBrowserError, "output exceeded",
        ):
            subject.run_body_sway_headless_capture_case(
                self.browser, URL, self.profile,
                collector(PENDING, CAPTURED), CASE_ID,
            )

        self.assertTrue(process.killed)

    def _boundaries(self, process, *, job=None):
        actual_job = job or KillOnCloseProcessJob(None, None)

        class Boundaries:
            def __enter__(inner):
                inner.patches = (
                    patch.object(subject.subprocess, "Popen", return_value=process),
                    patch.object(
                        subject, "attach_kill_on_close_process_job",
                        return_value=actual_job,
                    ),
                    patch.object(subject, "verify_suspended_browser_image"),
                    patch.object(subject, "resume_suspended_primary_thread"),
                )
                values = [item.start() for item in inner.patches]
                return values[0]

            def __exit__(inner, kind, value, traceback):
                for item in reversed(inner.patches):
                    item.stop()

        return Boundaries()


if __name__ == "__main__":
    unittest.main()
