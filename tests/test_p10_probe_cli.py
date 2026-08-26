"""Parser and canonical dispatch tests for the P10.2 probe CLI."""

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

from autospine_workbench.p10_probe_commands import (  # noqa: E402
    P10ProbeCommandError,
    P10ProbeCommandResult,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)


FIELDS = (
    "layer-manifest-sha256",
    "p3-rig-sha256",
    "p3-bundle-sha256",
    "motion-instance-sha256",
    "motion-retarget-bundle-sha256",
    "motion-instance-v2-sha256",
    "reviewed-motion-bundle-sha256",
)
SHAS = {field: f"{index:x}" * 64 for index, field in enumerate(FIELDS, 1)}


def parser(default=Path("state")):
    value = argparse.ArgumentParser()
    subparsers = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, default)
    return value


def argv(*extra):
    values = [
        "compile-body-sway-probe", "sample",
        "--candidates", "candidates.json",
        "--decision", "decision.json",
    ]
    for field in FIELDS:
        values.extend((f"--{field}", SHAS[field]))
    return [*values, *extra]


def result():
    return P10ProbeCommandResult(
        input_paths=tuple(Path(f"exact/{index}") for index in range(6)),
        idle_behavior_candidates_sha256="a" * 64,
        idle_behavior_decision_sha256="b" * 64,
        body_sway_probe_report_sha256="c" * 64,
        document={
            "format": "autospine-body-sway-probe-report",
            "status": "manual_visual_required",
        },
    )


class P10ProbeCliTests(unittest.TestCase):
    def test_parser_requires_seven_addresses_and_two_files(self):
        parsed = parser().parse_args(argv())
        self.assertEqual("sample", parsed.project_id)
        self.assertEqual(Path("candidates.json"), parsed.candidates)
        self.assertEqual(Path("decision.json"), parsed.decision)
        self.assertEqual(Path("state"), parsed.state_root)
        for flag in (*FIELDS, "candidates", "decision"):
            values = argv()
            option = f"--{flag}"
            index = values.index(option)
            del values[index:index + 2]
            with self.subTest(flag=flag), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit):
                parser().parse_args(values)

    def test_dispatch_passes_all_exact_inputs_and_never_claims_passed(self):
        with patch(
            "autospine_workbench.p10_probe_cli."
            "compile_body_sway_probe_command",
            return_value=result(),
        ) as service, redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                parser(Path("default")).parse_args(
                    argv("--state-root", "override")
                )
            )
        self.assertEqual(0, status)
        service.assert_called_once_with(
            Path("override"), "sample", Path("candidates.json"),
            Path("decision.json"),
            layer_manifest_sha256=SHAS["layer-manifest-sha256"],
            p3_rig_sha256=SHAS["p3-rig-sha256"],
            p3_bundle_sha256=SHAS["p3-bundle-sha256"],
            motion_instance_sha256=SHAS["motion-instance-sha256"],
            motion_retarget_bundle_sha256=(
                SHAS["motion-retarget-bundle-sha256"]
            ),
            motion_instance_v2_sha256=SHAS["motion-instance-v2-sha256"],
            reviewed_motion_bundle_sha256=(
                SHAS["reviewed-motion-bundle-sha256"]
            ),
        )
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual("completed_diagnostic", payload["status"])
        self.assertNotEqual("passed", payload["status"])
        self.assertEqual(6, len(payload["input_paths"]))

    def test_document_only_is_stable_canonical_and_unwrapped(self):
        lines = []
        for _index in range(2):
            with patch(
                "autospine_workbench.p10_probe_cli."
                "compile_body_sway_probe_command",
                return_value=result(),
            ), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(0, dispatch_projection_stage_command(
                    parser().parse_args(argv("--document-only"))
                ))
            lines.append(output.getvalue().strip())
        self.assertEqual(lines[0], lines[1])
        self.assertEqual(result().document, json.loads(lines[0]))
        self.assertNotIn("input_paths", lines[0])
        self.assertEqual(json.dumps(
            result().document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ), lines[0])

    def test_domain_error_is_canonical_and_returns_two(self):
        with patch(
            "autospine_workbench.p10_probe_cli."
            "compile_body_sway_probe_command",
            side_effect=P10ProbeCommandError("broken"),
        ), redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                parser().parse_args(argv())
            )
        self.assertEqual(2, status)
        self.assertEqual(
            {"error": "broken", "ok": False, "status": "error"},
            json.loads(output.getvalue()),
        )


if __name__ == "__main__":
    unittest.main()
