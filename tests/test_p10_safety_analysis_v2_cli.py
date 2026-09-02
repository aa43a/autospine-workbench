"""Job-only parser, output, and redaction tests for P10.4b v2 CLI."""

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

from autospine_workbench.p10_safety_analysis_v2_cli import (  # noqa: E402
    COMPILE_COMMAND, ERROR_CODE,
)
from autospine_workbench.p10_safety_analysis_v2_commands import (  # noqa: E402
    P10SafetyAnalysisV2CommandError,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands, dispatch_projection_stage_command,
)


JOB = "a" * 64


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="safety-analysis-v2-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, Path("project/workspace"))
    return value


def compiled_result():
    amplitude = {
        "format": "autospine-body-sway-amplitude-envelope-candidate",
        "format_version": 2, "status": "candidate_only",
        "probes": [
            {
                "gain": {"numerator": value, "denominator": 8},
                "status": "sampled_structural_passed",
                "visual_review_status": (
                    "official_runtime_sampled_cases_approved"
                    if value == 8 else "not_reviewed"
                ),
            }
            for value in range(9)
        ],
    }
    continuous = {
        "format": "autospine-body-sway-continuous-preview-proof",
        "format_version": 2, "status": "indeterminate",
        "summary": {
            "segment_count": 2, "certified_segment_count": 1,
            "indeterminate_segment_count": 1,
        },
        "claims": {
            "continuous_preview_model_structural_safety": False,
            "release_authority": False,
        },
        "release_gate": {
            "status": "blocked",
            "reason_codes": ["continuous_structural_proof_indeterminate"],
        },
    }
    return SimpleNamespace(
        job_id=JOB, package_id="b" * 64,
        project_id="sample", clip_id="wave",
        admission_sha256="c" * 64,
        amplitude_sha256="d" * 64,
        continuous_sha256="e" * 64,
        status="indeterminate",
        amplitude_document=amplitude,
        continuous_document=continuous,
    )


class P10SafetyAnalysisV2CliTests(unittest.TestCase):
    def setUp(self):
        self.parser = parser()
        self.store = SimpleNamespace(state_root=Path("private/state"))

    def test_parser_needs_only_job_and_has_no_file_or_sha_inputs(self):
        parsed = self.parser.parse_args([COMPILE_COMMAND, JOB])
        self.assertEqual(JOB, parsed.job_id)
        self.assertFalse(parsed.documents)
        self.assertEqual(
            {"command", "job_id", "documents", "workspace", "state_root"},
            set(vars(parsed)),
        )
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.parser.parse_args([
                    COMPILE_COMMAND, JOB, "--admission-sha256", "f" * 64,
                ])

    @patch("autospine_workbench.p10_safety_analysis_v2_cli._ReadOnlyCaptureJobs")
    @patch("autospine_workbench.p10_safety_analysis_v2_cli.ProjectStore")
    @patch(
        "autospine_workbench.p10_safety_analysis_v2_cli."
        "compile_p10_safety_analysis_v2_for_job"
    )
    def test_summary_is_path_free_and_keeps_release_blocked(
        self, compile_, project_store, jobs,
    ):
        result = compiled_result()
        compile_.return_value = result
        project_store.return_value = self.store
        with redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                self.parser.parse_args([COMPILE_COMMAND, JOB])
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(0, status)
        self.assertEqual("indeterminate", payload["status"])
        self.assertEqual(9, payload["amplitude"]["probe_count"])
        self.assertEqual("reviewed_gain_only", payload["amplitude"]["visual_review_scope"])
        self.assertEqual("blocked", payload["release_gate"]["status"])
        self.assertNotIn("documents", payload)
        self.assertNotIn("private", output.getvalue().lower())
        compile_.assert_called_once_with(jobs.return_value, self.store, JOB)
        jobs.assert_called_once_with(self.store.state_root)

    @patch("autospine_workbench.p10_safety_analysis_v2_cli._ReadOnlyCaptureJobs")
    @patch("autospine_workbench.p10_safety_analysis_v2_cli.ProjectStore")
    @patch(
        "autospine_workbench.p10_safety_analysis_v2_cli."
        "compile_p10_safety_analysis_v2_for_job"
    )
    def test_documents_flag_emits_both_canonical_v2_documents(
        self, compile_, project_store, _jobs,
    ):
        result = compiled_result()
        compile_.return_value = result
        project_store.return_value = self.store
        with redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                self.parser.parse_args([COMPILE_COMMAND, JOB, "--documents"])
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(0, status)
        self.assertEqual(result.amplitude_document, payload["documents"]["amplitude"])
        self.assertEqual(result.continuous_document, payload["documents"]["continuous"])

    @patch("autospine_workbench.p10_safety_analysis_v2_cli._ReadOnlyCaptureJobs")
    @patch("autospine_workbench.p10_safety_analysis_v2_cli.ProjectStore")
    @patch(
        "autospine_workbench.p10_safety_analysis_v2_cli."
        "compile_p10_safety_analysis_v2_for_job"
    )
    def test_failure_is_stable_and_redacts_internal_details(
        self, compile_, project_store, _jobs,
    ):
        project_store.return_value = self.store
        compile_.side_effect = P10SafetyAnalysisV2CommandError(
            r"C:\Users\private\continuous.json"
        )
        with redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                self.parser.parse_args([COMPILE_COMMAND, JOB])
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(2, status)
        self.assertEqual(ERROR_CODE, payload["error_code"])
        self.assertNotIn("private", output.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
