"""Parser, JSON dispatch, and root CLI tests for P6 Spine exports."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.cli import (  # noqa: E402
    build_parser as build_root_parser,
    main as root_main,
)
from autospine_workbench.spine42_commands import (  # noqa: E402
    Spine42CommandError,
    Spine42CommandResult,
)
from autospine_workbench.spine42_stage_cli import (  # noqa: E402
    add_spine42_stage_subcommands,
    dispatch_spine42_stage_command,
)


SHA = {
    name: character * 64
    for name, character in (
        ("p3_rig", "1"), ("p3_bundle", "2"),
        ("motion_instance", "3"), ("motion_bundle", "4"),
        ("skeleton", "5"), ("atlas", "6"), ("png", "7"),
        ("run_identity", "8"), ("run", "9"), ("report", "a"),
        ("bundle", "b"), ("target", "c"),
    )
}


def parser(default: Path) -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="p6-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    add_spine42_stage_subcommands(subparsers, default)
    return value


def result(*, motion: bool = True) -> Spine42CommandResult:
    p5 = None if not motion else {
        "target_profile_sha256": SHA["target"],
        "motion_instance_sha256": SHA["motion_instance"],
        "bundle_sha256": SHA["motion_bundle"],
        "clip_id": "idle",
    }
    return Spine42CommandResult(
        Path("state/builds/project/spine42/skeleton/bundle"),
        "project",
        "motion" if motion else "setup-only",
        "idle" if motion else None,
        SHA["skeleton"], SHA["atlas"], SHA["png"],
        SHA["run_identity"], SHA["run"], SHA["report"], SHA["bundle"],
        "mode=motion;clip=idle;bones=20;slots=17;attachments=17;animations=1;events=0",
        False,
        (
            ("p3", tuple({
                "rig_sha256": SHA["p3_rig"],
                "bundle_sha256": SHA["p3_bundle"],
            }.items())),
            ("p5", None if p5 is None else tuple(p5.items())),
        ),
    )


def compile_argv(*, motion: bool = True) -> list[str]:
    values = [
        "compile-spine42", "project",
        "--p3-rig-sha256", SHA["p3_rig"],
        "--p3-bundle-sha256", SHA["p3_bundle"],
    ]
    if motion:
        values.extend([
            "--motion-instance-sha256", SHA["motion_instance"],
            "--motion-bundle-sha256", SHA["motion_bundle"],
        ])
    return values


class Spine42StageCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = Path("exact-state")
        self.parser = parser(self.state)

    def dispatch(self, argv: list[str]) -> tuple[int | None, dict]:
        output = io.StringIO()
        with redirect_stdout(output):
            status = dispatch_spine42_stage_command(
                self.parser.parse_args(argv)
            )
        return status, json.loads(output.getvalue())

    def test_parser_preserves_explicit_setup_motion_and_verify_addresses(self):
        setup = self.parser.parse_args(compile_argv(motion=False))
        self.assertIsNone(setup.motion_instance_sha256)
        self.assertIsNone(setup.motion_bundle_sha256)
        motion = self.parser.parse_args(compile_argv())
        self.assertEqual(SHA["motion_instance"], motion.motion_instance_sha256)
        self.assertEqual(SHA["motion_bundle"], motion.motion_bundle_sha256)
        verified = self.parser.parse_args([
            "verify-spine42", "project",
            "--skeleton-json-sha256", SHA["skeleton"],
            "--bundle-sha256", SHA["bundle"],
            "--state-root", "other-state",
        ])
        self.assertEqual(Path("other-state"), verified.state_root)

        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parser.parse_args(["compile-spine42", "project"])
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parser.parse_args([
                "verify-spine42", "project",
                "--bundle-sha256", SHA["bundle"],
            ])

    def test_dispatches_exact_calls_and_prints_all_identities(self):
        with patch(
            "autospine_workbench.spine42_stage_cli.compile_spine42_bundle",
            return_value=result(),
        ) as service:
            status, response = self.dispatch(compile_argv())
        self.assertEqual(0, status)
        service.assert_called_once_with(
            self.state,
            "project",
            p3_rig_sha256=SHA["p3_rig"],
            p3_bundle_sha256=SHA["p3_bundle"],
            motion_instance_sha256=SHA["motion_instance"],
            motion_bundle_sha256=SHA["motion_bundle"],
        )
        self.assertTrue(response["ok"])
        self.assertEqual("passed", response["status"])
        self.assertEqual(result().source_addresses, response["source_addresses"])
        self.assertEqual(result().output_sha256s, response["output_sha256s"])
        for name in (
            "path", "project_id", "mode", "clip_id",
            "skeleton_json_sha256", "atlas_sha256", "png_sha256",
            "run_identity_sha256", "run_sha256", "report_sha256",
            "bundle_sha256", "summary", "reused",
        ):
            self.assertIn(name, response)

        with patch(
            "autospine_workbench.spine42_stage_cli.verify_spine42_bundle",
            return_value=result(),
        ) as service:
            status, _response = self.dispatch([
                "verify-spine42", "project",
                "--skeleton-json-sha256", SHA["skeleton"],
                "--bundle-sha256", SHA["bundle"],
            ])
        self.assertEqual(0, status)
        service.assert_called_once_with(
            self.state,
            "project",
            skeleton_json_sha256=SHA["skeleton"],
            bundle_sha256=SHA["bundle"],
        )

    def test_service_error_is_fail_loud_json_and_unknown_is_unclaimed(self):
        with patch(
            "autospine_workbench.spine42_stage_cli.compile_spine42_bundle",
            side_effect=Spine42CommandError("exact rebuild failed"),
        ):
            status, response = self.dispatch(compile_argv(motion=False))
        self.assertEqual(2, status)
        self.assertEqual({
            "ok": False,
            "status": "error",
            "error": "exact rebuild failed",
        }, response)

        output = io.StringIO()
        with redirect_stdout(output):
            status = dispatch_spine42_stage_command(
                argparse.Namespace(command="unrelated")
            )
        self.assertIsNone(status)
        self.assertEqual("", output.getvalue())

    def test_root_cli_registers_and_routes_both_commands(self):
        parsed = build_root_parser().parse_args(compile_argv())
        self.assertEqual("compile-spine42", parsed.command)
        self.assertEqual(SHA["p3_rig"], parsed.p3_rig_sha256)
        self.assertEqual(SHA["motion_instance"], parsed.motion_instance_sha256)

        with patch(
            "autospine_workbench.spine42_stage_cli.compile_spine42_bundle",
            return_value=result(),
        ) as service, redirect_stdout(io.StringIO()):
            status = root_main([*compile_argv(), "--state-root", str(self.state)])
        self.assertEqual(0, status)
        service.assert_called_once_with(
            self.state,
            "project",
            p3_rig_sha256=SHA["p3_rig"],
            p3_bundle_sha256=SHA["p3_bundle"],
            motion_instance_sha256=SHA["motion_instance"],
            motion_bundle_sha256=SHA["motion_bundle"],
        )

        with patch(
            "autospine_workbench.spine42_stage_cli.verify_spine42_bundle",
            return_value=result(),
        ) as service, redirect_stdout(io.StringIO()):
            status = root_main([
                "verify-spine42", "project",
                "--skeleton-json-sha256", SHA["skeleton"],
                "--bundle-sha256", SHA["bundle"],
                "--state-root", str(self.state),
            ])
        self.assertEqual(0, status)
        service.assert_called_once_with(
            self.state,
            "project",
            skeleton_json_sha256=SHA["skeleton"],
            bundle_sha256=SHA["bundle"],
        )

    def test_root_cli_rejects_half_motion_pair_as_json_without_writing(self):
        with TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            output = io.StringIO()
            with redirect_stdout(output):
                status = root_main([
                    *compile_argv(motion=False),
                    "--motion-instance-sha256", SHA["motion_instance"],
                    "--state-root", str(state),
                ])
            response = json.loads(output.getvalue())
            self.assertEqual(2, status)
            self.assertFalse(response["ok"])
            self.assertIn("supplied together", response["error"])
            self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main()
