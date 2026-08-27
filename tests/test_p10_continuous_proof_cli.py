"""Parser, canonical output, and redaction tests for the P10.4b2 CLI."""

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

from autospine_workbench.p10_continuous_proof_cli import (  # noqa: E402
    COMMAND,
    ERROR_CODE,
)
from autospine_workbench.p10_continuous_proof_commands import (  # noqa: E402
    P10ContinuousProofCommandError,
)
from autospine_workbench.p10_exact_review_cli_fields import (  # noqa: E402
    CHAIN_OPTIONS,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)


SHAS = tuple(character * 64 for character in "abcdefghijklm")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="continuous-proof-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, Path("default-state"))
    return value


def argv() -> list[str]:
    values = [
        COMMAND, "sample", "--candidates", "private/candidates.json",
        "--decision", "private/decision.json",
        "--probe-report", "private/probe.json",
    ]
    for option, sha in zip(CHAIN_OPTIONS, SHAS[:12], strict=True):
        values.extend((option, sha))
    values.extend(("--visual-revision", "3", "--state-root", "private/state"))
    return values


def result() -> SimpleNamespace:
    claims = {
        "continuous_preview_model_structural_safety": True,
        "uniform_gain_zero_to_reviewed_structurally_certified": True,
        "runtime_equivalence": False, "visual_range": False,
        "reviewed_seam_anchors": False, "motion_instance_v3": False,
        "publishable_timeline": False, "release_authority": False,
    }
    gate = {"status": "blocked", "reason_codes": ["preview_model_only"]}
    document = {
        "status": "continuous_preview_model_structural_certified",
        "project_id": "sample", "clip_id": "idle", "claims": claims,
        "release_gate": gate, "summary": {"segment_count": 32},
    }
    return SimpleNamespace(
        input_paths=(Path(r"C:\private\input.json"),),
        project_id="sample", clip_id="idle",
        amplitude_envelope_sha256=SHAS[0],
        preview_projection_sha256=SHAS[1],
        visual_candidate_sha256=SHAS[2], visual_revision=3,
        visual_decision_sha256=SHAS[3],
        continuous_proof_sha256=SHAS[4], document=document,
    )


class P10ContinuousProofCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = parser()

    def test_parser_requires_every_exact_input(self):
        parsed = self.parser.parse_args(argv())
        self.assertEqual(COMMAND, parsed.command)
        for option in (
            "--candidates", "--decision", "--probe-report",
            *CHAIN_OPTIONS, "--visual-revision",
        ):
            values = argv()
            index = values.index(option)
            del values[index:index + 2]
            with self.subTest(option=option), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit):
                self.parser.parse_args(values)

    @patch(
        "autospine_workbench.p10_continuous_proof_cli."
        "compile_body_sway_continuous_proof_command"
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
        self.assertEqual(compiled.continuous_proof_sha256,
                         summary["continuous_proof_sha256"])
        self.assertEqual(compiled.document, document)
        self.assertNotIn("input_paths", outputs[0])
        self.assertNotIn(r"C:\private", "".join(outputs))

    @patch(
        "autospine_workbench.p10_continuous_proof_cli."
        "compile_body_sway_continuous_proof_command"
    )
    def test_failure_is_stable_and_redacted(self, call):
        private = r"C:\Users\private\probe.json"
        call.side_effect = P10ContinuousProofCommandError(private)
        with redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                self.parser.parse_args(argv())
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(2, status)
        self.assertEqual(ERROR_CODE, payload["error_code"])
        self.assertNotIn(private, output.getvalue())


if __name__ == "__main__":
    unittest.main()
