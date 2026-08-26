"""Shared fixtures for the bounded headless-browser tests."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
import subprocess
import tempfile
import threading
from unittest.mock import patch

import autospine_workbench.body_sway_headless_browser as subject
from autospine_workbench.body_sway_headless_browser import (
    run_body_sway_headless_capture_case,
)
from autospine_workbench.body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureCollector,
)
from autospine_workbench.browser_executable_snapshot import (
    BrowserExecutableSnapshot,
)
from autospine_workbench.windows_process_job import KillOnCloseProcessJob


CASE_ID = "setup"
URL = "http://127.0.0.1:49152/capture/setup"
PENDING = {"captured_case_ids": [], "error_case_ids": []}
CAPTURED = {"captured_case_ids": [CASE_ID], "error_case_ids": []}
RUNTIME_ERROR = {"captured_case_ids": [], "error_case_ids": [CASE_ID]}


class FakeProcess:
    def __init__(
        self,
        output=b"",
        *,
        return_code=None,
        terminate_stalls=False,
        kill_stalls=False,
        delayed_output=False,
    ):
        self.stop_event = threading.Event()
        self.stdout = (
            DelayedOutput(output, self.stop_event)
            if delayed_output
            else io.BytesIO(output)
        )
        self.return_code = return_code
        self.terminate_stalls = terminate_stalls
        self.kill_stalls = kill_stalls
        self.terminated = False
        self.killed = False
        self.wait_timeouts = []

    def poll(self):
        return self.return_code

    def terminate(self):
        self.terminated = True
        self.stop_event.set()
        if not self.terminate_stalls:
            self.return_code = -15

    def kill(self):
        self.killed = True
        self.stop_event.set()
        if not self.kill_stalls:
            self.return_code = -9

    def wait(self, timeout):
        self.wait_timeouts.append(timeout)
        if self.return_code is None:
            raise subprocess.TimeoutExpired("chrome", timeout)
        return self.return_code


class DelayedOutput:
    def __init__(self, output, stop_event):
        self._stream = io.BytesIO(output)
        self._stop_event = stop_event
        self.closed = False

    def read(self, size):
        self._stop_event.wait(2)
        return self._stream.read(size)

    def close(self):
        self.closed = True
        self._stream.close()


def collector(*states):
    result = object.__new__(BodySwayRuntimeCaptureCollector)
    result._case_ids = (CASE_ID,)
    sequence = list(states or (PENDING,))
    terminal = sequence[-1]

    def status():
        return sequence.pop(0) if sequence else terminal

    result.status = status
    return result


class HeadlessBrowserFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.profile = Path(self.temporary.name).resolve(strict=True)
        browser_path = self.profile.parent / "chrome.exe"
        self.browser = BrowserExecutableSnapshot(
            path=str(browser_path),
            family="google-chrome",
            reported_version="142.0.7444.60",
            version_output_sha256=hashlib.sha256(
                b"Google Chrome 142.0.7444.60\n"
            ).hexdigest(),
            executable_sha256=hashlib.sha256(b"browser").hexdigest(),
            size_bytes=7,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def run_case(self, process, runtime_collector):
        no_job = KillOnCloseProcessJob(None, None)
        with patch.object(
            subject.subprocess, "Popen", return_value=process
        ) as launch, patch.object(
            subject,
            "attach_kill_on_close_process_job",
            return_value=no_job,
        ), patch.object(
            subject, "verify_suspended_browser_image"
        ), patch.object(
            subject, "resume_suspended_primary_thread"
        ):
            result = run_body_sway_headless_capture_case(
                self.browser,
                URL,
                self.profile,
                runtime_collector,
                CASE_ID,
            )
        return result, launch
