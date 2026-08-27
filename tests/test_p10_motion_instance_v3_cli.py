"""Parser, canonical output, and redaction tests for P10.6b CLI."""

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

import autospine_workbench.p10_motion_instance_v3_cli as cli  # noqa: E402
from autospine_workbench.cli import build_parser  # noqa: E402
from autospine_workbench.p10_motion_instance_v3_commands import (  # noqa: E402
    P10MotionInstanceV3CommandError,
)


SHAS = tuple(character * 64 for character in "abcdef")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="motion-instance-v3-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    cli.add_p10_motion_instance_v3_subcommands(
        subparsers, Path("default-state")
    )
    return value


def compile_argv() -> list[str]:
    return [
        cli.COMPILE_COMMAND, "fixture-project",
        "--admission-wrapper", r"C:\private\p10.6a.json",
        "--admission-sha256", SHAS[0],
        "--state-root", r"C:\private\state",
    ]


def verify_argv() -> list[str]:
    return [
        cli.VERIFY_COMMAND, "fixture-project",
        "--motion-instance-v3-sha256", SHAS[1],
        "--bundle-sha256", SHAS[2],
        "--state-root", r"C:\private\state",
    ]


def result(mode: str) -> SimpleNamespace:
    document = {
        "project_id": "fixture-project",
        "clip_id": "idle",
        "source": {"admission_sha256": SHAS[0]},
        "address": {
            "motion_instance_v3_sha256": SHAS[1],
            "bundle_sha256": SHAS[2],
        },
        "run_sha256": SHAS[3],
        "inventory": [
            "body-sway-motion-consumer-admission.json",
            "motion-instance-v3.json",
            "run-manifest.json",
        ],
        "reused": False if mode == "compiled" else None,
        "head_check": {
            "scope": (
                "prepublication_compile" if mode == "compiled"
                else "historical_replay"
            ),
            "current_heads_observed": mode == "compiled",
            "permanent_authority_claimed": False,
        },
        "verification": {
            "status": "passed", "exact_historical_replay": True,
        },
    }
    return SimpleNamespace(mode=mode, document=document)


class P10MotionInstanceV3CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = parser()

    def test_parser_requires_exact_addresses_and_keeps_state_default(self):
        cases = (
            (compile_argv(), ("--admission-wrapper", "--admission-sha256")),
            (
                verify_argv(),
                ("--motion-instance-v3-sha256", "--bundle-sha256"),
            ),
        )
        for values, required in cases:
            with self.subTest(command=values[0]):
                self.assertEqual(values[0], self.parser.parse_args(values).command)
            for option in required:
                attack = list(values)
                index = attack.index(option)
                del attack[index:index + 2]
                with self.subTest(option=option), redirect_stderr(
                    io.StringIO()
                ), self.assertRaises(SystemExit):
                    self.parser.parse_args(attack)
            without_root = list(values)
            index = without_root.index("--state-root")
            del without_root[index:index + 2]
            self.assertEqual(
                Path("default-state"),
                self.parser.parse_args(without_root).state_root,
            )

    def test_compile_success_is_canonical_path_free_and_exactly_dispatched(self):
        compiled = result("compiled")
        with patch.object(
            cli, "compile_body_sway_motion_instance_v3_command",
            return_value=compiled,
        ) as command, redirect_stdout(io.StringIO()) as output:
            status = cli.dispatch_p10_motion_instance_v3_command(
                self.parser.parse_args(compile_argv())
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(0, status)
        self.assertTrue(payload["ok"])
        self.assertEqual("compiled", payload["status"])
        self.assertEqual(
            json.dumps(
                payload, ensure_ascii=False, allow_nan=False,
                sort_keys=True, separators=(",", ":"),
            ),
            output.getvalue().strip(),
        )
        self.assertNotIn(r"C:\private", output.getvalue())
        command.assert_called_once_with(
            Path(r"C:\private\state"), "fixture-project",
            Path(r"C:\private\p10.6a.json"), admission_sha256=SHAS[0],
        )

    def test_verify_success_uses_only_the_exact_historical_address(self):
        verified = result("verified")
        with patch.object(
            cli, "verify_body_sway_motion_instance_v3_command",
            return_value=verified,
        ) as command, redirect_stdout(io.StringIO()) as output:
            status = cli.dispatch_p10_motion_instance_v3_command(
                self.parser.parse_args(verify_argv())
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(0, status)
        self.assertEqual("verified", payload["status"])
        self.assertFalse(payload["head_check"]["current_heads_observed"])
        self.assertFalse(payload["head_check"][
            "permanent_authority_claimed"
        ])
        command.assert_called_once_with(
            Path(r"C:\private\state"), "fixture-project",
            motion_instance_v3_sha256=SHAS[1], bundle_sha256=SHAS[2],
        )

    def test_failures_are_fixed_redacted_and_unrelated_is_ignored(self):
        cases = (
            (
                compile_argv(), "compile_body_sway_motion_instance_v3_command",
                cli.COMPILE_ERROR_CODE, cli.COMPILE_ERROR_MESSAGE,
            ),
            (
                verify_argv(), "verify_body_sway_motion_instance_v3_command",
                cli.VERIFY_ERROR_CODE, cli.VERIFY_ERROR_MESSAGE,
            ),
        )
        private = r"C:\private\state\forged.json: internal detail"
        for values, target, code, message in cases:
            with self.subTest(command=values[0]), patch.object(
                cli, target,
                side_effect=P10MotionInstanceV3CommandError(private),
            ), redirect_stdout(io.StringIO()) as output:
                status = cli.dispatch_p10_motion_instance_v3_command(
                    self.parser.parse_args(values)
                )
            payload = json.loads(output.getvalue())
            self.assertEqual(2, status)
            self.assertEqual({
                "error_code": code, "message": message,
                "ok": False, "status": "error",
            }, payload)
            self.assertNotIn(private, output.getvalue())
            self.assertNotIn(r"C:\private", output.getvalue())
        self.assertIsNone(cli.dispatch_p10_motion_instance_v3_command(
            argparse.Namespace(command="not-p10.6b")
        ))

    def test_root_parser_registers_compile_and_verify(self):
        root = build_parser()
        self.assertEqual(
            cli.COMPILE_COMMAND,
            root.parse_args(compile_argv()).command,
        )
        self.assertEqual(
            cli.VERIFY_COMMAND,
            root.parse_args(verify_argv()).command,
        )


if __name__ == "__main__":
    unittest.main()
