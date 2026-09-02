"""Parent-owned authority recheck tests for P10.4b v2 completion."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import autospine_workbench.p10_safety_analysis_parent_validation_v2 as subject  # noqa: E402
from autospine_workbench.body_sway_review_admission_consumer_v2 import (  # noqa: E402
    BodySwayReviewAdmissionV2ConsumerError,
)
from autospine_workbench.p10_safety_analysis_v2_commands import (  # noqa: E402
    P10SafetyAnalysisV2CommandError,
)
from tests.p10_safety_analysis_job_v2_test_helpers import SHA  # noqa: E402


class P10SafetyAnalysisParentValidationV2Tests(unittest.TestCase):
    def setUp(self):
        self.admission = {"format": "exact-admission"}
        self.amplitude = {"source": {
            "review_admission_v2": self.admission,
        }}
        self.continuous = {"format": "continuous"}
        self.worker = SimpleNamespace(
            result={"admission_sha256": SHA["1"]},
            amplitude_document=self.amplitude,
            continuous_document=self.continuous,
        )
        self.store = Mock()
        self.store.verify_staged_result.return_value = (
            self.amplitude, self.continuous,
        )

    def test_parent_rechecks_current_admission_after_exact_readback(self):
        current = SimpleNamespace(
            admission_sha256=SHA["1"], document=self.admission,
        )
        with patch.object(
            subject, "require_current_body_sway_review_admission_v2",
            return_value=current,
        ) as verify:
            result = subject.verify_parent_p10_safety_analysis_result_v2(
                Mock(), Mock(), self.store, SHA["8"], self.worker,
            )
        self.assertEqual((self.amplitude, self.continuous), result)
        verify.assert_called_once()

    def test_changed_current_head_is_terminal(self):
        with patch.object(
            subject, "require_current_body_sway_review_admission_v2",
            side_effect=BodySwayReviewAdmissionV2ConsumerError("changed"),
        ), self.assertRaises(P10SafetyAnalysisV2CommandError) as raised:
            subject.verify_parent_p10_safety_analysis_result_v2(
                Mock(), Mock(), self.store, SHA["8"], self.worker,
            )
        self.assertEqual("source_changed", raised.exception.failure_code)
        self.assertTrue(raised.exception.terminal)

    def test_unavailable_current_source_is_retryable(self):
        with patch.object(
            subject, "require_current_body_sway_review_admission_v2",
            side_effect=OSError("unavailable"),
        ), self.assertRaises(P10SafetyAnalysisV2CommandError) as raised:
            subject.verify_parent_p10_safety_analysis_result_v2(
                Mock(), Mock(), self.store, SHA["8"], self.worker,
            )
        self.assertEqual("source_unavailable", raised.exception.failure_code)
        self.assertFalse(raised.exception.terminal)

    def test_staged_readback_failure_is_terminal(self):
        self.store.verify_staged_result.side_effect = \
            subject.P10SafetyAnalysisJobStoreV2Error("invalid")
        with self.assertRaises(P10SafetyAnalysisV2CommandError) as raised:
            subject.verify_parent_p10_safety_analysis_result_v2(
                Mock(), Mock(), self.store, SHA["8"], self.worker,
            )
        self.assertEqual(
            "analysis_validation_failed", raised.exception.failure_code,
        )
        self.assertTrue(raised.exception.terminal)


if __name__ == "__main__":
    unittest.main()
