"""Completed-job and current-head tests for P10.3c v2 routing context."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.p10_capture_job_contract import (  # noqa: E402
    P10CaptureJobRequest,
)
from autospine_workbench.p10_visual_review_v2_context import (  # noqa: E402
    P10VisualReviewV2JobIncomplete, P10VisualReviewV2JobNotFound,
    P10VisualReviewV2SourceChanged,
    resolve_p10_visual_review_v2_context,
)


SHA = lambda value: value * 64


class P10VisualReviewV2ContextTests(unittest.TestCase):
    def setUp(self):
        self.p10 = {
            "candidate_sha256": SHA("1"),
            "decision_sha256": SHA("2"), "revision": 3,
        }
        self.framing = {
            "candidate_sha256": SHA("3"),
            "decision_sha256": SHA("4"), "revision": 1,
        }
        self.request = P10CaptureJobRequest.from_payload({
            "package_id": SHA("5"), "client_request_id": "browser-run-1",
            "expected_p10_1": self.p10,
            "expected_framing": self.framing,
            "explicit_runtime_license_confirmation": True,
            "explicit_run_confirmation": True,
        })
        self.addresses = {
            "project": "sample-a", "preview": SHA("6"),
            "execution_bundle": SHA("7"), "artifact": SHA("8"),
        }
        self.snapshot = {
            "job_id": self.request.job_id,
            "request": self.request.public_document(),
            "status": "completed", "terminal": True, "retryable": False,
            "addresses": self.addresses,
        }
        self.manager = Mock()
        self.manager.get.return_value = self.snapshot
        self.store = Mock()
        self.preview = SimpleNamespace(
            package_id=SHA("5"), project_id="sample-a",
            clip_id="wave-left-v1", temporary_preview_v2_sha256=SHA("6"),
            capture_framing_candidate_sha256=SHA("3"),
            capture_framing_decision_sha256=SHA("4"),
            capture_framing_revision=1, case_count=43,
            document={"source": {"current_p10_1_head": self.p10}},
        )

    def resolve(self, preview=None):
        with patch(
            "autospine_workbench.p10_visual_review_v2_context."
            "compile_body_sway_preview_v2_for_package",
            return_value=preview or self.preview,
        ) as compiler:
            result = resolve_p10_visual_review_v2_context(
                self.manager, self.store, self.request.job_id,
            )
        return result, compiler

    def test_completed_job_replays_package_and_derives_four_part_address(self):
        context, compiler = self.resolve()
        self.manager.get.assert_called_once_with(self.request.job_id)
        compiler.assert_called_once_with(self.store, SHA("5"))
        self.assertEqual(tuple(self.addresses.values()), (
            context.address.project_id,
            context.address.temporary_preview_v2_sha256,
            context.address.runtime_execution_bundle_sha256,
            context.address.capture_artifact_set_sha256,
        ))
        self.assertNotIn("path", str(context.public_job()).lower())

    def test_incomplete_job_never_compiles_review_evidence(self):
        self.snapshot.update({
            "status": "capturing", "terminal": False,
            "addresses": None,
        })
        with patch(
            "autospine_workbench.p10_visual_review_v2_context."
            "compile_body_sway_preview_v2_for_package",
        ) as compiler, self.assertRaises(P10VisualReviewV2JobIncomplete):
            resolve_p10_visual_review_v2_context(
                self.manager, self.store, self.request.job_id,
            )
        compiler.assert_not_called()

    def test_current_p10_framing_or_preview_drift_fails_closed(self):
        changed = SimpleNamespace(**vars(self.preview))
        changed.document = {"source": {"current_p10_1_head": {
            **self.p10, "revision": 4,
        }}}
        with self.assertRaises(P10VisualReviewV2SourceChanged):
            self.resolve(changed)
        changed = SimpleNamespace(**vars(self.preview))
        changed.capture_framing_revision = 2
        with self.assertRaises(P10VisualReviewV2SourceChanged):
            self.resolve(changed)
        changed = SimpleNamespace(**vars(self.preview))
        changed.temporary_preview_v2_sha256 = SHA("9")
        with self.assertRaises(P10VisualReviewV2SourceChanged):
            self.resolve(changed)

    def test_tampered_job_or_request_identity_is_not_found(self):
        for field, value in (
            ("job_id", SHA("0")),
            ("request", {**self.request.public_document(),
                         "package_id": SHA("0")}),
        ):
            with self.subTest(field=field):
                self.manager.reset_mock()
                self.manager.get.return_value = {**self.snapshot, field: value}
                with self.assertRaises(P10VisualReviewV2JobNotFound):
                    resolve_p10_visual_review_v2_context(
                        self.manager, self.store, self.request.job_id,
                    )


if __name__ == "__main__":
    unittest.main()
