"""Candidate semantic validation tests independent of optional jsonschema."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.candidate_validation import (  # noqa: E402
    CandidateValidationError,
    require_valid_candidate_document,
    validate_candidate_document,
)
from autospine_workbench.joint_candidates import AuditBBoxHeuristicProvider  # noqa: E402
from tests.test_joint_candidates import project_fixture  # noqa: E402


def validate(document: dict):
    return validate_candidate_document(
        document,
        joint_ids={"elbow.left", "wrist.left"},
        layer_ids={"layer-arm-left"},
        canvas_width=100,
        canvas_height=200,
    )


class CandidateValidationTests(unittest.TestCase):
    def test_baseline_document_is_semantically_valid(self) -> None:
        document = AuditBBoxHeuristicProvider().analyze(project_fixture())
        self.assertEqual([], validate(document))
        require_valid_candidate_document(
            document,
            joint_ids={"elbow.left", "wrist.left"},
            layer_ids=set(),
            canvas_width=100,
            canvas_height=200,
        )

    def test_duplicate_unknown_layer_and_forbidden_probability_fail(self) -> None:
        document = AuditBBoxHeuristicProvider().analyze(project_fixture())
        elbow = document["joints"]["elbow.left"]["candidates"][0]
        wrist = document["joints"]["wrist.left"]["candidates"][0]
        wrist["candidate_id"] = elbow["candidate_id"]
        elbow["source_layer_ids"] = ["missing-layer"]
        elbow["probability"] = 0.9
        codes = {item.code for item in validate(document)}
        self.assertEqual({"duplicate", "unknown_layer", "forbidden"}, codes)
        with self.assertRaises(CandidateValidationError):
            require_valid_candidate_document(
                document,
                joint_ids={"elbow.left", "wrist.left"},
                layer_ids={"layer-arm-left"},
                canvas_width=100,
                canvas_height=200,
            )

    def test_non_finite_out_of_bounds_and_missing_joint_fail(self) -> None:
        document = AuditBBoxHeuristicProvider().analyze(project_fixture())
        broken = copy.deepcopy(document)
        del broken["joints"]["wrist.left"]
        broken["joints"]["elbow.left"]["candidates"][0]["xy"] = [float("nan"), 999]
        codes = {item.code for item in validate(broken)}
        self.assertIn("missing_joint", codes)
        self.assertIn("coordinate", codes)


if __name__ == "__main__":
    unittest.main()
