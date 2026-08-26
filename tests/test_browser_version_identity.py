from __future__ import annotations

import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import autospine_workbench.browser_version_identity as subject
from autospine_workbench.browser_version_identity import (
    BrowserVersionIdentityError,
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

    @unittest.skipUnless(os.name == "nt", "Windows VERSIONINFO selection")
    def test_prefers_windows_version_info_and_canonicalizes_it(self) -> None:
        info = WindowsFileVersion("Google Chrome", (151, 0, 7922, 174))
        with patch.object(
            subject, "read_windows_file_version", return_value=info
        ), patch.object(subject, "_bounded_version_output") as command:
            identity = identify_browser_version(self.executable)
        command.assert_not_called()
        self.assertEqual("151.0.7922.174", identity.reported_version)
        self.assertEqual(b"Google Chrome 151.0.7922.174\n", identity.canonical_bytes)

    @unittest.skipUnless(os.name == "nt", "Windows VERSIONINFO selection")
    def test_falls_back_to_process_output_when_version_info_is_absent(self) -> None:
        with patch.object(
            subject,
            "read_windows_file_version",
            side_effect=WindowsFileVersionError("missing"),
        ), patch.object(
            subject, "_bounded_version_output", return_value=CHROME_OUTPUT
        ):
            identity = identify_browser_version(self.executable)
        self.assertEqual(b"Google Chrome 142.0.7444.60\n", identity.canonical_bytes)

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
                with self.assertRaisesRegex(BrowserVersionIdentityError, message):
                    subject._bounded_version_output(self.executable)
        self.assertTrue(cases[0][0].killed)
        self.assertTrue(cases[2][0].killed)

    def test_real_version_reader_is_bounded_and_cross_platform(self) -> None:
        output = subject._bounded_version_output(Path(sys.executable))
        self.assertIn(b"Python", output)
        self.assertLessEqual(len(output), subject.MAX_VERSION_OUTPUT_BYTES)


if __name__ == "__main__":
    unittest.main()
