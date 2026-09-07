"""Unreviewed distances distinguish absent references from measured zero."""
from copy import deepcopy
import math
import unittest

from tests.test_benchmark_joint_draft import candidate
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.benchmark.joint_draft import JOINTS, build_joint_draft
from autospine_workbench.benchmark.joint_comparison import build_joint_comparison, validate_joint_comparison


def baseline(value):
    return {"schema": "autospine.benchmark-joint-baseline/v1", "authority": "none",
            "candidate_sha256": canonical_sha256(value), "records": [
                {"joint_id": joint, "position": [20, 20], "method": "audit_bbox_heuristic",
                 "score_kind": "heuristic", "heuristic_score": 0.2,
                 "source": "fallback", "reason_codes": ["baseline_requires_review"]} for joint in JOINTS]}


class JointComparisonTests(unittest.TestCase):
    def setUp(self):
        self.value = candidate(); self.baseline = baseline(self.value)
        self.draft = build_joint_draft(self.value)

    def build(self, **kwargs):
        return build_joint_comparison(self.value, self.baseline, self.draft, **kwargs)

    def test_absent_reference_has_null_distances_and_no_accuracy_claim(self):
        result = self.build()
        self.assertEqual(result["summary"]["unmarked"], 17)
        self.assertEqual(result["summary"]["compared"], 0)
        self.assertIsNone(result["summary"]["median_distance_px"])
        self.assertIsNone(result["summary"]["core"]["median_distance_height_ratio"])
        self.assertTrue(result["diagnostic_only"])
        self.assertEqual(result["reference_kind"], "unreviewed_joint_draft")
        self.assertNotIn("accuracy", result)
        self.assertTrue(all(row["distance_px"] is None for row in result["records"]))

    def test_observed_unobservable_core_and_normalized_distances(self):
        by_id = {row["joint_id"]: row for row in self.draft["records"]}
        by_id["root"].update(status="observed", position=[20, 20])
        by_id["shoulder.left"].update(status="observed", position=[23, 24])
        by_id["ankle.right"].update(status="observed", position=[26, 28])
        by_id["hip.right"].update(status="unobservable", notes="Occluded")
        result = self.build(character_height=80)
        self.assertEqual(result["summary"]["observed"], 3)
        self.assertEqual(result["summary"]["unmarked"], 13)
        self.assertEqual(result["summary"]["unobservable"], 1)
        self.assertEqual(result["summary"]["median_distance_px"], 5)
        self.assertEqual(result["summary"]["core"]["median_distance_px"], 7.5)
        self.assertEqual(result["summary"]["core"]["median_distance_height_ratio"], 7.5 / 80)
        self.assertEqual(result["records"][0]["distance_px"], 0)
        self.assertIsNone(self.build()["summary"]["median_distance_height_ratio"])

    def test_height_rejects_invalid_values(self):
        for height in (True, 0, -1, 101, 10**1000, math.inf, math.nan, "80", 1e-300):
            with self.subTest(height=height), self.assertRaisesRegex(ValueError, "height_invalid"):
                self.build(character_height=height)

    def test_baseline_identity_coordinates_ids_and_scores_fail_closed(self):
        mutations = [lambda b: b.update(candidate_sha256="0"*64),
                     lambda b: b.update(authority="human"), lambda b: b["records"].reverse(),
                     lambda b: b["records"][0].update(joint_id="unknown"),
                     lambda b: b["records"][0].update(position=[10**1000, 0]),
                     lambda b: b["records"][0].update(position=[math.nan, 0]),
                     lambda b: b["records"][0].update(position=[True, 0]),
                     lambda b: b["records"][0].update(heuristic_score=True),
                     lambda b: b["records"][0].update(source={"untrusted": True}),
                     lambda b: b["records"][0].update(reason_codes="baseline_requires_review"),
                     lambda b: b["records"][0].update(heuristic_score=math.inf)]
        original = deepcopy(self.baseline)
        for mutate in mutations:
            self.baseline = deepcopy(original); mutate(self.baseline)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): self.build()

    def test_exact_replay_and_input_immutability(self):
        original = deepcopy((self.value, self.baseline, self.draft))
        result = self.build(character_height=80)
        self.assertEqual(validate_joint_comparison(self.value, self.baseline, self.draft, result,
                                                  character_height=80), result)
        self.assertEqual(original, (self.value, self.baseline, self.draft))
        for field in result:
            changed = deepcopy(result); changed[field] = "tampered"
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_joint_comparison(self.value, self.baseline, self.draft, changed, character_height=80)
        with self.assertRaises(ValueError):
            validate_joint_comparison(self.value, self.baseline, self.draft, result, character_height=70)


if __name__ == "__main__":
    unittest.main()
