"""Parser, canonical output, and redaction tests for P10.7a CLI."""

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

import autospine_workbench.p10_spine42_v3_cli as cli  # noqa: E402
from autospine_workbench.cli import build_parser  # noqa: E402
from autospine_workbench.p10_spine42_v3_commands import (  # noqa: E402
    P10Spine42V3CommandError,
)


SHAS = tuple(character * 64 for character in "abcdef")


def parser():
    value = argparse.ArgumentParser(prog="spine42-v3-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    cli.add_p10_spine42_v3_subcommands(subparsers, Path("default-state"))
    return value


def compile_argv():
    return [
        cli.COMPILE_COMMAND, "fixture-project",
        "--motion-instance-v3-sha256", SHAS[0],
        "--motion-instance-v3-bundle-sha256", SHAS[1],
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
        "project_id": "fixture-project",
        "clip_id": "idle",
        "address": {
            "skeleton_json_sha256": SHAS[2],
            "bundle_sha256": SHAS[3],
        },
        "head_check": {
            "current_heads_observed": mode == "compiled",
            "permanent_authority_claimed": False,
        },
        "authority": {"spine_adapter_emitted": True},
        "reused": False if mode == "compiled" else None,
    })


class P10Spine42V3CliTests(unittest.TestCase):
    def setUp(self):
        self.parser = parser()

    def test_parser_requires_exact_addresses_and_root_registers_both(self):
        cases = (
            (compile_argv(), (
                "--motion-instance-v3-sha256",
                "--motion-instance-v3-bundle-sha256",
            )),
            (verify_argv(), (
                "--skeleton-json-sha256", "--bundle-sha256",
            )),
        )
        root = build_parser()
        for values, required in cases:
            self.assertEqual(values[0], root.parse_args(values).command)
            for option in required:
                attack = list(values)
                index = attack.index(option)
                del attack[index:index + 2]
                with redirect_stderr(io.StringIO()), self.assertRaises(
                    SystemExit
                ):
                    self.parser.parse_args(attack)

    def test_compile_and_verify_dispatch_exact_path_free_inputs(self):
        cases = (
            (
                compile_argv(),
                "compile_body_sway_spine42_v3_command",
                result("compiled"),
                {
                    "motion_instance_v3_sha256": SHAS[0],
                    "motion_instance_v3_bundle_sha256": SHAS[1],
                },
            ),
            (
                verify_argv(),
                "verify_body_sway_spine42_v3_command",
                result("verified"),
                {
                    "skeleton_json_sha256": SHAS[2],
                    "bundle_sha256": SHAS[3],
                },
            ),
        )
        for values, target, returned, kwargs in cases:
            with self.subTest(command=values[0]), patch.object(
                cli, target, return_value=returned
            ) as command, redirect_stdout(io.StringIO()) as output:
                status = cli.dispatch_p10_spine42_v3_command(
                    self.parser.parse_args(values)
                )
            payload = json.loads(output.getvalue())
            self.assertEqual(0, status)
            self.assertTrue(payload["ok"])
            self.assertNotIn(r"C:\private", output.getvalue())
            command.assert_called_once_with(
                Path(r"C:\private\state"), "fixture-project", **kwargs
            )

    def test_failures_are_fixed_redacted_and_unrelated_is_ignored(self):
        cases = (
            (compile_argv(), "compile_body_sway_spine42_v3_command",
             cli.COMPILE_ERROR_CODE, cli.COMPILE_ERROR_MESSAGE),
            (verify_argv(), "verify_body_sway_spine42_v3_command",
             cli.VERIFY_ERROR_CODE, cli.VERIFY_ERROR_MESSAGE),
        )
        private = r"C:\private\state\secret.json"
        for values, target, code, message in cases:
            with patch.object(
                cli, target, side_effect=P10Spine42V3CommandError(private)
            ), redirect_stdout(io.StringIO()) as output:
                status = cli.dispatch_p10_spine42_v3_command(
                    self.parser.parse_args(values)
                )
            self.assertEqual(2, status)
            self.assertEqual({
                "error_code": code, "message": message,
                "ok": False, "status": "error",
            }, json.loads(output.getvalue()))
            self.assertNotIn(private, output.getvalue())
        self.assertIsNone(cli.dispatch_p10_spine42_v3_command(
            argparse.Namespace(command="unrelated")
        ))


if __name__ == "__main__":
    unittest.main()
