"""Missing ground truth stays unknown and method deltas use paired references."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_pose_observations import observation_fixture
from tests.test_benchmark_joint_comparison import baseline as make_baseline
from autospine_workbench.pose_observations import load_pose_observations
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.asset.joints.optimizer import JOINTS
from autospine_workbench.benchmark.joint_draft import build_joint_draft
from autospine_workbench.benchmark.joint_reference import build_joint_reference
from autospine_workbench.benchmark.pose_accuracy import build_pose_accuracy, validate_pose_accuracy


class PoseAccuracyTests(unittest.TestCase):
    def setUp(self):
        self.candidate = {"schema": "autospine.benchmark-semantic-candidates/v1", "authority": "none",
                          "canvas": [100, 200], "character_id": "sample-a", "composite_sha256": "a"*64}
        self.baseline = make_baseline(self.candidate)
        self.document = observation_fixture()
        self.document["joints"] = {joint: {"xy": [23, 24], "detector_score": .7, "visibility": "unknown"} for joint in JOINTS}
        self.document["joints"]["shoulder.right"]["xy"] = [20, 30]
        self.pose = self.load_pose(self.document)
        self.optimized = {"schema": "autospine.joint-optimization/v1", "authority": "none", "diagnostic_only": True,
                          "candidate_sha256": canonical_sha256(self.candidate), "pose_sha256": self.pose.document_sha256,
                          "status": "candidate_requires_review", "joints": [{"joint_id": joint, "position": [20, 20]} for joint in JOINTS]}

    def load_pose(self, document):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pose.json"; path.write_text(json.dumps(document), encoding="utf-8")
            return load_pose_observations(path, expected_project_id="sample-a", expected_image_sha256="a"*64,
                                          expected_canvas_size=(100, 200))

    def reference(self):
        draft = build_joint_draft(self.candidate)
        for row in draft["records"]:
            if row["joint_id"].startswith("shoulder."): row.update(status="observed", position=[20, 20])
            if row["joint_id"] == "ankle.left": row.update(status="unobservable", notes="occluded")
        request = {"schema": "autospine.benchmark-joint-reference-request/v1", "authority": "none",
                   "candidate_sha256": canonical_sha256(self.candidate), "draft_sha256": canonical_sha256(draft),
                   "reviewer": "test only", "decision": "accept", "independent_annotation": True}
        return build_joint_reference(self.candidate, draft, request)

    def build(self, reference=None, **kwargs):
        return build_pose_accuracy(self.candidate, self.baseline, self.pose, self.optimized, reference,
                                   character_height=kwargs.get("character_height", 150))

    def test_missing_reference_never_becomes_zero_error(self):
        result = self.build()
        self.assertFalse(result["accuracy_evaluated"])
        self.assertEqual(result["summary"]["reference_counts"], {"observed": 0, "unmarked": 12, "unobservable": 0})
        for method in ("baseline", "pose", "optimized"):
            self.assertEqual(result["summary"][method]["coverage"], 1)
            self.assertEqual(result["summary"][method]["compared"], 0)
            self.assertIsNone(result["summary"][method]["median_distance_px"])
            self.assertTrue(all(row["methods"][method]["distance_px"] is None for row in result["records"]))

    def test_formal_observations_compare_three_methods_and_core(self):
        result = self.build(self.reference())
        self.assertTrue(result["accuracy_evaluated"])
        self.assertEqual(result["summary"]["baseline"]["median_distance_px"], 0)
        self.assertEqual(result["summary"]["pose"]["median_distance_px"], 7.5)
        self.assertEqual(result["summary"]["pose"]["core"]["compared"], 2)
        self.assertEqual(result["summary"]["pose"]["median_distance_height_ratio"], .05)
        self.assertEqual(result["summary"]["comparisons"]["baseline_vs_pose"]["median_delta_px"], 7.5)
        self.assertEqual(result["summary"]["comparisons"]["pose_vs_optimized"]["median_delta_px"], -7.5)
        ankle = next(row for row in result["records"] if row["joint_id"] == "ankle.left")
        self.assertIsNone(ankle["methods"]["pose"]["distance_px"])

    def test_partial_pose_and_blocked_optimization_use_only_common_reference(self):
        del self.document["joints"]["shoulder.right"]
        self.pose = self.load_pose(self.document)
        self.optimized.update(status="blocked", joints=[], pose_sha256=self.pose.document_sha256)
        result = self.build(self.reference())
        self.assertEqual(result["summary"]["pose"]["coverage"], 11/12)
        self.assertEqual(result["summary"]["pose"]["reference_coverage"], .5)
        paired = result["summary"]["comparisons"]["baseline_vs_pose"]
        self.assertEqual(paired["compared"], 1); self.assertEqual(paired["median_delta_px"], 5)
        self.assertEqual(result["summary"]["optimized"]["coverage"], 0)
        self.assertIsNone(result["summary"]["comparisons"]["pose_vs_optimized"]["median_delta_px"])

    def test_height_source_identity_and_nonfinite_inputs_fail_closed(self):
        for height in (True, 0, 201, 10**1000, float("nan")):
            with self.assertRaises(ValueError): self.build(character_height=height)
        original = self.pose
        self.pose = replace(original, image_sha256="b"*64)
        with self.assertRaises(ValueError): self.build()
        self.pose = original
        self.optimized["joints"][0]["position"] = [10**1000, 0]
        with self.assertRaises(ValueError): self.build()

    def test_reference_source_draft_and_report_tampering_fail(self):
        reference = self.reference(); result = self.build(reference)
        self.assertEqual(validate_pose_accuracy(self.candidate, self.baseline, self.pose, self.optimized,
                                               reference, result, character_height=150), result)
        changed = deepcopy(reference); changed["records"][5]["position"] = [50, 50]
        with self.assertRaises(ValueError): self.build(changed)
        result["summary"]["pose"]["median_distance_px"] = 0
        with self.assertRaises(ValueError):
            validate_pose_accuracy(self.candidate, self.baseline, self.pose, self.optimized,
                                   reference, result, character_height=150)


if __name__ == "__main__": unittest.main()
