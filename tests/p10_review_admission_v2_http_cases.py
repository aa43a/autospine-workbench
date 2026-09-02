"""Reusable live-HTTP cases for the P10.4a v2 admission route."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from autospine_workbench.p10_review_admission_v2_commands import (
    P10ReviewAdmissionV2CommandError,
)
from autospine_workbench.p10_visual_review_v2_context import (
    P10VisualReviewV2JobIncomplete,
)


def _sha(value: str) -> str:
    return value * 64


class P10ReviewAdmissionV2HttpCases:
    """Verify the read-only response, status mapping, and redaction."""

    def configure_review_admission_v2_http(self) -> None:
        self.admission_document = {
            "format": "autospine-body-sway-review-admission",
            "format_version": 2,
            "status": "admitted_for_safety_analysis",
            "claims": {
                "sampled_visual_approved": True,
                "continuous_time": False,
                "release_authority": False,
            },
            "release_gate": {
                "status": "blocked",
                "reason_codes": ["continuous_time_safety_unproven"],
            },
        }
        self.admission_result = SimpleNamespace(
            job_id=self.job_id, package_id=_sha("5"),
            terminal_event_sha256=_sha("b"), terminal_sequence=50,
            project_id="fixture-project", clip_id="wave-left-v1",
            temporary_preview_v2_sha256=_sha("6"),
            runtime_execution_sha256=_sha("c"),
            runtime_execution_bundle_sha256=_sha("7"),
            capture_artifact_set_sha256=_sha("8"),
            visual_candidate_sha256=self.candidate_sha,
            visual_revision=1, visual_decision_sha256=self.decision_sha,
            admission_sha256=_sha("d"), document=self.admission_document,
        )
        self.compile_admission = Mock(return_value=self.admission_result)
        self.patches.append(patch(
            "autospine_workbench.p10_review_admission_v2_http."
            "compile_body_sway_review_admission_v2_for_job",
            self.compile_admission,
        ))

    def test_admission_get_is_path_free_and_read_only(self):
        endpoint = f"{self.base}/admission"
        status, headers, value = self.json_request("GET", endpoint)
        self.assertEqual(200, status)
        self.assertEqual("no-store", headers["cache-control"])
        self.assertTrue(value["ok"])
        self.assertEqual(_sha("d"), value["admission_sha256"])
        self.assertEqual(self.admission_document, value["document"])
        self.assertEqual(self.job_id, value["job"]["job_id"])
        self.assertEqual(self.candidate_sha,
                         value["inputs"]["visual_candidate_sha256"])
        self.assertNotIn(r"C:\\", json.dumps(value))
        self.compile_admission.assert_called_once_with(
            self.manager, self.server.project_store, self.job_id,
        )

        status, headers, raw = self.request("OPTIONS", endpoint)
        self.assertEqual((204, b""), (status, raw))
        self.assertEqual("GET, HEAD, OPTIONS", headers["allow"])
        status, headers, value = self.json_request("POST", endpoint, {})
        self.assertEqual(405, status)
        self.assertEqual("GET, HEAD, OPTIONS", headers["allow"])
        self.assertEqual("method_not_allowed", value["error"])

    def test_admission_incomplete_job_is_actionable_409(self):
        def incomplete(*_args, **_kwargs):
            try:
                raise P10VisualReviewV2JobIncomplete(
                    r"C:\Users\private\capture-job.json"
                )
            except P10VisualReviewV2JobIncomplete as exc:
                raise P10ReviewAdmissionV2CommandError(
                    "admission failed"
                ) from exc

        self.compile_admission.side_effect = incomplete
        status, _, value = self.json_request(
            "GET", f"{self.base}/admission",
        )
        self.assertEqual(409, status)
        self.assertEqual("runtime_capture_job_not_completed", value["error"])
        self.assertNotIn("private", json.dumps(value))

    def test_admission_without_approved_head_is_actionable_409(self):
        self.compile_admission.side_effect = P10ReviewAdmissionV2CommandError(
            "Completed job has no current visual review v2 decision"
        )
        status, _, value = self.json_request(
            "GET", f"{self.base}/admission",
        )
        self.assertEqual(409, status)
        self.assertEqual(
            "body_sway_review_admission_v2_not_ready", value["error"],
        )

    def test_admission_internal_error_never_leaks_private_path(self):
        private = r"C:\Users\private\review-admission.json"
        self.compile_admission.side_effect = P10ReviewAdmissionV2CommandError(
            private
        )
        status, _, value = self.json_request(
            "GET", f"{self.base}/admission",
        )
        self.assertEqual(500, status)
        self.assertEqual("body_sway_review_admission_v2_error",
                         value["error"])
        self.assertNotIn(private, json.dumps(value))


__all__ = ["P10ReviewAdmissionV2HttpCases"]
