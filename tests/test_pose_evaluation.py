"""Manual-reference pose evaluation tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.pose_evaluation import (  # noqa: E402
    PoseEvaluationError,
    evaluate_pose,
)
from autospine_workbench.pose_observations import (  # noqa: E402
    PoseJointObservation,
    PoseObservationSet,
)

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None


def project_fixture() -> dict:
    return {
        "id": "sample-a",
        "canvas": {"width": 100, "height": 200},
        "resolved": {
            "revision": 3,
            "sha256": "a" * 64,
            "inputs": {"override_sha256": "b" * 64},
            "skeleton": {
                "joints": [
                    {
                        "id": "shoulder.left",
                        "x": 10,
                        "y": 20,
                        "review_state": "manual_adjusted",
                    },
                    {
                        "id": "shoulder.right",
                        "x": 90,
                        "y": 20,
                        "review_state": "manual_adjusted",
                    },
                    {
                        "id": "elbow.left",
                        "x": 20,
                        "y": 50,
                        "review_state": "unreviewed",
                    },
                    {
                        "id": "head",
                        "x": 50,
                        "y": 10,
                        "review_state": "manual_adjusted",
                    },
                ]
            },
        },
    }


def observations(
    joints: dict[str, tuple[float, float]] | None = None,
) -> PoseObservationSet:
    positions = joints or {
        "shoulder.left": (13, 24),
        "shoulder.right": (90, 20),
        "elbow.left": (50, 50),
    }
    mapped = {
        joint_id: PoseJointObservation(x, y, 0.75, "unknown")
        for joint_id, (x, y) in positions.items()
    }
    return PoseObservationSet(
        project_id="sample-a",
        image_sha256="c" * 64,
        canvas_size=(100, 200),
        detector_id="fixture-pose",
        detector_version="1",
        model_revision="fixture-revision",
        config_sha256="d" * 64,
        runtime="unittest",
        detected_count=1,
        selected_index=0,
        selection_method="single",
        joints=mapped,
        document_sha256="e" * 64,
    )


class PoseEvaluationTests(unittest.TestCase):
    def test_only_manual_limb_references_contribute_to_metrics(self) -> None:
        report = evaluate_pose(project_fixture(), observations())
        self.assertEqual(2, report["metrics"]["reference_count"])
        self.assertEqual(2, report["metrics"]["matched_count"])
        self.assertEqual(2.5, report["metrics"]["mean_error_px"])
        self.assertEqual(3.535534, report["metrics"]["rmse_error_px"])
        self.assertEqual(5.0, report["metrics"]["max_error_px"])
        self.assertEqual(
            ["shoulder.left", "shoulder.right"], report["matched_joint_ids"]
        )
        self.assertNotIn("elbow.left", report["joints"])
        self.assertEqual("as_mapped", report["side_swap_diagnostic"]["lower_error_mapping"])
        self.assertIn("NO_PASS_FAIL_THRESHOLDS", report["qa"]["flags"])
        self.assertIn("INCOMPLETE_MANUAL_REFERENCE", report["qa"]["flags"])

    def test_swapped_counterfactual_is_diagnostic_and_never_rewrites_pose(self) -> None:
        pose = observations(
            {"shoulder.left": (90, 20), "shoulder.right": (10, 20)}
        )
        report = evaluate_pose(project_fixture(), pose)
        diagnostic = report["side_swap_diagnostic"]
        self.assertEqual("swapped", diagnostic["lower_error_mapping"])
        self.assertEqual(0.0, diagnostic["swapped_mean_error_px"])
        self.assertGreater(diagnostic["as_mapped_mean_error_px"], 0)
        self.assertIn("SIDE_SWAP_COUNTERFACTUAL_LOWER_ERROR", report["qa"]["flags"])
        self.assertEqual([90.0, 20.0], report["joints"]["shoulder.left"]["predicted_xy"])

    def test_zero_overlap_is_publishable_but_has_null_error_metrics(self) -> None:
        report = evaluate_pose(
            project_fixture(), observations({"wrist.left": (30, 60)})
        )
        self.assertEqual(0, report["metrics"]["matched_count"])
        self.assertEqual(0.0, report["metrics"]["observation_coverage"])
        self.assertIsNone(report["metrics"]["mean_error_px"])
        self.assertEqual("insufficient", report["side_swap_diagnostic"]["lower_error_mapping"])
        self.assertIn("NO_OVERLAPPING_OBSERVATIONS", report["qa"]["flags"])
        self.assertEqual(
            ["shoulder.left", "shoulder.right"],
            report["missing_observation_ids"],
        )

    def test_no_manual_limb_reference_fails(self) -> None:
        project = project_fixture()
        for joint in project["resolved"]["skeleton"]["joints"]:
            joint["review_state"] = "unreviewed"
        with self.assertRaises(PoseEvaluationError):
            evaluate_pose(project, observations())

    def test_resolved_snapshot_identity_changes_run(self) -> None:
        first = evaluate_pose(project_fixture(), observations())
        changed = project_fixture()
        changed["resolved"]["sha256"] = "f" * 64
        second = evaluate_pose(changed, observations())
        self.assertNotEqual(
            first["evaluator"]["run_sha256"], second["evaluator"]["run_sha256"]
        )
        invalid = copy.deepcopy(project_fixture())
        invalid["resolved"].pop("sha256")
        with self.assertRaises(ValueError):
            evaluate_pose(invalid, observations())

    @unittest.skipIf(Draft202012Validator is None, "install the 'test' extra")
    def test_report_validates_against_schema(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "pose-evaluation-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(
            evaluate_pose(project_fixture(), observations())
        )


if __name__ == "__main__":
    unittest.main()
