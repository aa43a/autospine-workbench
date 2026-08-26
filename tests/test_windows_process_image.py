from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import autospine_workbench.windows_process_image as subject
from autospine_workbench.browser_executable_snapshot import (
    BrowserExecutableSnapshot,
    BrowserExecutableSnapshotError,
)
from autospine_workbench.windows_process_image import (
    WindowsProcessImageError,
    verify_suspended_browser_image,
)


class _Backend:
    def __init__(self, path):
        self.path = path
        self.handles = []

    def query_path(self, process_handle):
        self.handles.append(process_handle)
        return self.path


class _Process:
    def __init__(self, handle=41):
        self._handle = handle


class WindowsProcessImageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve(strict=True)
        self.executable = self.root / "chrome.exe"
        self.executable.write_bytes(b"browser")
        self.snapshot = BrowserExecutableSnapshot(
            path=str(self.executable),
            family="google-chrome",
            reported_version="151.0.7922.174",
            version_output_sha256=hashlib.sha256(b"version").hexdigest(),
            executable_sha256=hashlib.sha256(b"browser").hexdigest(),
            size_bytes=7,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_windows_queries_mapped_path_then_rechecks_exact_bytes(self):
        backend = _Backend(self.executable)
        with patch.object(subject, "_IS_WINDOWS", True), patch.object(
            subject, "_create_windows_process_image_backend", return_value=backend
        ), patch.object(
            subject, "recheck_browser_executable", return_value=self.snapshot
        ) as recheck:
            verify_suspended_browser_image(_Process(), self.snapshot)
        self.assertEqual([41], backend.handles)
        recheck.assert_called_once_with(self.snapshot)

    def test_path_exchange_fails_before_byte_recheck(self):
        replacement = self.root / "replacement.exe"
        replacement.write_bytes(b"other")
        backend = _Backend(replacement)
        with patch.object(subject, "_IS_WINDOWS", True), patch.object(
            subject, "_create_windows_process_image_backend", return_value=backend
        ), patch.object(subject, "recheck_browser_executable") as recheck:
            with self.assertRaisesRegex(
                WindowsProcessImageError, "differs from the explicit path"
            ):
                verify_suspended_browser_image(_Process(), self.snapshot)
        recheck.assert_not_called()

    def test_path_byte_swap_is_normalized_and_rejected(self):
        backend = _Backend(self.executable)
        changed = BrowserExecutableSnapshotError("changed")
        with patch.object(subject, "_IS_WINDOWS", True), patch.object(
            subject, "_create_windows_process_image_backend", return_value=backend
        ), patch.object(
            subject, "recheck_browser_executable", side_effect=changed
        ):
            with self.assertRaisesRegex(
                WindowsProcessImageError, "changed before primary-thread resume"
            ):
                verify_suspended_browser_image(_Process(), self.snapshot)

    def test_non_windows_still_rechecks_expected_path_bytes(self):
        with patch.object(subject, "_IS_WINDOWS", False), patch.object(
            subject, "_create_windows_process_image_backend"
        ) as create, patch.object(
            subject, "recheck_browser_executable", return_value=self.snapshot
        ) as recheck:
            verify_suspended_browser_image(object(), self.snapshot)
        create.assert_not_called()
        recheck.assert_called_once_with(self.snapshot)

    def test_rejects_invalid_snapshot_and_process_handle(self):
        with self.assertRaisesRegex(WindowsProcessImageError, "snapshot"):
            verify_suspended_browser_image(_Process(), {})  # type: ignore[arg-type]
        with patch.object(subject, "_IS_WINDOWS", True):
            with self.assertRaisesRegex(WindowsProcessImageError, "valid"):
                verify_suspended_browser_image(_Process(0), self.snapshot)


if __name__ == "__main__":
    unittest.main()
