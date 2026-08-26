"""Parser and dispatch tests for the read-only P9 command surface."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.p9_readonly_commands import (  # noqa: E402
    P9ReadOnlyCommandError,
    P9ReadOnlyCommandResult,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)


SHA = {str(index): str(index) * 64 for index in range(1, 9)}


def parser(default: Path) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="p9-test")
    subparsers = result.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, default)
    return result


def command_result() -> P9ReadOnlyCommandResult:
    return P9ReadOnlyCommandResult(
        input_bundle_paths=(Path("state/input-a"), Path("state/input-b")),
        report_sha256="a" * 64,
        report={
            "format": "autospine-test-report",
            "semantics": {"runtime_timeline_emitted": False},
        },
    )


class P9ReadOnlyCliTests(unittest.TestCase):
    def setUp(self):
        self.state = Path("state")
        self.parser = parser(self.state)

    def test_parser_requires_policy_addresses_and_explicit_thresholds(self):
        parsed = self.parser.parse_args([
            "probe-foot-lock", "sample",
            "--projected-motion-sha256", SHA["1"],
            "--projected-bundle-sha256", SHA["2"],
            "--motion-instance-sha256", SHA["3"],
            "--motion-retarget-bundle-sha256", SHA["4"],
            "--max-correction-reference-ratio", "0.25",
            "--max-residual-px", "3.5",
        ])
        self.assertEqual(0.25, parsed.max_correction_reference_ratio)
        self.assertEqual(3.5, parsed.max_residual_px)
        self.assertEqual(self.state, parsed.state_root)
        invalid = [
            "compile-heading-evidence",
            "--motion-sha256", SHA["1"],
            "--motion-bundle-sha256", SHA["2"],
            "--projected-motion-sha256", SHA["3"],
            "--projected-bundle-sha256", SHA["4"],
        ]
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parser.parse_args(invalid)

    def test_all_four_commands_dispatch_exact_arguments(self):
        cases = (
            (
                [
                    "compile-kimodo-policy-evidence",
                    "--motion-sha256", SHA["1"],
                    "--motion-bundle-sha256", SHA["2"],
                    "--projected-motion-sha256", SHA["3"],
                    "--projected-bundle-sha256", SHA["4"],
                ],
                "compile_kimodo_policy_evidence_command",
                (self.state,),
                {
                    "motion_sha256": SHA["1"],
                    "motion_bundle_sha256": SHA["2"],
                    "projected_motion_sha256": SHA["3"],
                    "projected_bundle_sha256": SHA["4"],
                },
            ),
            (
                [
                    "compile-heading-evidence", "--policy-map", "policy.json",
                    "--motion-sha256", SHA["1"],
                    "--motion-bundle-sha256", SHA["2"],
                    "--projected-motion-sha256", SHA["3"],
                    "--projected-bundle-sha256", SHA["4"],
                ],
                "compile_heading_evidence_command",
                (self.state, Path("policy.json")),
                {
                    "motion_sha256": SHA["1"],
                    "motion_bundle_sha256": SHA["2"],
                    "projected_motion_sha256": SHA["3"],
                    "projected_bundle_sha256": SHA["4"],
                },
            ),
            (
                [
                    "probe-foot-lock", "sample",
                    "--projected-motion-sha256", SHA["1"],
                    "--projected-bundle-sha256", SHA["2"],
                    "--motion-instance-sha256", SHA["3"],
                    "--motion-retarget-bundle-sha256", SHA["4"],
                    "--max-correction-reference-ratio", "0.25",
                    "--max-residual-px", "3.5",
                ],
                "probe_foot_lock_command",
                (self.state, "sample"),
                {
                    "projected_motion_sha256": SHA["1"],
                    "projected_bundle_sha256": SHA["2"],
                    "motion_instance_sha256": SHA["3"],
                    "motion_retarget_bundle_sha256": SHA["4"],
                    "max_correction_reference_ratio": 0.25,
                    "max_residual_px": 3.5,
                },
            ),
            (
                [
                    "probe-depth-order", "sample", "--policy", "depth.json",
                    "--projected-motion-sha256", SHA["1"],
                    "--projected-bundle-sha256", SHA["2"],
                    "--motion-instance-sha256", SHA["3"],
                    "--motion-retarget-bundle-sha256", SHA["4"],
                    "--p3-rig-sha256", SHA["5"],
                    "--p3-bundle-sha256", SHA["6"],
                ],
                "probe_depth_order_command",
                (self.state, "sample", Path("depth.json")),
                {
                    "projected_motion_sha256": SHA["1"],
                    "projected_bundle_sha256": SHA["2"],
                    "motion_instance_sha256": SHA["3"],
                    "motion_retarget_bundle_sha256": SHA["4"],
                    "p3_rig_sha256": SHA["5"],
                    "p3_bundle_sha256": SHA["6"],
                },
            ),
        )
        for argv, service_name, positional, keywords in cases:
            with self.subTest(command=argv[0]), patch(
                f"autospine_workbench.p9_readonly_cli.{service_name}",
                return_value=command_result(),
            ) as service, redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    self.parser.parse_args(argv)
                )
            self.assertEqual(0, status)
            service.assert_called_once_with(*positional, **keywords)
            line = output.getvalue().strip()
            payload = json.loads(line)
            self.assertEqual(
                json.dumps(payload, ensure_ascii=False, allow_nan=False,
                           sort_keys=True, separators=(",", ":")),
                line,
            )
            self.assertTrue(payload["ok"])
            self.assertEqual(
                [str(Path("state/input-a")), str(Path("state/input-b"))],
                payload["input_bundle_paths"],
            )

    def test_domain_error_is_canonical_and_returns_two(self):
        argv = [
            "compile-kimodo-policy-evidence",
            "--motion-sha256", SHA["1"],
            "--motion-bundle-sha256", SHA["2"],
            "--projected-motion-sha256", SHA["3"],
            "--projected-bundle-sha256", SHA["4"],
        ]
        with patch(
            "autospine_workbench.p9_readonly_cli."
            "compile_kimodo_policy_evidence_command",
            side_effect=P9ReadOnlyCommandError("broken"),
        ), redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                self.parser.parse_args(argv)
            )
        self.assertEqual(2, status)
        self.assertEqual(
            {"error": "broken", "ok": False, "status": "error"},
            json.loads(output.getvalue()),
        )

    def test_document_only_prints_a_canonical_handoff_document(self):
        argv = [
            "compile-kimodo-policy-evidence", "--document-only",
            "--motion-sha256", SHA["1"],
            "--motion-bundle-sha256", SHA["2"],
            "--projected-motion-sha256", SHA["3"],
            "--projected-bundle-sha256", SHA["4"],
        ]
        with patch(
            "autospine_workbench.p9_readonly_cli."
            "compile_kimodo_policy_evidence_command",
            return_value=command_result(),
        ), redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                self.parser.parse_args(argv)
            )
        self.assertEqual(0, status)
        self.assertEqual(command_result().report, json.loads(output.getvalue()))
        self.assertNotIn("input_bundle_paths", output.getvalue())


if __name__ == "__main__":
    unittest.main()
