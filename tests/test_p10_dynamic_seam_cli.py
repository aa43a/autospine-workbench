"""Parser, dispatch, canonical output, and redaction tests for P10.5d."""

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

from autospine_workbench.cli import build_parser, main  # noqa: E402
from autospine_workbench.p10_dynamic_seam_cli import (  # noqa: E402
    COMMAND,
    ERROR_CODE,
)
from autospine_workbench.p10_dynamic_seam_commands import (  # noqa: E402
    P10DynamicSeamCommandError,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)
from tests.p10_dynamic_seam_command_helpers import SHAS  # noqa: E402


TARGET = (
    "autospine_workbench.p10_dynamic_seam_cli."
    "compile_body_sway_dynamic_seam_probe_command"
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="dynamic-seam-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, Path("default-state"))
    return value


def argv() -> list[str]:
    return [
        COMMAND,
        "fixture-project",
        "--continuous-proof",
        r"C:\private\proof.json",
        "--reviewed-set-sha256",
        SHAS[1],
        "--reviewed-set-bundle-sha256",
        SHAS[2],
        "--state-root",
        r"C:\private\state",
    ]


def result():
    return SimpleNamespace(document={
        "project_id": "fixture-project",
        "clip_id": "idle",
        "body_sway_dynamic_seam_probe_sha256": SHAS[4],
        "probe": {"status": "fixture-probe-status"},
        "head_observation": {
            "method": "outer-before-after-analysis-of-inner-double-snapshots",
            "scope": "compile_time",
            "permanent_authority_claimed": False,
        },
    })


class P10DynamicSeamCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = parser()

    def test_parser_requires_all_explicit_inputs_and_has_state_default(self):
        parsed = self.parser.parse_args(argv())
        self.assertEqual(COMMAND, parsed.command)
        for option in (
            "--continuous-proof",
            "--reviewed-set-sha256",
            "--reviewed-set-bundle-sha256",
        ):
            values = argv()
            index = values.index(option)
            del values[index:index + 2]
            with self.subTest(option=option), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit):
                self.parser.parse_args(values)
        values = argv()
        index = values.index("--state-root")
        del values[index:index + 2]
        self.assertEqual(
            Path("default-state"), self.parser.parse_args(values).state_root
        )

    @patch(TARGET)
    def test_success_is_canonical_path_free_and_main_dispatches(self, command):
        command.return_value = result()
        with redirect_stdout(io.StringIO()) as output:
            status = main(argv())
        payload = json.loads(output.getvalue())
        self.assertEqual(0, status)
        self.assertTrue(payload["ok"])
        self.assertEqual("compiled", payload["status"])
        self.assertIn("probe", payload)
        self.assertIn("head_observation", payload)
        self.assertNotIn(r"C:\private", output.getvalue())
        command.assert_called_once_with(
            Path(r"C:\private\state"),
            "fixture-project",
            Path(r"C:\private\proof.json"),
            reviewed_set_sha256=SHAS[1],
            reviewed_set_bundle_sha256=SHAS[2],
        )

    @patch(TARGET)
    def test_failure_is_exit_two_stable_and_redacted(self, command):
        private = r"C:\private\proof.json: forged"
        command.side_effect = P10DynamicSeamCommandError(private)
        with redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                self.parser.parse_args(argv())
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(2, status)
        self.assertEqual(ERROR_CODE, payload["error_code"])
        self.assertEqual("error", payload["status"])
        self.assertNotIn(private, output.getvalue())
        self.assertNotIn(r"C:\private", output.getvalue())

    def test_unrelated_command_returns_none(self):
        self.assertIsNone(dispatch_projection_stage_command(
            argparse.Namespace(command="not-p10.5d")
        ))
        self.assertIn(COMMAND, build_parser()._subparsers._group_actions[0]
                      .choices)


if __name__ == "__main__":
    unittest.main()
