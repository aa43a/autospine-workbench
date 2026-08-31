from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import autospine_workbench.windows_process_job as subject
from autospine_workbench.process_tree_cleanup import stop_owned_process_tree
from autospine_workbench.windows_process_job import (
    KillOnCloseProcessJob,
    WindowsProcessJobError,
    attach_kill_on_close_process_job,
)


class _Process:
    def __init__(self, *polls, handle=41, pid=101, terminate_stalls=False):
        self._handle = handle
        self.pid = pid
        self._polls = list(polls or (None,))
        self._terminal_poll = self._polls[-1]
        self.return_code = self._terminal_poll
        self.terminate_stalls = terminate_stalls
        self.terminated = False
        self.killed = False
        self.wait_timeouts = []

    def poll(self):
        value = self._polls.pop(0) if self._polls else self.return_code
        self.return_code = value
        return value

    def terminate(self):
        self.terminated = True
        if not self.terminate_stalls:
            self.return_code = -15

    def kill(self):
        self.killed = True
        self.return_code = -9

    def wait(self, timeout):
        self.wait_timeouts.append(timeout)
        if self.return_code is None:
            raise subprocess.TimeoutExpired("chrome", timeout)
        return self.return_code


class _Backend:
    def __init__(
        self, *, membership_verified=True, assign_error=None, close_error=None
    ):
        self.membership_verified = membership_verified
        self.assign_error = assign_error
        self.close_error = close_error
        self.calls = []

    def create(self):
        self.calls.append(("create",))
        return 73

    def configure_kill_on_close(self, handle):
        self.calls.append(("configure", handle))

    def process_is_in_job(self, process_handle, job_handle):
        self.calls.append(("is_in_job", process_handle, job_handle))
        return self.membership_verified

    def assign(self, handle, process_handle):
        self.calls.append(("assign", handle, process_handle))
        if self.assign_error:
            raise self.assign_error

    def close(self, handle):
        self.calls.append(("close", handle))
        if self.close_error:
            raise self.close_error


class WindowsProcessJobTests(unittest.TestCase):
    def attach(self, process, backend):
        with patch.object(subject, "_IS_WINDOWS", True), patch.object(
            subject, "_create_windows_job_backend", return_value=backend
        ):
            return attach_kill_on_close_process_job(process)

    def test_non_windows_is_a_safe_noop(self):
        process = object()
        with patch.object(subject, "_IS_WINDOWS", False), patch.object(
            subject, "_create_windows_job_backend"
        ) as create:
            job = attach_kill_on_close_process_job(process)
        self.assertFalse(job.owns_windows_process_tree)
        job.close()
        create.assert_not_called()

    def test_configures_checks_and_assigns_before_returning(self):
        backend = _Backend()
        process = _Process(None, None, None)
        job = self.attach(process, backend)

        self.assertTrue(job.owns_windows_process_tree)
        self.assertEqual(
            [
                ("create",),
                ("configure", 73),
                ("assign", 73, 41),
                ("is_in_job", 41, 73),
            ],
            backend.calls,
        )
        job.close()
        self.assertFalse(job.owns_windows_process_tree)
        self.assertEqual(("close", 73), backend.calls[-1])
        job.close()
        self.assertEqual(1, backend.calls.count(("close", 73)))

    def test_exited_process_fails_before_job_creation(self):
        backend = _Backend()
        with self.assertRaisesRegex(WindowsProcessJobError, "exited before"):
            self.attach(_Process(7), backend)
        self.assertEqual([], backend.calls)

    def test_exit_during_setup_closes_unassigned_job(self):
        backend = _Backend()
        with self.assertRaisesRegex(WindowsProcessJobError, "exited before"):
            self.attach(_Process(None, 7), backend)
        self.assertEqual(
            [("create",), ("configure", 73), ("close", 73)],
            backend.calls,
        )

    def test_unverified_inner_job_membership_is_rejected_and_closed(self):
        backend = _Backend(membership_verified=False)
        with self.assertRaisesRegex(WindowsProcessJobError, "membership"):
            self.attach(_Process(None, None), backend)
        self.assertIn(("assign", 73, 41), backend.calls)
        self.assertEqual(("close", 73), backend.calls[-1])

    def test_attach_close_failures_are_retried_and_noted(self):
        close_error = WindowsProcessJobError("CloseHandle denied")
        backend = _Backend(
            membership_verified=False, close_error=close_error
        )
        with self.assertRaisesRegex(
            WindowsProcessJobError, "membership"
        ) as raised:
            self.attach(_Process(None, None), backend)
        self.assertEqual(2, backend.calls.count(("close", 73)))
        self.assertEqual(2, len(raised.exception.__notes__))
        self.assertTrue(
            all("CloseHandle denied" in note for note in raised.exception.__notes__)
        )

    def test_verified_inner_job_allows_an_inherited_outer_job(self):
        backend = _Backend(membership_verified=True)
        job = self.attach(_Process(None, None), backend)
        self.assertTrue(job.owns_windows_process_tree)
        self.assertEqual(("is_in_job", 41, 73), backend.calls[-1])

    def test_assignment_failure_is_preserved_and_handle_closed(self):
        failure = WindowsProcessJobError("assignment denied")
        backend = _Backend(assign_error=failure)
        with self.assertRaisesRegex(WindowsProcessJobError, "assignment denied"):
            self.attach(_Process(None, None, None), backend)
        self.assertEqual(("close", 73), backend.calls[-1])

    def test_invalid_process_handle_fails_without_creating_job(self):
        backend = _Backend()
        with self.assertRaisesRegex(WindowsProcessJobError, "no valid"):
            self.attach(_Process(None, handle=0), backend)
        self.assertEqual([], backend.calls)

    def test_owned_job_close_kills_tree_then_waits_bounded(self):
        process = _Process(None)
        backend = _Backend()
        job = KillOnCloseProcessJob(73, backend)

        def close_and_mark_exit(handle):
            backend.calls.append(("close", handle))
            process.return_code = -1

        backend.close = close_and_mark_exit
        stop_owned_process_tree(process, job, 0.4, 0.6)

        self.assertEqual([0.6], process.wait_timeouts)
        self.assertFalse(process.terminated)
        self.assertFalse(process.killed)
        self.assertFalse(job.owns_windows_process_tree)

    def test_job_close_timeout_recovers_after_bounded_root_kill(self):
        process = _Process(None)
        backend = _Backend()
        job = KillOnCloseProcessJob(73, backend)
        stop_owned_process_tree(process, job, 0.4, 0.6)
        self.assertTrue(process.killed)
        self.assertEqual([0.6, 0.6], process.wait_timeouts)

    def test_job_close_timeout_still_fails_if_root_cannot_be_stopped(self):
        class StubbornProcess(_Process):
            def kill(self):
                self.killed = True

        process = StubbornProcess(None)
        backend = _Backend()
        job = KillOnCloseProcessJob(73, backend)
        with self.assertRaisesRegex(
            WindowsProcessJobError, "could not be stopped"
        ):
            stop_owned_process_tree(process, job, 0.4, 0.6)
        self.assertTrue(process.killed)
        self.assertEqual([0.6, 0.6], process.wait_timeouts)

    def test_close_failure_preserves_error_and_attempts_root_cleanup(self):
        failure = WindowsProcessJobError("CloseHandle failed")
        process = _Process(None)
        job = KillOnCloseProcessJob(73, _Backend(close_error=failure))
        with self.assertRaisesRegex(WindowsProcessJobError, "CloseHandle"):
            stop_owned_process_tree(process, job, 0.4, 0.6)
        self.assertTrue(process.terminated)

    def test_close_failure_retries_retained_handle_after_root_cleanup(self):
        process = _Process(None)
        backend = _Backend()
        attempts = []

        def fail_once(handle):
            attempts.append(handle)
            if len(attempts) == 1:
                raise WindowsProcessJobError("first close failed")

        backend.close = fail_once
        job = KillOnCloseProcessJob(73, backend)
        with self.assertRaisesRegex(WindowsProcessJobError, "first close"):
            stop_owned_process_tree(process, job, 0.4, 0.6)
        self.assertEqual([73, 73], attempts)
        self.assertFalse(job.owns_windows_process_tree)


if __name__ == "__main__":
    unittest.main()
