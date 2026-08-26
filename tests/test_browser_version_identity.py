from __future__ import annotations

import io
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import autospine_workbench.browser_version_identity as subject
from autospine_workbench.browser_version_identity import (
    BrowserVersionIdentityError,
    browser_version_identity_sha256,
    canonical_browser_version_identity_bytes,
    identify_browser_version,
)
from autospine_workbench.windows_file_version import (
    WindowsFileVersion,
    WindowsFileVersionError,
)


CHROME_OUTPUT = b"Google Chrome 142.0.7444.60\r\n"


class _FakeProcess:
    def __init__(self, output: bytes, *, code: int = 0, timeout: bool = False):
        self.stdout = io.BytesIO(output)
        self.pid = 4242
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

    def poll(self) -> int:
        return self.code


class _ReadFailingStream(io.BytesIO):
    def read(self, size: int = -1) -> bytes:
        raise OSError("reader failed")


class BrowserVersionIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.executable = Path(self.temporary.name).resolve() / "chrome-test.exe"
        self.executable.write_bytes(b"fake browser")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_canonicalizes_chrome_and_chromium_process_output(self) -> None:
        cases = (
            (
                b"Google Chrome for Testing 142.0.7444.60\r\n",
                "google-chrome",
                b"Google Chrome 142.0.7444.60\n",
            ),
            (
                b"Chromium 140.0.7339.80 built on Debian GNU/Linux 12\n",
                "chromium",
                b"Chromium 140.0.7339.80\n",
            ),
        )
        for output, family, canonical in cases:
            with self.subTest(family=family), patch.object(
                subject, "_version_evidence", return_value=output
            ):
                identity = identify_browser_version(self.executable)
            self.assertEqual(family, identity.family)
            self.assertEqual(canonical, identity.canonical_bytes)

    def test_public_pure_identity_helpers_are_exact_and_fail_closed(self) -> None:
        canonical = canonical_browser_version_identity_bytes(
            "google-chrome", "142.0.7444.60"
        )
        self.assertEqual(b"Google Chrome 142.0.7444.60\n", canonical)
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            browser_version_identity_sha256(
                "google-chrome", "142.0.7444.60"
            ),
        )
        for family, version in (
            ("edge", "142.0.7444.60"),
            ("chromium", "142.0.7444"),
            ("chromium", "142.0.7444.60\n"),
            (None, "142.0.7444.60"),
        ):
            with self.subTest(family=family, version=version), self.assertRaises(
                BrowserVersionIdentityError
            ):
                canonical_browser_version_identity_bytes(family, version)

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
            with self.subTest(output=output), patch.object(
                subject, "_version_evidence", return_value=output
            ):
                with self.assertRaises(BrowserVersionIdentityError):
                    identify_browser_version(self.executable)

    def test_prefers_windows_version_info_and_canonicalizes_it(self) -> None:
        info = WindowsFileVersion("Google Chrome", (151, 0, 7922, 174))
        with patch.object(subject.os, "name", "nt"), patch.object(
            subject, "read_windows_file_version", return_value=info
        ), patch.object(subject, "_bounded_version_output") as command:
            identity = identify_browser_version(self.executable)
        command.assert_not_called()
        self.assertEqual("151.0.7922.174", identity.reported_version)
        self.assertEqual(b"Google Chrome 151.0.7922.174\n", identity.canonical_bytes)

    def test_windows_rejects_missing_version_info_without_executing_browser(self) -> None:
        with patch.object(subject.os, "name", "nt"), patch.object(
            subject,
            "read_windows_file_version",
            side_effect=WindowsFileVersionError("missing"),
        ), patch.object(
            subject, "_bounded_version_output"
        ) as command, self.assertRaisesRegex(
            BrowserVersionIdentityError, "VERSIONINFO"
        ):
            identify_browser_version(self.executable)
        command.assert_not_called()

    def test_windows_rejects_non_chrome_version_info_without_fallback(self) -> None:
        info = WindowsFileVersion("Microsoft Edge", (151, 0, 7922, 174))
        with patch.object(subject.os, "name", "nt"), patch.object(
            subject, "read_windows_file_version", return_value=info
        ), patch.object(
            subject, "_bounded_version_output"
        ) as command, self.assertRaisesRegex(
            BrowserVersionIdentityError, "VERSIONINFO"
        ):
            identify_browser_version(self.executable)
        command.assert_not_called()

    def test_bounded_version_command_uses_no_shell_and_exact_argument(self) -> None:
        fake = _FakeProcess(CHROME_OUTPUT)
        with patch.object(
            subject, "_cleanup_version_process"
        ), patch.object(subject.subprocess, "Popen", return_value=fake) as launch:
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
            ), patch.object(
                subject, "_cleanup_version_process"
            ), patch.object(subject.subprocess, "Popen", return_value=fake):
                with self.assertRaisesRegex(BrowserVersionIdentityError, message):
                    subject._bounded_version_output(self.executable)

    def test_non_windows_command_owns_and_cleans_complete_process_group(self) -> None:
        fake = _FakeProcess(CHROME_OUTPUT)
        with patch.object(subject.os, "name", "posix"), patch.object(
            subject.os, "killpg", create=True
        ) as kill_group, patch.object(
            subject.subprocess, "Popen", return_value=fake
        ) as launch:
            output = subject._bounded_version_output(self.executable)
        self.assertEqual(CHROME_OUTPUT, output)
        self.assertIs(True, launch.call_args.kwargs["start_new_session"])
        self.assertNotIn("creationflags", launch.call_args.kwargs)
        self.assertEqual(
            [
                call(fake.pid, subject._POSIX_TERMINATE_SIGNAL),
                call(fake.pid, subject._POSIX_KILL_SIGNAL),
            ],
            kill_group.call_args_list,
        )

    def test_non_windows_timeout_still_cleans_complete_process_group(self) -> None:
        fake = _FakeProcess(b"", timeout=True)
        with patch.object(subject.os, "name", "posix"), patch.object(
            subject.os, "killpg", create=True
        ) as kill_group, patch.object(
            subject.subprocess, "Popen", return_value=fake
        ), self.assertRaisesRegex(BrowserVersionIdentityError, "timed out"):
            subject._bounded_version_output(self.executable)
        self.assertEqual(
            [
                call(fake.pid, subject._POSIX_TERMINATE_SIGNAL),
                call(fake.pid, subject._POSIX_KILL_SIGNAL),
            ],
            kill_group.call_args_list,
        )

    def test_cleanup_failure_does_not_mask_primary_version_error(self) -> None:
        fake = _FakeProcess(b"overflow")
        cleanup = RuntimeError("cleanup failed")
        with patch.object(
            subject, "MAX_VERSION_OUTPUT_BYTES", 4
        ), patch.object(
            subject, "_cleanup_version_process", side_effect=cleanup
        ), patch.object(subject.subprocess, "Popen", return_value=fake):
            with self.assertRaisesRegex(
                BrowserVersionIdentityError, "exceeds"
            ) as raised:
                subject._bounded_version_output(self.executable)
        self.assertTrue(any(
            "cleanup also failed" in note.lower()
            for note in getattr(raised.exception, "__notes__", ())
        ))

    def test_reader_cleanup_failure_is_noted_on_primary_error(self) -> None:
        fake = _FakeProcess(b"overflow")
        with patch.object(
            subject, "MAX_VERSION_OUTPUT_BYTES", 4
        ), patch.object(
            subject, "_cleanup_version_process"
        ), patch.object(
            fake.stdout, "close", side_effect=OSError("reader close failed")
        ), patch.object(subject.subprocess, "Popen", return_value=fake):
            with self.assertRaisesRegex(
                BrowserVersionIdentityError, "exceeds"
            ) as raised:
                subject._bounded_version_output(self.executable)
        self.assertTrue(any(
            "reader close failed" in note
            for note in getattr(raised.exception, "__notes__", ())
        ))

    def test_reader_failure_is_preserved_as_the_error_cause(self) -> None:
        fake = _FakeProcess(b"")
        fake.stdout = _ReadFailingStream()
        with patch.object(
            subject, "_cleanup_version_process"
        ), patch.object(subject.subprocess, "Popen", return_value=fake):
            with self.assertRaisesRegex(
                BrowserVersionIdentityError, "could not be read"
            ) as raised:
                subject._bounded_version_output(self.executable)
        self.assertIsInstance(raised.exception.__cause__, OSError)
        self.assertTrue(any(
            "reader also failed" in note.lower()
            for note in getattr(raised.exception, "__notes__", ())
        ))

    def test_cleanup_failure_rejects_otherwise_valid_version_output(self) -> None:
        fake = _FakeProcess(CHROME_OUTPUT)
        cleanup = BrowserVersionIdentityError("cleanup failed")
        with patch.object(
            subject, "_cleanup_version_process", side_effect=cleanup
        ), patch.object(subject.subprocess, "Popen", return_value=fake):
            with self.assertRaisesRegex(BrowserVersionIdentityError, "cleanup"):
                subject._bounded_version_output(self.executable)

    def test_real_version_reader_is_bounded_and_cross_platform(self) -> None:
        output = subject._bounded_version_output(Path(sys.executable))
        self.assertIn(b"Python", output)
        self.assertLessEqual(len(output), subject.MAX_VERSION_OUTPUT_BYTES)


if __name__ == "__main__":
    unittest.main()
