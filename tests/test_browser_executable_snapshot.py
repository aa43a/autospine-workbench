from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import autospine_workbench.browser_executable_snapshot as subject
from autospine_workbench.browser_executable_snapshot import (
    BrowserExecutableSnapshot,
    BrowserExecutableSnapshotError,
    recheck_browser_executable,
    snapshot_browser_executable,
)


CHROME_OUTPUT = b"Google Chrome 142.0.7444.60\r\n"
CHROMIUM_OUTPUT = b"Chromium 141.0.7390.0\n"


class _FakeProcess:
    def __init__(self, output: bytes, *, code: int = 0, timeout: bool = False):
        self.stdout = io.BytesIO(output)
        self.code = code
        self.timeout = timeout
        self.wait_count = 0
        self.killed = False

    def wait(self, timeout: float) -> int:
        self.wait_count += 1
        if self.timeout and self.wait_count == 1:
            raise subprocess.TimeoutExpired("browser", timeout)
        return self.code

    def kill(self) -> None:
        self.killed = True


class BrowserExecutableSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve(strict=True)
        self.executable = self.root / "chrome-test.exe"
        self.executable.write_bytes(b"fixed fake executable bytes")
        self.executable.chmod(
            self.executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @contextmanager
    def version(self, output: bytes = CHROME_OUTPUT):
        with patch.object(subject, "_bounded_version_output", return_value=output):
            yield

    def test_snapshots_google_chrome_with_exact_byte_identity(self) -> None:
        raw = self.executable.read_bytes()
        with self.version():
            snapshot = snapshot_browser_executable(self.executable)

        self.assertEqual("google-chrome", snapshot.family)
        self.assertEqual("142.0.7444.60", snapshot.reported_version)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), snapshot.executable_sha256)
        self.assertEqual(hashlib.sha256(CHROME_OUTPUT).hexdigest(), snapshot.version_output_sha256)
        self.assertEqual(len(raw), snapshot.size_bytes)
        self.assertEqual(str(self.executable), snapshot.path)
        self.assertEqual(
            {
                "format": "autospine-browser-executable-snapshot",
                "version": 1,
                "path": str(self.executable),
                "family": "google-chrome",
                "reported_version": "142.0.7444.60",
                "version_output_sha256": hashlib.sha256(CHROME_OUTPUT).hexdigest(),
                "executable_sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw),
            },
            snapshot.to_document(),
        )

    def test_snapshots_chromium_family(self) -> None:
        with self.version(CHROMIUM_OUTPUT):
            snapshot = snapshot_browser_executable(self.executable)
        self.assertEqual("chromium", snapshot.family)
        self.assertEqual("141.0.7390.0", snapshot.reported_version)

    def test_accepts_chrome_for_testing_and_known_chromium_build_suffix(self) -> None:
        self.assertEqual(
            ("google-chrome", "142.0.7444.60"),
            subject._parse_version_output(
                b"Google Chrome for Testing 142.0.7444.60\n"
            ),
        )
        self.assertEqual(
            ("chromium", "140.0.7339.80"),
            subject._parse_version_output(
                b"Chromium 140.0.7339.80 built on Debian GNU/Linux 12\n"
            ),
        )

    def test_rejects_unsupported_or_ambiguous_version_output(self) -> None:
        invalid = (
            b"Microsoft Edge 142.0.7444.60\n",
            b"Google Chrome 142.0.7444\n",
            b"Google Chrome 142.0.7444.60\nwarning\n",
            b"Chromium 142.0.7444.60 unexpected suffix\n",
            b"\xff",
            b"",
        )
        for output in invalid:
            with self.subTest(output=output):
                with self.assertRaises(BrowserExecutableSnapshotError):
                    subject._parse_version_output(output)

    def test_requires_absolute_canonical_regular_executable(self) -> None:
        with self.assertRaisesRegex(BrowserExecutableSnapshotError, "absolute"):
            snapshot_browser_executable(Path("chrome.exe"))
        lexical_alias = self.root / "folder" / ".." / self.executable.name
        with self.assertRaisesRegex(BrowserExecutableSnapshotError, "lexical aliases"):
            snapshot_browser_executable(lexical_alias)
        with self.assertRaisesRegex(BrowserExecutableSnapshotError, "regular file"):
            snapshot_browser_executable(self.root)

    def test_rejects_file_and_parent_symlinks_when_supported(self) -> None:
        alias = self.root / "chrome-alias.exe"
        parent_alias = self.root / "parent-alias"
        real_parent = self.root / "real-parent"
        real_parent.mkdir()
        nested = real_parent / "chrome.exe"
        nested.write_bytes(b"browser")
        nested.chmod(nested.stat().st_mode | stat.S_IXUSR)
        try:
            alias.symlink_to(self.executable)
            parent_alias.symlink_to(real_parent, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        try:
            with self.assertRaises(BrowserExecutableSnapshotError):
                snapshot_browser_executable(alias)
            with self.assertRaises(BrowserExecutableSnapshotError):
                snapshot_browser_executable(parent_alias / nested.name)
        finally:
            alias.unlink(missing_ok=True)
            parent_alias.unlink(missing_ok=True)

    def test_recognizes_windows_reparse_attribute_as_alias(self) -> None:
        metadata = type("Metadata", (), {
            "st_mode": stat.S_IFREG,
            "st_file_attributes": 0x400,
        })()
        with patch.object(Path, "is_junction", return_value=False, create=True):
            self.assertTrue(subject._is_alias(self.executable, metadata))

    def test_enforces_executable_size_limit(self) -> None:
        with patch.object(subject, "MAX_EXECUTABLE_BYTES", 4), self.version():
            with self.assertRaisesRegex(BrowserExecutableSnapshotError, "size"):
                snapshot_browser_executable(self.executable)

    def test_detects_change_across_pre_and_post_version_hashes(self) -> None:
        with patch.object(
            subject,
            "_hash_executable",
            side_effect=[("a" * 64, 25), ("b" * 64, 25)],
        ), self.version():
            with self.assertRaisesRegex(BrowserExecutableSnapshotError, "version"):
                snapshot_browser_executable(self.executable)

    def test_recheck_requires_every_field_and_current_bytes(self) -> None:
        with self.version():
            expected = snapshot_browser_executable(self.executable)
            self.assertEqual(expected, recheck_browser_executable(expected))
            self.executable.write_bytes(b"changed executable contents")
            with self.assertRaisesRegex(BrowserExecutableSnapshotError, "changed"):
                recheck_browser_executable(expected)
        with self.assertRaises(BrowserExecutableSnapshotError):
            recheck_browser_executable(expected.to_document())  # type: ignore[arg-type]

    def test_recheck_rejects_changed_reported_version(self) -> None:
        with self.version():
            expected = snapshot_browser_executable(self.executable)
        changed = b"Google Chrome 143.0.7444.60\n"
        with self.version(changed):
            with self.assertRaisesRegex(BrowserExecutableSnapshotError, "changed"):
                recheck_browser_executable(expected)

    def test_bounded_version_command_uses_no_shell_and_exact_argument(self) -> None:
        fake = _FakeProcess(CHROME_OUTPUT)
        with patch.object(subject.subprocess, "Popen", return_value=fake) as launch:
            output = subject._bounded_version_output(self.executable)
        self.assertEqual(CHROME_OUTPUT, output)
        args, kwargs = launch.call_args
        self.assertEqual([str(self.executable), "--version"], args[0])
        self.assertIs(False, kwargs["shell"])
        self.assertEqual(str(self.executable.parent), kwargs["cwd"])
        self.assertIs(subprocess.DEVNULL, kwargs["stdin"])
        self.assertIs(subprocess.PIPE, kwargs["stdout"])
        self.assertIs(subprocess.STDOUT, kwargs["stderr"])

    def test_bounded_version_command_rejects_timeout_failure_and_overflow(self) -> None:
        cases = (
            (_FakeProcess(b"", timeout=True), "timed out"),
            (_FakeProcess(b"failure", code=3), "failed"),
            (_FakeProcess(b"x" * 10), "exceeds"),
        )
        for fake, message in cases:
            with self.subTest(message=message), patch.object(
                subject, "MAX_VERSION_OUTPUT_BYTES", 8
            ), patch.object(subject.subprocess, "Popen", return_value=fake):
                with self.assertRaisesRegex(BrowserExecutableSnapshotError, message):
                    subject._bounded_version_output(self.executable)
        self.assertTrue(cases[0][0].killed)
        self.assertTrue(cases[2][0].killed)

    def test_real_version_reader_is_bounded_and_cross_platform(self) -> None:
        output = subject._bounded_version_output(Path(sys.executable))
        self.assertIn(b"Python", output)
        self.assertLessEqual(len(output), subject.MAX_VERSION_OUTPUT_BYTES)


if __name__ == "__main__":
    unittest.main()
