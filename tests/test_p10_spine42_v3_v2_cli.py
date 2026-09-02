"""P10.7a v2 parser, dispatch, and redaction tests."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
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

import autospine_workbench.p10_spine42_v3_v2_cli as cli  # noqa: E402
from autospine_workbench.cli import build_parser  # noqa: E402
from autospine_workbench.p10_spine42_v3_commands_v2 import (  # noqa: E402
    P10Spine42V3CommandV2Error,
)


SHAS = tuple(character * 64 for character in "abcdef")


def parser():
    value = argparse.ArgumentParser(prog="spine42-v3-v2-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    cli.add_p10_spine42_v3_v2_subcommands(
        subparsers, Path("default-state")
    )
    return value


def compile_argv():
    return [
        cli.COMPILE_COMMAND, "fixture-project",
        "--motion-instance-v3-sha256", SHAS[0],
        "--motion-instance-v3-bundle-sha256", SHAS[1],
        "--workspace", r"C:\private\workspace",
        "--state-root", r"C:\private\state",
    ]


def verify_argv():
    return [
        cli.VERIFY_COMMAND, "fixture-project",
        "--skeleton-json-sha256", SHAS[2],
        "--bundle-sha256", SHAS[3],
        "--state-root", r"C:\private\state",
    ]


def result(mode):
    return SimpleNamespace(mode=mode, document={
        "project_id": "fixture-project", "clip_id": "idle",
        "address": {"skeleton_json_sha256": SHAS[2],
                    "bundle_sha256": SHAS[3]},
        "verification": {"status": "passed", "exact_readback": True},
    })


class P10Spine42V3V2CliTests(unittest.TestCase):
    def setUp(self):
        self.parser = parser()

    def test_root_registers_v1_and_v2_with_required_addresses(self):
        root = build_parser()
        for values, required in (
            (compile_argv(), ("--motion-instance-v3-sha256",
                              "--motion-instance-v3-bundle-sha256")),
            (verify_argv(), ("--skeleton-json-sha256", "--bundle-sha256")),
        ):
            self.assertEqual(values[0], root.parse_args(values).command)
            for option in required:
                attack = list(values)
                index = attack.index(option)
                del attack[index:index + 2]
                with redirect_stderr(io.StringIO()), self.assertRaises(
                    SystemExit
                ):
                    self.parser.parse_args(attack)
        self.assertEqual(
            "compile-body-sway-spine42-v3",
            root.parse_args([
                "compile-body-sway-spine42-v3", "fixture-project",
                "--motion-instance-v3-sha256", SHAS[0],
                "--motion-instance-v3-bundle-sha256", SHAS[1],
            ]).command,
        )

    def test_compile_and_verify_dispatch_exact_inputs(self):
        compile_result = result("compiled")
        store = SimpleNamespace(state_root=Path(r"C:\private\state"))
        capture = object()
        with patch.object(cli, "ProjectStore", return_value=store), patch.object(
            cli, "_ReadOnlyCaptureJobs", return_value=capture,
        ), patch.object(
            cli, "compile_body_sway_spine42_v3_v2_command",
            return_value=compile_result,
        ) as command, redirect_stdout(io.StringIO()) as output:
            status = cli.dispatch_p10_spine42_v3_v2_command(
                self.parser.parse_args(compile_argv())
            )
        self.assertEqual(0, status)
        command.assert_called_once_with(
            capture, store, "fixture-project",
            motion_instance_v3_sha256=SHAS[0],
            motion_instance_v3_bundle_sha256=SHAS[1],
        )
        self.assertNotIn(r"C:\private", output.getvalue())

        with patch.object(
            cli, "verify_body_sway_spine42_v3_v2_command",
            return_value=result("verified"),
        ) as command, redirect_stdout(io.StringIO()) as output:
            status = cli.dispatch_p10_spine42_v3_v2_command(
                self.parser.parse_args(verify_argv())
            )
        self.assertEqual(0, status)
        command.assert_called_once_with(
            Path(r"C:\private\state"), "fixture-project",
            skeleton_json_sha256=SHAS[2], bundle_sha256=SHAS[3],
        )
        self.assertTrue(json.loads(output.getvalue())["ok"])

    def test_failures_are_fixed_path_free_and_unrelated_is_ignored(self):
        private = r"C:\private\state\secret.json"
        for values, target, code, message in (
            (compile_argv(), "compile_body_sway_spine42_v3_v2_command",
             cli.COMPILE_ERROR_CODE, cli.COMPILE_ERROR_MESSAGE),
            (verify_argv(), "verify_body_sway_spine42_v3_v2_command",
             cli.VERIFY_ERROR_CODE, cli.VERIFY_ERROR_MESSAGE),
        ):
            with patch.object(
                cli, target, side_effect=P10Spine42V3CommandV2Error(private),
            ), patch.object(
                cli, "ProjectStore", return_value=SimpleNamespace(
                    state_root=Path(r"C:\private\state")
                ),
            ), redirect_stdout(io.StringIO()) as output:
                status = cli.dispatch_p10_spine42_v3_v2_command(
                    self.parser.parse_args(values)
                )
            self.assertEqual(2, status)
            self.assertEqual({
                "error_code": code, "message": message,
                "ok": False, "status": "error",
            }, json.loads(output.getvalue()))
            self.assertNotIn(private, output.getvalue())
        self.assertIsNone(cli.dispatch_p10_spine42_v3_v2_command(
            argparse.Namespace(command="unrelated")
        ))


if __name__ == "__main__":
    unittest.main()
