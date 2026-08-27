"""Parser, license-gate, dispatch, and redaction tests for P10.7b."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.cli import build_parser, main
import autospine_workbench.p10_spine42_v3_runtime_cli as cli
from autospine_workbench.p10_spine42_v3_runtime_commands import (
    P10Spine42V3RuntimeCommandError,
)


SHAS = tuple(character * 64 for character in "abcd")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="spine42-v3-runtime-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    cli.add_p10_spine42_v3_runtime_subcommands(
        subparsers, Path("default-state")
    )
    return value


def capture_argv(*, acknowledge: bool = False) -> list[str]:
    values = [
        cli.CAPTURE_COMMAND, "fixture-project",
        "--skeleton-json-sha256", SHAS[0],
        "--spine42-v3-bundle-sha256", SHAS[1],
        "--runtime-root", r"C:\private\runtime",
        "--browser-executable", r"C:\private\chrome.exe",
        "--state-root", r"C:\private\state",
    ]
    if acknowledge:
        values.append("--acknowledge-spine-runtime-license")
    return values


def verify_argv() -> list[str]:
    return [
        cli.VERIFY_COMMAND, "fixture-project",
        "--spine42-v3-bundle-sha256", SHAS[1],
        "--capture-bundle-sha256", SHAS[2],
        "--state-root", r"C:\private\state",
    ]


def result(mode: str) -> SimpleNamespace:
    return SimpleNamespace(
        mode=mode, path=Path("state/published"),
        project_id="fixture-project", clip_id="idle",
        skeleton_json_sha256=SHAS[0],
        spine42_v3_bundle_sha256=SHAS[1],
        capture_plan_sha256=SHAS[2], raster_metrics_sha256=SHAS[3],
        manifest_sha256="e" * 64, capture_bundle_sha256="f" * 64,
        browser_family="google-chrome",
        browser_reported_version="151.0.0.1",
        case_count=9, attachment_count=4, artifact_count=54,
        metrics_status="passed", release_gate_status="blocked",
        reused=False if mode == "captured" else None,
    )


class P10Spine42V3RuntimeCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = parser()

    def test_parser_requires_exact_capture_and_verify_addresses(self):
        cases = (
            (capture_argv(acknowledge=True), (
                "--skeleton-json-sha256", "--spine42-v3-bundle-sha256",
                "--runtime-root", "--browser-executable",
            )),
            (verify_argv(), (
                "--spine42-v3-bundle-sha256", "--capture-bundle-sha256",
            )),
        )
        for values, required in cases:
            self.assertEqual(values[0], build_parser().parse_args(values).command)
            for option in required:
                attack = list(values)
                index = attack.index(option)
                del attack[index:index + 2]
                with self.subTest(option=option), redirect_stderr(
                    io.StringIO()
                ), self.assertRaises(SystemExit):
                    self.parser.parse_args(attack)

    @patch.object(cli, "capture_body_sway_spine42_v3_runtime_command")
    def test_capture_license_gate_is_fail_closed_and_exact(self, service):
        service.return_value = result("captured")
        for value, expected in ((None, False), ("true", False), (" 1", False),
                                ("1", True)):
            environment = {} if value is None else {
                cli.LICENSE_ACKNOWLEDGEMENT_ENV: value
            }
            service.reset_mock()
            with self.subTest(value=value), patch.dict(
                os.environ, environment, clear=True
            ), redirect_stdout(io.StringIO()) as output:
                status = cli.dispatch_p10_spine42_v3_runtime_command(
                    self.parser.parse_args(capture_argv())
                )
            self.assertEqual(0 if expected else 2, status)
            if expected:
                service.assert_called_once_with(
                    Path(r"C:\private\state"), "fixture-project",
                    skeleton_json_sha256=SHAS[0],
                    spine42_v3_bundle_sha256=SHAS[1],
                    runtime_root=Path(r"C:\private\runtime"),
                    browser_executable=Path(r"C:\private\chrome.exe"),
                    license_acknowledged=True,
                )
                self.assertEqual("captured", json.loads(
                    output.getvalue()
                )["status"])
            else:
                service.assert_not_called()
                self.assertEqual(cli.CAPTURE_ERROR_CODE, json.loads(
                    output.getvalue()
                )["error_code"])

    @patch.object(cli, "capture_body_sway_spine42_v3_runtime_command")
    def test_explicit_acknowledgement_dispatches_through_root(self, service):
        service.return_value = result("captured")
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(
            io.StringIO()
        ) as output:
            status = main(capture_argv(acknowledge=True))
        self.assertEqual(0, status)
        self.assertTrue(service.call_args.kwargs["license_acknowledged"])
        payload = json.loads(output.getvalue())
        self.assertEqual(54, payload["summary"]["artifact_count"])
        self.assertEqual("blocked", payload["release_gate"]["status"])

        private = r"C:\private\runtime\spine-player.js"
        service.side_effect = P10Spine42V3RuntimeCommandError(private)
        with redirect_stdout(io.StringIO()) as output:
            status = cli.dispatch_p10_spine42_v3_runtime_command(
                self.parser.parse_args(capture_argv(acknowledge=True))
            )
        self.assertEqual(2, status)
        self.assertEqual({
            "error_code": cli.CAPTURE_ERROR_CODE,
            "message": cli.CAPTURE_ERROR_MESSAGE,
            "ok": False, "status": "error",
        }, json.loads(output.getvalue()))
        self.assertNotIn(private, output.getvalue())

    @patch.object(cli, "verify_body_sway_spine42_v3_runtime_command")
    def test_verify_dispatch_and_all_failures_are_fixed_redacted(self, service):
        service.return_value = result("verified")
        with redirect_stdout(io.StringIO()) as output:
            status = cli.dispatch_p10_spine42_v3_runtime_command(
                self.parser.parse_args(verify_argv())
            )
        self.assertEqual(0, status)
        service.assert_called_once_with(
            Path(r"C:\private\state"), "fixture-project",
            spine42_v3_bundle_sha256=SHAS[1],
            capture_bundle_sha256=SHAS[2],
        )
        self.assertEqual("verified", json.loads(output.getvalue())["status"])

        private = r"C:\private\state\secret.json"
        service.side_effect = P10Spine42V3RuntimeCommandError(private)
        with redirect_stdout(io.StringIO()) as output:
            status = cli.dispatch_p10_spine42_v3_runtime_command(
                self.parser.parse_args(verify_argv())
            )
        self.assertEqual(2, status)
        self.assertEqual({
            "error_code": cli.VERIFY_ERROR_CODE,
            "message": cli.VERIFY_ERROR_MESSAGE,
            "ok": False, "status": "error",
        }, json.loads(output.getvalue()))
        self.assertNotIn(private, output.getvalue())
        self.assertIsNone(cli.dispatch_p10_spine42_v3_runtime_command(
            argparse.Namespace(command="unrelated")
        ))


if __name__ == "__main__":
    unittest.main()
