"""Automatic argument, output, and redaction tests for P10.4a v2 CLI."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
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

from autospine_workbench.p10_review_admission_v2_cli import (  # noqa: E402
    COMPILE_COMMAND, ERROR_CODE, VERIFY_COMMAND,
)
from autospine_workbench.p10_review_admission_v2_commands import (  # noqa: E402
    P10ReviewAdmissionV2CommandError,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands, dispatch_projection_stage_command,
)


JOB = "a" * 64


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="review-admission-v2-test")
    subparsers = value.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, Path("project/workspace"))
    return value


def compiled_result():
    claims = {
        "completed_sampled_execution_bound": True,
        "sampled_visual_approved": True,
        "official_runtime_execution_replayed": True,
        "head_observed_at_compile_time": True,
        "safe_range": False, "continuous_time": False,
        "reviewed_seam_anchors": False,
        "inter_attachment_seam_safety": False,
        "publishable_timeline": False, "release_authority": False,
    }
    gate = {"status": "blocked", "reason_codes": ["safe_range_unproven"]}
    document = {
        "format": "autospine-body-sway-review-admission",
        "format_version": 2, "project_id": "sample", "clip_id": "wave",
        "claims": claims, "release_gate": gate,
        "status": "admitted_for_safety_analysis",
    }
    return SimpleNamespace(
        job_id=JOB, package_id="b" * 64, project_id="sample",
        clip_id="wave", terminal_event_sha256="c" * 64,
        terminal_sequence=12, visual_candidate_sha256="d" * 64,
        visual_revision=3, visual_decision_sha256="e" * 64,
        admission_sha256="f" * 64, document=document,
    )


class P10ReviewAdmissionV2CliTests(unittest.TestCase):
    def setUp(self):
        self.parser = parser()
        self.store = SimpleNamespace(state_root=Path("private/state"))

    def test_compile_parser_needs_only_job_and_supports_all_head_pins(self):
        parsed = self.parser.parse_args([COMPILE_COMMAND, JOB])
        self.assertEqual(JOB, parsed.job_id)
        self.assertIsNone(parsed.expected_candidate_sha256)
        values = [
            COMPILE_COMMAND, JOB,
            "--expected-candidate-sha256", "1" * 64,
            "--expected-visual-revision", "7",
            "--expected-decision-sha256", "2" * 64,
        ]
        parsed = self.parser.parse_args(values)
        self.assertEqual(7, parsed.expected_visual_revision)

    @patch("autospine_workbench.p10_review_admission_v2_cli._ReadOnlyCaptureJobs")
    @patch("autospine_workbench.p10_review_admission_v2_cli.ProjectStore")
    @patch(
        "autospine_workbench.p10_review_admission_v2_cli."
        "compile_body_sway_review_admission_v2_for_job"
    )
    def test_summary_and_document_only_are_path_free(
        self, compile_, project_store, jobs,
    ):
        result = compiled_result()
        compile_.return_value = result
        project_store.return_value = self.store
        outputs = []
        for extra in ([], ["--document-only"]):
            with redirect_stdout(io.StringIO()) as output:
                status = dispatch_projection_stage_command(
                    self.parser.parse_args([COMPILE_COMMAND, JOB, *extra])
                )
            self.assertEqual(0, status)
            outputs.append(output.getvalue().strip())
        summary, document = map(json.loads, outputs)
        self.assertEqual(result.admission_sha256, summary["admission_sha256"])
        self.assertEqual(3, summary["visual_revision"])
        self.assertEqual(result.document, document)
        self.assertNotIn("private", "".join(outputs).lower())
        jobs.assert_called_with(self.store.state_root)

    @patch("autospine_workbench.p10_review_admission_v2_cli._ReadOnlyCaptureJobs")
    @patch("autospine_workbench.p10_review_admission_v2_cli.ProjectStore")
    @patch(
        "autospine_workbench.p10_review_admission_v2_cli."
        "compile_body_sway_review_admission_v2_for_job"
    )
    def test_compile_failure_is_stable_and_redacted(
        self, compile_, project_store, _jobs,
    ):
        project_store.return_value = self.store
        compile_.side_effect = P10ReviewAdmissionV2CommandError(
            r"C:\Users\private\decision.json"
        )
        with redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                self.parser.parse_args([COMPILE_COMMAND, JOB])
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(2, status)
        self.assertEqual(ERROR_CODE, payload["error_code"])
        self.assertNotIn("private", output.getvalue().lower())

    @patch("autospine_workbench.p10_review_admission_v2_cli._ReadOnlyCaptureJobs")
    @patch("autospine_workbench.p10_review_admission_v2_cli.ProjectStore")
    @patch("autospine_workbench.p10_review_admission_v2_cli.strict_json_object")
    @patch("autospine_workbench.p10_review_admission_v2_cli.read_real_file")
    @patch(
        "autospine_workbench.p10_review_admission_v2_cli."
        "require_current_body_sway_review_admission_v2"
    )
    def test_verify_recompiles_current_authority(
        self, consume, read, parse, project_store, _jobs,
    ):
        project_store.return_value = self.store
        document = compiled_result().document
        read.return_value = b"{}"
        parse.return_value = document
        consume.return_value = SimpleNamespace(
            job_id=JOB, admission_sha256="f" * 64, document=document,
        )
        with redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(
                self.parser.parse_args([VERIFY_COMMAND, "admission.json"])
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(0, status)
        self.assertEqual("current", payload["status"])
        consume.assert_called_once()


if __name__ == "__main__":
    unittest.main()
