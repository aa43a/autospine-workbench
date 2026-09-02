"""Regression coverage for sealed P10.4b v2 interval rows."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_amplitude_envelope_v2 import (  # noqa: E402
    compile_body_sway_amplitude_envelope_candidate_v2,
)
from autospine_workbench.body_sway_continuous_interval import (  # noqa: E402
    EXCLUSIONS, SCOPE,
)
from autospine_workbench.body_sway_continuous_proof_v2 import (  # noqa: E402
    BodySwayContinuousProofV2Error,
    compile_body_sway_continuous_preview_proof_v2,
)
from autospine_workbench.body_sway_continuous_proof_validation_v2 import (  # noqa: E402
    BodySwayContinuousProofValidationV2Error,
    require_sealed_body_sway_continuous_preview_proof_v2,
)
from autospine_workbench.body_sway_continuous_proof_analysis import (  # noqa: E402
    _summary,
)
from autospine_workbench.body_sway_continuous_proof_profile_v2 import (  # noqa: E402
    continuous_segment_sha256_v2,
)
from autospine_workbench.body_sway_preview_projection_v2 import (  # noqa: E402
    compile_body_sway_preview_projection_v2,
)
from autospine_workbench.body_sway_review_admission_consumer_v2 import (  # noqa: E402
    CurrentBodySwayReviewAdmissionV2,
)
from autospine_workbench.p10_review_admission_v2_commands import (  # noqa: E402
    _result,
)
from autospine_workbench.p10_safety_analysis_source_v2 import (  # noqa: E402
    P10SafetyAnalysisSourceV2,
)
from tests.p10_review_admission_v2_helpers import (  # noqa: E402
    shared_p10_review_admission_v2_fixture,
)


_TINY_BUDGET = {
    "max_depth": 0,
    "max_boxes_per_segment": 2,
    "max_total_boxes": 2,
}


def _tiny_budget():
    return dict(_TINY_BUDGET)


@contextmanager
def _patched_budgets(*targets):
    with ExitStack() as stack:
        for target in targets:
            stack.enter_context(patch(target, side_effect=_tiny_budget))
        yield


def _compile_tiny_budget_document(on_progress=None):
    fixture = shared_p10_review_admission_v2_fixture()
    command = _result(fixture.inputs, fixture.admission)
    admission = CurrentBodySwayReviewAdmissionV2(
        command.admission_sha256, command,
    )
    source = P10SafetyAnalysisSourceV2(
        fixture.context.package_id,
        SimpleNamespace(result=fixture.preview_result),
        fixture.preview_inputs,
        compile_body_sway_preview_projection_v2(fixture.preview_inputs),
        fixture.mesh_bundle,
    )
    amplitude = compile_body_sway_amplitude_envelope_candidate_v2(
        admission, source,
    )
    targets = (
        "autospine_workbench.body_sway_continuous_proof_profile_v2."
        "continuous_proof_budget_v2",
        "autospine_workbench.body_sway_continuous_proof_v2."
        "continuous_proof_budget_v2",
        "autospine_workbench.body_sway_continuous_proof_sealed_validation_v2."
        "continuous_proof_budget_v2",
    )
    with _patched_budgets(*targets):
        return compile_body_sway_continuous_preview_proof_v2(
            amplitude, source, on_progress=on_progress,
        ).document


class P10SafetyAnalysisV2SealedBudgetRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.progress = []
        cls.document = _compile_tiny_budget_document(
            lambda stage, current, total:
                cls.progress.append((stage, current, total)),
        )

    def test_box_progress_is_bounded_and_reports_first_work(self):
        boxes = [row for row in self.progress
                 if row[0] == "continuous_boxes"]
        self.assertTrue(boxes)
        self.assertEqual(("continuous_boxes", 0, 2), boxes[0])
        self.assertIn(("continuous_boxes", 1, 2), boxes)
        self.assertIn(("continuous_boxes", 2, 2), boxes)
        self.assertTrue(all(0 <= current <= total == 2
                            for _, current, total in boxes))

    def test_validation_reports_the_second_exact_recomputation(self):
        rows = [row for row in self.progress
                if row[0] == "continuous_validation"]
        self.assertTrue(rows)
        self.assertEqual(("continuous_validation", 0, 2), rows[0])
        self.assertIn(("continuous_validation", 1, 2), rows)
        self.assertEqual(("continuous_validation", 2, 2), rows[-1])

    def test_progress_observation_does_not_change_proof_bytes(self):
        self.assertEqual(self.document, _compile_tiny_budget_document())

    def test_progress_observer_fault_cannot_become_interval_evidence(self):
        def faulty(stage, current, _total):
            if stage == "continuous_boxes" and current == 1:
                raise ValueError("observer failed")

        with self.assertRaises(BodySwayContinuousProofV2Error):
            _compile_tiny_budget_document(faulty)

    def test_validation_progress_fault_cannot_publish_a_document(self):
        def faulty(stage, current, _total):
            if stage == "continuous_validation" and current == 1:
                raise RuntimeError("validation observer failed")

        with self.assertRaises(BodySwayContinuousProofV2Error):
            _compile_tiny_budget_document(faulty)

    def test_canonical_list_fields_do_not_reject_evaluated_segments(self):
        evaluated = [
            row for row in self.document["segments"]
            if row["evaluated_box_count"] > 0
        ]
        self.assertGreaterEqual(len(evaluated), 1)
        for row in evaluated:
            self.assertIsInstance(row["reason_codes"], list)
            self.assertIsInstance(row["scope"], list)
            self.assertIsInstance(row["exclusions"], list)
            self.assertEqual(list(SCOPE), row["scope"])
            self.assertEqual(list(EXCLUSIONS), row["exclusions"])

        with _patched_budgets(
            "autospine_workbench.body_sway_continuous_proof_profile_v2."
            "continuous_proof_budget_v2",
            "autospine_workbench."
            "body_sway_continuous_proof_sealed_validation_v2."
            "continuous_proof_budget_v2",
        ):
            require_sealed_body_sway_continuous_preview_proof_v2(
                self.document,
            )

    def test_last_remaining_box_then_global_budget_fallback_is_sealed(self):
        rows = self.document["segments"]
        evaluated = [row for row in rows if row["evaluated_box_count"] > 0]
        fallback = rows[len(evaluated):]

        self.assertEqual(2, len(evaluated))
        self.assertEqual(
            _TINY_BUDGET["max_total_boxes"],
            sum(row["evaluated_box_count"] for row in evaluated),
        )
        self.assertEqual(1, evaluated[-1]["evaluated_box_count"])
        self.assertGreaterEqual(len(fallback), 1)
        self.assertTrue(all(
            row["evaluated_box_count"] == 0
            and row["reason_codes"] == [
                "global_subdivision_box_budget_exhausted"
            ]
            for row in fallback
        ))

        with _patched_budgets(
            "autospine_workbench.body_sway_continuous_proof_profile_v2."
            "continuous_proof_budget_v2",
            "autospine_workbench."
            "body_sway_continuous_proof_sealed_validation_v2."
            "continuous_proof_budget_v2",
        ):
            require_sealed_body_sway_continuous_preview_proof_v2(
                self.document,
            )

    def test_global_budget_fallback_cannot_precede_exhaustion(self):
        forged = deepcopy(self.document)
        first, fallback = forged["segments"][0], forged["segments"][-1]
        replacement = deepcopy(fallback)
        replacement["left_tick"] = first["left_tick"]
        replacement["right_tick"] = first["right_tick"]
        replacement["segment_evidence_sha256"] = (
            continuous_segment_sha256_v2(replacement)
        )
        forged["segments"][0] = replacement
        forged["summary"] = _summary(forged["segments"])

        with _patched_budgets(
            "autospine_workbench.body_sway_continuous_proof_profile_v2."
            "continuous_proof_budget_v2",
            "autospine_workbench."
            "body_sway_continuous_proof_sealed_validation_v2."
            "continuous_proof_budget_v2",
        ), self.assertRaisesRegex(
            BodySwayContinuousProofValidationV2Error,
            "global fallback precedes exhaustion",
        ):
            require_sealed_body_sway_continuous_preview_proof_v2(forged)


if __name__ == "__main__":
    unittest.main()
