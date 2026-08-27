"""Adaptive time/gain coverage tests for P10.5d anchor proximity."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import autospine_workbench.body_sway_dynamic_seam_interval \
    as driver  # noqa: E402
from autospine_workbench.body_sway_dynamic_seam_interval import (  # noqa: E402
    BodySwayDynamicSeamIntervalBudget,
    BodySwayDynamicSeamIntervalDriverError,
    prove_body_sway_dynamic_seam_sampled_linear_segment,
)
from autospine_workbench.body_sway_dynamic_seam_evidence_profile import (  # noqa: E402
    MAX_BOXES_PER_SEGMENT,
    MAX_DEPTH,
)
from autospine_workbench.body_sway_interval_pose import (  # noqa: E402
    prepare_body_sway_interval_pose,
)
from tests.body_sway_dynamic_seam_interval_helpers import (  # noqa: E402
    dynamic_seam_driver_fixture,
    full_sample,
    interval_assessment,
)


class BodySwayDynamicSeamIntervalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rig, cls.context, cls.locators = dynamic_seam_driver_fixture()
        cls.left = full_sample(cls.context, tick=0)
        cls.right = full_sample(cls.context, tick=10)

    def prove(self, *, budget=None):
        return prove_body_sway_dynamic_seam_sampled_linear_segment(
            self.locators, self.context, self.left, self.right,
            budget=budget,
        )

    def test_static_real_geometry_certifies_every_pair_in_one_box(self):
        proof = self.prove()
        self.assertEqual(
            "continuous_anchor_proximity_certified", proof.status
        )
        self.assertEqual((), proof.reason_codes)
        self.assertEqual((1, 1, 0, 0), (
            proof.evaluated_box_count,
            proof.certified_terminal_box_count,
            proof.indeterminate_terminal_box_count,
            proof.maximum_depth_reached,
        ))
        self.assertEqual(6, proof.relationship_count)
        self.assertEqual(24, proof.pair_count)
        self.assertLessEqual(
            proof.max_squared_distance_upper_px2,
            proof.threshold_squared_px2,
        )

    def test_subdivision_alternates_time_gain_and_aggregates_terminals(self):
        uncertain = interval_assessment(
            self.locators, 5.0, status="indeterminate",
            reasons=("anchor_proximity_unproven",),
        )
        terminal = [
            interval_assessment(self.locators, value, vary=True)
            for value in (1.0, 2.0, 3.0)
        ]
        sequence = [uncertain, uncertain, *terminal[:2], terminal[2]]
        with patch.object(
            driver, "assess_body_sway_dynamic_seam_interval_box",
            side_effect=sequence,
        ), patch.object(
            driver, "prepare_body_sway_interval_pose",
            wraps=prepare_body_sway_interval_pose,
        ) as pose_calls:
            proof = self.prove()
        self.assertEqual(
            "continuous_anchor_proximity_certified", proof.status
        )
        self.assertEqual((5, 3, 0, 2), (
            proof.evaluated_box_count,
            proof.certified_terminal_box_count,
            proof.indeterminate_terminal_box_count,
            proof.maximum_depth_reached,
        ))
        calls = [row.kwargs for row in pose_calls.call_args_list]
        self.assertEqual((0.0, 0.5), (
            calls[1]["time_fraction"].lower,
            calls[1]["time_fraction"].upper,
        ))
        self.assertEqual((0.0, 0.5), (
            calls[2]["gain"].lower, calls[2]["gain"].upper,
        ))
        self.assertEqual((0.5, 1.0), (
            calls[3]["gain"].lower, calls[3]["gain"].upper,
        ))
        self.assertAlmostEqual(3.53, proof.max_squared_distance_upper_px2)
        self.assertAlmostEqual(
            3.53,
            proof.relationships[-1].pairs[-1]
                .max_squared_distance_upper_px2,
        )

    def test_over_threshold_is_indeterminate_never_rejected_or_safe(self):
        outside = interval_assessment(
            self.locators, math.nextafter(4.0, math.inf),
            status="indeterminate",
            reasons=("anchor_proximity_unproven",),
        )
        with patch.object(
            driver, "assess_body_sway_dynamic_seam_interval_box",
            return_value=outside,
        ):
            proof = self.prove(budget=BodySwayDynamicSeamIntervalBudget(
                max_depth=0, max_boxes=1
            ))
        self.assertEqual("indeterminate", proof.status)
        self.assertIn("anchor_proximity_unproven", proof.reason_codes)
        self.assertIn("subdivision_depth_exhausted", proof.reason_codes)
        self.assertNotIn("safe", proof.status)
        self.assertNotIn("rejected", proof.status)

    def test_depth_box_and_resolution_limits_are_explicit(self):
        uncertain = interval_assessment(
            self.locators, 5.0, status="indeterminate",
            reasons=("anchor_proximity_unproven",),
        )
        cases = (
            (BodySwayDynamicSeamIntervalBudget(0, 1), False,
             "subdivision_depth_exhausted"),
            (BodySwayDynamicSeamIntervalBudget(1, 1), False,
             "subdivision_box_budget_exhausted"),
            (BodySwayDynamicSeamIntervalBudget(1, 3), True,
             "parameter_resolution_exhausted"),
        )
        for budget, force_resolution, reason in cases:
            context = patch.object(driver, "_split", return_value=None) \
                if force_resolution else _null_context()
            with self.subTest(reason=reason), patch.object(
                driver, "assess_body_sway_dynamic_seam_interval_box",
                return_value=uncertain,
            ), context:
                proof = self.prove(budget=budget)
            self.assertIn(reason, proof.reason_codes)
        for values in ((MAX_DEPTH + 1, 1), (0, MAX_BOXES_PER_SEGMENT + 1)):
            with self.assertRaises(BodySwayDynamicSeamIntervalDriverError):
                BodySwayDynamicSeamIntervalBudget(*values)

    def test_nonfinite_upper_is_json_none_and_remains_indeterminate(self):
        unbounded = interval_assessment(
            self.locators, math.inf, status="indeterminate",
            reasons=(
                "anchor_proximity_unproven",
                "non_finite_interval_bound",
            ),
        )
        with patch.object(
            driver, "assess_body_sway_dynamic_seam_interval_box",
            return_value=unbounded,
        ):
            proof = self.prove(budget=BodySwayDynamicSeamIntervalBudget(0, 1))
        self.assertIsNone(proof.max_squared_distance_upper_px2)
        self.assertIsNone(
            proof.relationships[0].pairs[0]
                .max_squared_distance_upper_px2
        )
        self.assertIn("non_finite_interval_bound", proof.reason_codes)

    def test_result_is_frozen_serializable_and_explicitly_non_visual(self):
        proof = self.prove()
        document = proof.to_dict()
        self.assertIn("engineering-proxy", proof.metric_interpretation)
        self.assertIn("not-visual", proof.metric_interpretation)
        self.assertFalse(document["visual_seam_quality_claimed"])
        self.assertIn("raster-or-visual-seam-calibration", proof.exclusions)
        self.assertIn("all-six-static-seam-relationships", proof.scope)
        self.assertIn("adaptive-interval", proof.proof_method)
        self.assertIn("binary64", proof.rounding_profile)
        self.assertIn("supplied-endpoint-segment", proof.time_model)
        self.assertIn(
            "upstream-preview-key-adjacency-binding", proof.exclusions
        )
        self.assertNotIn(
            "all-adjacent-preview-sample-tick-pairs", proof.scope
        )
        self.assertEqual(document, deepcopy(document))
        with self.assertRaises(FrozenInstanceError):
            proof.status = "forged"  # type: ignore[misc]

    def test_production_files_stay_within_p10_budget(self):
        for name in (
            "body_sway_dynamic_seam_interval.py",
            "body_sway_dynamic_seam_interval_results.py",
        ):
            lines = (SRC / "autospine_workbench" / name).read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertLessEqual(len(lines), 300, name)


class _null_context:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


if __name__ == "__main__":
    unittest.main()
