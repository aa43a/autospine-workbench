"""Parser, routing, and redaction tests for P10.6b v2 CLI."""

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
from autospine_workbench.p10_motion_instance_v3_commands_v2 import (  # noqa: E402
    P10MotionInstanceV3CommandV2Error,
)
from autospine_workbench.p10_motion_instance_v3_v2_cli import (  # noqa: E402
    COMPILE_COMMAND, COMPILE_ERROR_CODE, VERIFY_COMMAND,
    VERIFY_ERROR_CODE,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)


SHAS = tuple(f"{index:064x}" for index in range(1, 8))
TARGET = "autospine_workbench.p10_motion_instance_v3_v2_cli"


def parser():
    value = argparse.ArgumentParser()
    subs = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subs, Path("default-state"))
    return value


def compile_argv():
    return [
        COMPILE_COMMAND, "fixture-project",
        "--dynamic-seam-probe-sha256", SHAS[0],
        "--dynamic-seam-bundle-sha256", SHAS[1],
        "--workspace", r"C:\private\workspace",
        "--state-root", r"C:\private\state",
    ]


def verify_argv():
    return [
        VERIFY_COMMAND, "fixture-project",
        "--motion-instance-v3-sha256", SHAS[2],
        "--bundle-sha256", SHAS[3],
        "--state-root", r"C:\private\state",
    ]


def result(mode):
    return SimpleNamespace(mode=mode, document={
        "project_id": "fixture-project", "clip_id": "idle",
        "address": {
            "motion_instance_v3_sha256": SHAS[2],
            "bundle_sha256": SHAS[3],
        },
    })


class P10MotionInstanceV3V2CliTests(unittest.TestCase):
    def test_compile_parser_accepts_no_file_admission_or_p9_input(self):
        value = parser()
        parsed = value.parse_args(compile_argv())
        self.assertEqual(COMPILE_COMMAND, parsed.command)
        for forbidden in (
            "admission_wrapper", "admission_sha256", "dynamic_seam_probe",
            "motion_instance_v2_sha256", "reviewed_motion_bundle_sha256",
        ):
            self.assertFalse(hasattr(parsed, forbidden), forbidden)
        for option in (
            "--dynamic-seam-probe-sha256",
            "--dynamic-seam-bundle-sha256",
        ):
            values = compile_argv()
            index = values.index(option)
            del values[index:index + 2]
            with self.subTest(option=option), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit):
                value.parse_args(values)

    def test_compile_root_dispatch_is_canonical_and_path_free(self):
        store = SimpleNamespace(state_root=Path("state"))
        command_target = (
            f"{TARGET}.compile_body_sway_motion_instance_v3_v2_command"
        )
        with patch(f"{TARGET}.ProjectStore", return_value=store), \
                patch(f"{TARGET}._ReadOnlyCaptureJobs",
                      return_value="capture") as jobs, \
                patch(command_target, return_value=result("compiled")) \
                as command, redirect_stdout(io.StringIO()) as output:
            status = main(compile_argv())
        payload = json.loads(output.getvalue())
        self.assertEqual(0, status)
        self.assertTrue(payload["ok"])
        self.assertEqual("compiled", payload["status"])
        self.assertNotIn("private", output.getvalue())
        jobs.assert_called_once_with(store.state_root)
        call = command.call_args
        self.assertEqual(("capture", store, "fixture-project"), call.args)
        self.assertEqual(SHAS[0], call.kwargs[
            "dynamic_seam_probe_sha256"
        ])
        self.assertEqual(SHAS[1], call.kwargs[
            "dynamic_seam_bundle_sha256"
        ])

    def test_verify_dispatches_only_explicit_historical_address(self):
        target = f"{TARGET}.verify_body_sway_motion_instance_v3_v2_command"
        with patch(target, return_value=result("verified")) as command, \
                redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                parser().parse_args(verify_argv())
            )
        self.assertEqual(0, status)
        self.assertEqual("verified", json.loads(output.getvalue())["status"])
        call = command.call_args
        self.assertEqual("fixture-project", call.args[1])
        self.assertEqual(SHAS[2], call.kwargs[
            "motion_instance_v3_sha256"
        ])
        self.assertEqual(SHAS[3], call.kwargs["bundle_sha256"])

    def test_failures_are_fixed_redacted_and_v1_router_remains(self):
        commands = (
            (COMPILE_COMMAND, compile_argv(), COMPILE_ERROR_CODE,
             "compile_body_sway_motion_instance_v3_v2_command"),
            (VERIFY_COMMAND, verify_argv(), VERIFY_ERROR_CODE,
             "verify_body_sway_motion_instance_v3_v2_command"),
        )
        for name, values, code, function in commands:
            with self.subTest(command=name), \
                    patch(f"{TARGET}.ProjectStore", return_value=
                          SimpleNamespace(state_root=Path("state"))), \
                    patch(f"{TARGET}._ReadOnlyCaptureJobs",
                          return_value="capture"), \
                    patch(f"{TARGET}.{function}", side_effect=
                          P10MotionInstanceV3CommandV2Error(
                              r"C:\private\bundle.json"
                          )), redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    parser().parse_args(values)
                )
            payload = json.loads(output.getvalue())
            self.assertEqual(2, status)
            self.assertEqual(code, payload["error_code"])
            self.assertNotIn("private", output.getvalue())
        choices = build_parser()._subparsers._group_actions[0].choices
        self.assertIn(COMPILE_COMMAND, choices)
        self.assertIn(VERIFY_COMMAND, choices)
        self.assertIn("compile-body-sway-motion-instance-v3", choices)
        self.assertIn("verify-body-sway-motion-instance-v3", choices)

    def test_unrelated_command_returns_none(self):
        from autospine_workbench.p10_motion_instance_v3_v2_cli import (
            dispatch_p10_motion_instance_v3_v2_command,
        )
        self.assertIsNone(dispatch_p10_motion_instance_v3_v2_command(
            argparse.Namespace(command="not-p10.6b")
        ))


if __name__ == "__main__":
    unittest.main()
