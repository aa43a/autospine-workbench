"""Tests for the Windows browser launcher stability lease."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import autospine_workbench.locked_browser_executable_lease as subject  # noqa: E402
from autospine_workbench.browser_executable_snapshot import (  # noqa: E402
    BrowserExecutableSnapshot,
)
from autospine_workbench.locked_browser_executable_lease import (  # noqa: E402
    LockedBrowserExecutableLease,
    LockedBrowserExecutableLeaseError,
)


class _Backend:
    def __init__(self, final_path: Path, events: list[str]) -> None:
        self.final_path_value = final_path
        self.events = events
        self.close_fails = False

    def open_read_locked(self, path: Path) -> int:
        self.events.append("open")
        return 73

    def final_path(self, handle: int) -> Path:
        self.events.append("final-path")
        return self.final_path_value

    def close(self, handle: int) -> None:
        self.events.append("close")
        if self.close_fails:
            raise LockedBrowserExecutableLeaseError("close failed")


class LockedBrowserExecutableLeaseTests(unittest.TestCase):
    def setUp(self) -> None:
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

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_open_final_path_snapshot_and_recheck_precede_use(self):
        events: list[str] = []
        backend = _Backend(self.executable, events)

        def snapshot(path):
            events.append("snapshot")
            return self.snapshot

        def recheck(value):
            events.append("recheck")
            return value

        lease = LockedBrowserExecutableLease(self.executable)
        with patch.object(subject, "_IS_WINDOWS", True), patch.object(
            subject, "_create_windows_browser_file_backend",
            return_value=backend,
        ), patch.object(
            subject, "snapshot_browser_executable", side_effect=snapshot,
        ), patch.object(
            subject, "recheck_browser_executable", side_effect=recheck,
        ):
            with lease as opened:
                self.assertIs(self.snapshot, opened)
                self.assertFalse(lease.closed)
                self.assertEqual(
                    ["open", "final-path", "snapshot", "recheck"], events
                )
        self.assertEqual("close", events[-1])
        self.assertTrue(lease.closed)

    def test_final_path_exchange_fails_and_closes_handle(self):
        events: list[str] = []
        other = self.root / "other.exe"
        backend = _Backend(other, events)
        with patch.object(subject, "_IS_WINDOWS", True), patch.object(
            subject, "_create_windows_browser_file_backend",
            return_value=backend,
        ), patch.object(subject, "snapshot_browser_executable") as snapshot:
            with self.assertRaisesRegex(
                LockedBrowserExecutableLeaseError, "final path differs"
            ):
                with LockedBrowserExecutableLease(self.executable):
                    pass
        self.assertEqual(["open", "final-path", "close"], events)
        snapshot.assert_not_called()

    def test_close_failure_is_visible_or_noted_on_primary_error(self):
        events: list[str] = []
        backend = _Backend(self.executable, events)
        backend.close_fails = True
        lease = LockedBrowserExecutableLease(self.executable)
        patches = self._successful_entry_patches(backend)
        with patches, self.assertRaisesRegex(
            LockedBrowserExecutableLeaseError, "close failed"
        ):
            with lease:
                pass
        self.assertFalse(lease.closed)

        primary = LookupError("capture failed")
        second = LockedBrowserExecutableLease(self.executable)
        with self._successful_entry_patches(backend):
            with self.assertRaises(LookupError) as raised:
                with second:
                    raise primary
        self.assertIs(primary, raised.exception)
        self.assertTrue(any(
            "lease close also failed" in note.lower()
            for note in getattr(primary, "__notes__", ())
        ))

    def test_non_windows_rejects_before_open_or_snapshot(self):
        with patch.object(subject, "_IS_WINDOWS", False), patch.object(
            subject, "_create_windows_browser_file_backend"
        ) as backend, patch.object(
            subject, "snapshot_browser_executable"
        ) as snapshot, self.assertRaisesRegex(
            LockedBrowserExecutableLeaseError, "only on Windows"
        ):
            with LockedBrowserExecutableLease(self.executable):
                pass
        backend.assert_not_called()
        snapshot.assert_not_called()

    def _successful_entry_patches(self, backend):
        stack = _PatchStack()
        stack.add(patch.object(subject, "_IS_WINDOWS", True))
        stack.add(patch.object(
            subject, "_create_windows_browser_file_backend",
            return_value=backend,
        ))
        stack.add(patch.object(
            subject, "snapshot_browser_executable",
            return_value=self.snapshot,
        ))
        stack.add(patch.object(
            subject, "recheck_browser_executable",
            return_value=self.snapshot,
        ))
        return stack


@unittest.skipUnless(os.name == "nt", "Windows share-mode integration")
class LockedBrowserExecutableWindowsIntegrationTests(unittest.TestCase):
    def test_handle_denies_write_replace_delete_until_close(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            executable = root / "chrome.exe"
            replacement = root / "replacement.exe"
            executable.write_bytes(b"browser")
            replacement.write_bytes(b"replacement")
            snapshot = BrowserExecutableSnapshot(
                path=str(executable), family="chromium",
                reported_version="151.0.7922.174",
                version_output_sha256="a" * 64,
                executable_sha256=hashlib.sha256(b"browser").hexdigest(),
                size_bytes=7,
            )
            lease = LockedBrowserExecutableLease(executable)
            with patch.object(
                subject, "snapshot_browser_executable", return_value=snapshot,
            ), patch.object(
                subject, "recheck_browser_executable", return_value=snapshot,
            ):
                with lease:
                    with self.assertRaises(OSError):
                        executable.write_bytes(b"changed")
                    with self.assertRaises(OSError):
                        os.replace(replacement, executable)
                    with self.assertRaises(OSError):
                        executable.unlink()
            self.assertTrue(lease.closed)
            executable.write_bytes(b"changed")
            os.replace(replacement, executable)
            executable.unlink()
            self.assertFalse(executable.exists())


class _PatchStack:
    def __init__(self) -> None:
        self._patches = []

    def add(self, item) -> None:
        self._patches.append(item)

    def __enter__(self):
        for item in self._patches:
            item.start()
        return self

    def __exit__(self, kind, value, traceback):
        for item in reversed(self._patches):
            item.stop()


if __name__ == "__main__":
    unittest.main()
