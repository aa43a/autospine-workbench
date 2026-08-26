from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import autospine_workbench.windows_suspended_process as subject
from autospine_workbench.windows_suspended_process import (
    WindowsSuspendedProcessError,
    resume_suspended_primary_thread,
)


class _Process:
    def __init__(self, pid=101):
        self.pid = pid


class _Backend:
    def __init__(self, thread_ids=(202,), previous_count=1):
        self.thread_ids = thread_ids
        self.previous_count = previous_count
        self.calls = []

    def owned_thread_ids(self, process_id):
        self.calls.append(("threads", process_id))
        return self.thread_ids

    def resume_once(self, thread_id):
        self.calls.append(("resume", thread_id))
        return self.previous_count


class WindowsSuspendedProcessTests(unittest.TestCase):
    def run_resume(self, process, backend):
        with patch.object(subject, "_IS_WINDOWS", True), patch.object(
            subject, "_create_windows_thread_backend", return_value=backend
        ):
            return resume_suspended_primary_thread(process)

    def test_non_windows_is_a_safe_noop(self):
        with patch.object(subject, "_IS_WINDOWS", False), patch.object(
            subject, "_create_windows_thread_backend"
        ) as create:
            self.assertIsNone(resume_suspended_primary_thread(object()))
        create.assert_not_called()

    def test_resumes_the_only_thread_from_exact_suspended_count(self):
        backend = _Backend()
        self.assertIsNone(self.run_resume(_Process(), backend))
        self.assertEqual(
            [("threads", 101), ("resume", 202)], backend.calls
        )

    def test_requires_exactly_one_primary_thread(self):
        for thread_ids in ((), (201, 202)):
            backend = _Backend(thread_ids=thread_ids)
            with self.subTest(thread_ids=thread_ids), self.assertRaisesRegex(
                WindowsSuspendedProcessError, "exactly one"
            ):
                self.run_resume(_Process(), backend)
            self.assertEqual([("threads", 101)], backend.calls)

    def test_requires_exact_create_suspended_count(self):
        for previous_count in (0, 2):
            backend = _Backend(previous_count=previous_count)
            with self.subTest(
                previous_count=previous_count
            ), self.assertRaisesRegex(
                WindowsSuspendedProcessError, "exact suspended state"
            ):
                self.run_resume(_Process(), backend)

    def test_rejects_invalid_process_id_before_api_load(self):
        backend = _Backend()
        for process in (object(), _Process(0), _Process("101")):
            with self.subTest(process=process), self.assertRaisesRegex(
                WindowsSuspendedProcessError, "valid process id"
            ):
                self.run_resume(process, backend)
        self.assertEqual([], backend.calls)


if __name__ == "__main__":
    unittest.main()
