"""Parser, dispatch, and redaction tests for automatic P10.6a v2 CLI."""

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
from autospine_workbench.p10_motion_consumer_admission_commands_v2 import (  # noqa: E402
    P10MotionConsumerAdmissionCommandV2Error,
)
from autospine_workbench.p10_motion_consumer_admission_v2_cli import (  # noqa: E402
    COMMAND, ERROR_CODE,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)
from tests.p10_motion_consumer_admission_v2_command_helpers import (  # noqa: E402
    SHAS,
)


TARGET = (
    "autospine_workbench.p10_motion_consumer_admission_v2_cli."
    "compile_body_sway_motion_consumer_admission_v2_command"
)


def parser():
    value = argparse.ArgumentParser()
    subs = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subs, Path("default-state"))
    return value


def argv():
    return [
        COMMAND, "fixture-project",
        "--dynamic-seam-probe-sha256", SHAS[0],
        "--dynamic-seam-bundle-sha256", SHAS[1],
        "--workspace", r"C:\private\workspace",
        "--state-root", r"C:\private\state",
    ]


def result():
    return SimpleNamespace(document={
        "project_id": "fixture-project", "clip_id": "idle",
        "dynamic_seam_address": {
            "probe_sha256": SHAS[0], "bundle_sha256": SHAS[1],
        },
        "body_sway_motion_consumer_admission_v2_sha256": SHAS[4],
        "admission": {"format_version": 2},
    })


class P10MotionConsumerAdmissionV2CliTests(unittest.TestCase):
    def test_parser_requires_only_project_and_two_exact_addresses(self):
        value = parser()
        parsed = value.parse_args(argv())
        self.assertEqual(COMMAND, parsed.command)
        self.assertFalse(hasattr(parsed, "dynamic_seam_probe"))
        for option in (
            "--dynamic-seam-probe-sha256",
            "--dynamic-seam-bundle-sha256",
        ):
            values = argv()
            index = values.index(option)
            del values[index:index + 2]
            with self.subTest(option=option), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit):
                value.parse_args(values)

    @patch(TARGET)
    def test_success_is_canonical_path_free_and_root_dispatches(self, command):
        command.return_value = result()
        with redirect_stdout(io.StringIO()) as output:
            status = main(argv())
        payload = json.loads(output.getvalue())
        self.assertEqual(0, status)
        self.assertTrue(payload["ok"])
        self.assertEqual("compiled", payload["status"])
        self.assertNotIn(r"C:\private", output.getvalue())
        called = command.call_args
        self.assertEqual("fixture-project", called.args[2])
        self.assertEqual(SHAS[0], called.kwargs[
            "dynamic_seam_probe_sha256"
        ])
        self.assertEqual(SHAS[1], called.kwargs[
            "dynamic_seam_bundle_sha256"
        ])

    @patch(TARGET)
    def test_failure_is_stable_redacted_and_router_keeps_v1(self, command):
        command.side_effect = P10MotionConsumerAdmissionCommandV2Error(
            r"C:\private\bundle.json"
        )
        with redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                parser().parse_args(argv())
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(2, status)
        self.assertEqual(ERROR_CODE, payload["error_code"])
        self.assertNotIn("private", output.getvalue())
        choices = build_parser()._subparsers._group_actions[0].choices
        self.assertIn(COMMAND, choices)
        self.assertIn("compile-body-sway-motion-consumer-admission", choices)

    def test_unrelated_command_returns_none(self):
        self.assertIsNone(dispatch_projection_stage_command(
            argparse.Namespace(command="not-p10.6a")
        ))


if __name__ == "__main__":
    unittest.main()
