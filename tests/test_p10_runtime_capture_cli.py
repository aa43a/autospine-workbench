"""Parser, dispatch, and bounded output tests for P10 runtime capture."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.p10_runtime_capture_cli import (  # noqa: E402
    CAPTURE_ERROR_CODE,
    CAPTURE_ERROR_MESSAGE,
    LICENSE_ACKNOWLEDGEMENT_ENV,
)
from autospine_workbench.p10_runtime_capture_commands import (  # noqa: E402
    P10RuntimeCaptureCommandError,
    P10RuntimeCaptureCommandResult,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)


SHA = {str(index): str(index) * 64 for index in range(1, 8)}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="capture-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, Path("default-state"))
    return value


def argv(*, acknowledge: bool = False) -> list[str]:
    values = [
        "capture-body-sway-runtime", "sample",
        "--candidates", "candidates.json",
        "--decision", "decision.json",
        "--probe-report", "report.json",
        "--runtime-root", "licensed-runtime",
        "--browser-executable", "chrome.exe",
        "--state-root", "state",
        "--layer-manifest-sha256", SHA["1"],
        "--p3-rig-sha256", SHA["2"],
        "--p3-bundle-sha256", SHA["3"],
        "--motion-instance-sha256", SHA["4"],
        "--motion-retarget-bundle-sha256", SHA["5"],
        "--motion-instance-v2-sha256", SHA["6"],
        "--reviewed-motion-bundle-sha256", SHA["7"],
    ]
    if acknowledge:
        values.append("--acknowledge-spine-runtime-license")
    return values


def result() -> P10RuntimeCaptureCommandResult:
    return P10RuntimeCaptureCommandResult(
        path=Path("state/published"),
        temporary_preview_sha256="a" * 64,
        runtime_capture_sha256="b" * 64,
        artifact_set_sha256="c" * 64,
        bundle_sha256="d" * 64,
        case_count=19,
        browser_family="google-chrome",
        browser_reported_version="140.0.0.1",
        release_gate_status="blocked",
        release_gate_reason_codes=("manual_visual_review_required",),
        reused=False,
    )


class P10RuntimeCaptureCliTests(unittest.TestCase):
    def setUp(self):
        self.parser = parser()

    def test_parser_requires_runtime_browser_and_exact_addresses(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parser.parse_args(argv()[:-2])
        args = self.parser.parse_args(argv(acknowledge=True))
        self.assertEqual(Path("licensed-runtime"), args.runtime_root)
        self.assertEqual(Path("chrome.exe"), args.browser_executable)
        self.assertTrue(args.acknowledge_spine_runtime_license)

    @patch("autospine_workbench.p10_runtime_capture_cli.capture_body_sway_runtime_command")
    def test_dispatch_accepts_only_exact_one_environment_value(self, service):
        service.return_value = result()
        for value, expected in (("1", True), ("true", False), (" 1", False)):
            with self.subTest(value=value), patch.dict(
                os.environ, {LICENSE_ACKNOWLEDGEMENT_ENV: value}
            ), redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    self.parser.parse_args(argv())
                )
            self.assertEqual(0, status)
            self.assertIs(
                expected,
                service.call_args.kwargs["license_acknowledged"],
            )
            payload = json.loads(output.getvalue())
            self.assertEqual("captured_unreviewed", payload["status"])
            self.assertEqual("blocked", payload["release_gate"]["status"])
            self.assertEqual(19, payload["case_count"])
            self.assertFalse(payload["reused"])
            self.assertEqual({
                "ok", "status", "release_gate", "path",
                "temporary_preview_sha256", "runtime_capture_sha256",
                "artifact_set_sha256", "bundle_sha256", "case_count",
                "browser_family", "browser_reported_version", "reused",
            }, set(payload))
            self.assertNotIn("licensed-runtime", output.getvalue())
            self.assertNotIn("chrome.exe", output.getvalue())
            self.assertNotIn("manifest", output.getvalue())
            self.assertNotIn("png", output.getvalue().lower())

    @patch("autospine_workbench.p10_runtime_capture_cli.capture_body_sway_runtime_command")
    def test_flag_overrides_non_acknowledging_environment(self, service):
        private_root = r"C:\Users\private\licensed-runtime"
        service.side_effect = P10RuntimeCaptureCommandError(
            f"browser failed at {private_root}\\chrome.exe"
        )
        with patch.dict(
            os.environ, {LICENSE_ACKNOWLEDGEMENT_ENV: "0"}
        ), redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                self.parser.parse_args(argv(acknowledge=True))
            )
        self.assertEqual(2, status)
        self.assertTrue(service.call_args.kwargs["license_acknowledged"])
        self.assertEqual(
            {
                "error_code": CAPTURE_ERROR_CODE,
                "message": CAPTURE_ERROR_MESSAGE,
                "ok": False,
                "status": "error",
            },
            json.loads(output.getvalue()),
        )
        self.assertNotIn(private_root, output.getvalue())
        self.assertNotIn("chrome.exe", output.getvalue())


if __name__ == "__main__":
    unittest.main()
