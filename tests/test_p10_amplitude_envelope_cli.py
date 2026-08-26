"""Parser, canonical output, and redaction tests for P10.4b1 CLI."""

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

from autospine_workbench.p10_amplitude_envelope_cli import (  # noqa: E402
    COMMAND,
    ERROR_CODE,
)
from autospine_workbench.p10_amplitude_envelope_commands import (  # noqa: E402
    P10AmplitudeEnvelopeCommandError,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)


SHAS = tuple(character * 64 for character in "abcdefghijklm")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="amplitude-envelope-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, Path("default-state"))
    return value


def argv() -> list[str]:
    values = [
        COMMAND, "sample", "--candidates", "private/candidates.json",
        "--decision", "private/decision.json",
        "--probe-report", "private/probe.json",
    ]
    for option, sha in zip(_SHA_OPTIONS, SHAS[:12], strict=True):
        values.extend((option, sha))
    values.extend(("--visual-revision", "3", "--state-root", "private/state"))
    return values


def result() -> SimpleNamespace:
    claims = {
        "sampled_visual_approved_at_reviewed_gain": True,
        "sampled_structural_gain_probes": True,
        "safe_range": False, "continuous_time": False,
        "visual_range": False, "reviewed_seam_anchors": False,
        "motion_instance_v3": False, "publishable_timeline": False,
        "release_authority": False,
    }
    gate = {"status": "blocked", "reason_codes": ["safe_range_unproven"]}
    document = {
        "status": "candidate_only", "project_id": "sample",
        "clip_id": "idle", "claims": claims, "release_gate": gate,
        "summary": {"gain_probe_count": 9},
    }
    return SimpleNamespace(
        input_paths=(Path(r"C:\private\input.json"),),
        project_id="sample", clip_id="idle",
        review_admission_sha256=SHAS[0],
        preview_projection_sha256=SHAS[1],
        visual_candidate_sha256=SHAS[2], visual_revision=3,
        visual_decision_sha256=SHAS[3],
        amplitude_envelope_sha256=SHAS[4], document=document,
    )


class P10AmplitudeEnvelopeCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = parser()

    def test_parser_requires_every_exact_input(self):
        parsed = self.parser.parse_args(argv())
        self.assertEqual(COMMAND, parsed.command)
        self.assertEqual(3, parsed.visual_revision)
        for option in (
            "--candidates", "--decision", "--probe-report",
            *_SHA_OPTIONS, "--visual-revision",
        ):
            values = argv()
            index = values.index(option)
            del values[index:index + 2]
            with self.subTest(option=option), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit):
                self.parser.parse_args(values)

    @patch(
        "autospine_workbench.p10_amplitude_envelope_cli."
        "compile_body_sway_amplitude_envelope_command"
    )
    def test_summary_and_document_only_are_canonical_and_path_free(self, call):
        compiled = result()
        call.return_value = compiled
        outputs = []
        for extra in ([], ["--document-only"]):
            with redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    self.parser.parse_args([*argv(), *extra])
                )
            self.assertEqual(0, status)
            outputs.append(output.getvalue().strip())
        summary, document = map(json.loads, outputs)
        self.assertEqual(compiled.amplitude_envelope_sha256,
                         summary["amplitude_envelope_sha256"])
        self.assertEqual(3, summary["visual_revision"])
        self.assertEqual(compiled.document, document)
        self.assertNotIn("input_paths", outputs[0])
        self.assertNotIn(r"C:\private", "".join(outputs))

    @patch(
        "autospine_workbench.p10_amplitude_envelope_cli."
        "compile_body_sway_amplitude_envelope_command"
    )
    def test_failure_is_stable_and_redacted(self, call):
        private = r"C:\Users\private\probe.json"
        call.side_effect = P10AmplitudeEnvelopeCommandError(private)
        with redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                self.parser.parse_args(argv())
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(2, status)
        self.assertEqual(ERROR_CODE, payload["error_code"])
        self.assertNotIn(private, output.getvalue())


_SHA_OPTIONS = (
    "--layer-manifest-sha256", "--p3-rig-sha256", "--p3-bundle-sha256",
    "--motion-instance-sha256", "--motion-retarget-bundle-sha256",
    "--motion-instance-v2-sha256", "--reviewed-motion-bundle-sha256",
    "--temporary-preview-sha256", "--runtime-capture-bundle-sha256",
    "--capture-artifact-set-sha256", "--visual-candidate-sha256",
    "--visual-decision-sha256",
)


if __name__ == "__main__":
    unittest.main()
