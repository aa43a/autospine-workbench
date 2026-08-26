"""Parser, canonical stdout, and zero-write tests for P9.5 CLI commands."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.cli import main  # noqa: E402
from autospine_workbench.p9_v2_commands import (  # noqa: E402
    P9V2CommandError,
    P9V2CommandResult,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)
from tests.p9_v2_helpers import tree  # noqa: E402
from tests.p9_v2_real_chain import P9V2RealFixture  # noqa: E402


SHA = {str(index): str(index) * 64 for index in range(1, 7)}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    subparsers = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, Path("state"))
    return value


def result() -> P9V2CommandResult:
    return P9V2CommandResult(
        input_paths=(Path("input"),),
        report_sha256="f" * 64,
        report={"format": "autospine-test-v2", "format_version": 1},
    )


def compile_argv(*extra: str) -> list[str]:
    return [
        "compile-motion-instance-v2", "sample",
        "--motion-instance-sha256", SHA["1"],
        "--motion-retarget-bundle-sha256", SHA["2"],
        "--reviewed-policy", "policy.json",
        *extra,
    ]


def export_argv(*extra: str) -> list[str]:
    return [
        "export-spine42-v2", "sample",
        "--p3-rig-sha256", SHA["3"],
        "--p3-bundle-sha256", SHA["4"],
        "--motion-instance-sha256", SHA["1"],
        "--motion-retarget-bundle-sha256", SHA["2"],
        "--reviewed-policy", "policy.json",
        *extra,
    ]


class P9V2CliDispatchTests(unittest.TestCase):
    def test_both_commands_dispatch_exact_addresses(self) -> None:
        cases = (
            (
                compile_argv(),
                "compile_motion_instance_v2_command",
                (Path("state"), "sample", Path("policy.json")),
                {
                    "motion_instance_sha256": SHA["1"],
                    "motion_retarget_bundle_sha256": SHA["2"],
                },
            ),
            (
                export_argv(),
                "export_spine42_v2_command",
                (Path("state"), "sample", Path("policy.json")),
                {
                    "p3_rig_sha256": SHA["3"],
                    "p3_bundle_sha256": SHA["4"],
                    "motion_instance_sha256": SHA["1"],
                    "motion_retarget_bundle_sha256": SHA["2"],
                },
            ),
        )
        for argv, service_name, positional, keywords in cases:
            with self.subTest(command=argv[0]), patch(
                f"autospine_workbench.p9_v2_cli.{service_name}",
                return_value=result(),
            ) as service, redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    parser().parse_args(argv)
                )
            self.assertEqual(0, status)
            service.assert_called_once_with(*positional, **keywords)
            line = output.getvalue().strip()
            payload = json.loads(line)
            self.assertEqual(
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                line,
            )
            self.assertTrue(payload["ok"])

    def test_document_only_prints_the_unwrapped_canonical_report(self) -> None:
        for argv, service_name in (
            (compile_argv("--document-only"), "compile_motion_instance_v2_command"),
            (export_argv("--document-only"), "export_spine42_v2_command"),
        ):
            with self.subTest(command=argv[0]), patch(
                f"autospine_workbench.p9_v2_cli.{service_name}",
                return_value=result(),
            ), redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    parser().parse_args(argv)
                )
            self.assertEqual(0, status)
            self.assertEqual(
                '{"format":"autospine-test-v2","format_version":1}',
                output.getvalue().strip(),
            )

    def test_domain_error_is_canonical_and_returns_two(self) -> None:
        with patch(
            "autospine_workbench.p9_v2_cli.compile_motion_instance_v2_command",
            side_effect=P9V2CommandError("broken"),
        ), redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                parser().parse_args(compile_argv())
            )
        self.assertEqual(2, status)
        self.assertEqual(
            {"error": "broken", "ok": False, "status": "error"},
            json.loads(output.getvalue()),
        )


class P9V2RealCliTests(unittest.TestCase):
    def test_both_real_cli_paths_compile_in_memory_without_state_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = P9V2RealFixture(Path(temporary))
            base = [
                fixture.project_id,
                "--motion-instance-sha256", fixture.p5_address.instance_sha256,
                "--motion-retarget-bundle-sha256", fixture.p5_address.bundle_sha256,
                "--reviewed-policy", str(fixture.policy_path),
                "--state-root", str(fixture.state),
                "--document-only",
            ]
            commands = (
                ["compile-motion-instance-v2", *base],
                [
                    "export-spine42-v2", *base,
                    "--p3-rig-sha256", fixture.p3_rig_sha256,
                    "--p3-bundle-sha256", fixture.p3_bundle_sha256,
                ],
            )
            for argv in commands:
                before = tree(fixture.state)
                with self.subTest(command=argv[0]), redirect_stdout(
                    io.StringIO()
                ) as output:
                    status = main(argv)
                self.assertEqual(0, status)
                self.assertEqual(before, tree(fixture.state))
                line = output.getvalue().strip()
                report = json.loads(line)
                self.assertEqual(
                    json.dumps(
                        report, ensure_ascii=False, allow_nan=False,
                        sort_keys=True, separators=(",", ":"),
                    ),
                    line,
                )
                self.assertNotIn("png_bytes", line)
                if argv[0] == "export-spine42-v2":
                    self.assertEqual(17, len(report["skeleton_json"]["bones"]))
                    self.assertEqual(
                        {"face-layer"},
                        set(report["source"]["source_image_sha256s"]),
                    )
                    self.assertTrue(report["atlas_text"].startswith(
                        "skeleton.png\n"
                    ))


if __name__ == "__main__":
    unittest.main()
