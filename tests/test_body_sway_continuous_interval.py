"""Conservative sampled-linear interval proof tests for P10.4b2."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
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

from autospine_workbench.body_sway_continuous_interval import (  # noqa: E402
    BodySwayContinuousIntervalError,
    BodySwayIntervalProofBudget,
    prove_body_sway_sampled_linear_segment,
)
from autospine_workbench.body_sway_interval_arithmetic import (  # noqa: E402
    OutwardInterval,
    cosine_interval,
    sine_interval,
)
from autospine_workbench.mesh_deformation_metrics import (  # noqa: E402
    SETUP_AREA_EPSILON,
)
from autospine_workbench.body_sway_probe_geometry_context import (  # noqa: E402
    prepare_body_sway_geometry_context,
)
from tests.body_sway_probe_geometry_helpers import (  # noqa: E402
    exact_rig_and_target,
    sample,
)


class BodySwayIntervalArithmeticTests(unittest.TestCase):
    def test_arithmetic_and_trigonometry_are_outward(self):
        left = OutwardInterval(-2.0, -1.0)
        right = OutwardInterval(3.0, 4.0)
        product = left * right
        self.assertLessEqual(product.lower, -8.0)
        self.assertGreaterEqual(product.upper, -3.0)

        sine = sine_interval(OutwardInterval(0.0, math.pi))
        self.assertLessEqual(sine.lower, 0.0)
        self.assertEqual(1.0, sine.upper)
        cosine = cosine_interval(OutwardInterval(0.0, 2.0 * math.pi))
        self.assertEqual((-1.0, 1.0), (cosine.lower, cosine.upper))

    def test_interval_bisection_covers_closed_parent(self):
        parent = OutwardInterval(0.0, 1.0)
        left, right = parent.bisect()
        self.assertEqual(parent.lower, left.lower)
        self.assertEqual(parent.upper, right.upper)
        self.assertEqual(left.upper, right.lower)


class BodySwayContinuousIntervalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rig, target = exact_rig_and_target()
        cls.context = prepare_body_sway_geometry_context(rig, target)

    def test_static_segment_is_certified_with_mesh_bounds(self):
        proof = prove_body_sway_sampled_linear_segment(
            self.context, sample(tick=0), sample(tick=50_000)
        )

        self.assertEqual("continuous_structural_certified", proof.status)
        self.assertEqual((), proof.reason_codes)
        self.assertEqual(1, proof.evaluated_box_count)
        self.assertGreater(proof.bounds.canvas_margin_lower_px, 0.0)
        self.assertGreater(
            proof.bounds.min_signed_area_ratio_lower, 0.02
        )
        self.assertLess(
            proof.bounds.max_signed_area_ratio_upper, 20.0
        )
        self.assertLess(
            proof.bounds.max_edge_stretch_squared_ratio_upper, 9.0
        )
        self.assertIn("runtime_equivalence", proof.exclusions)
        self.assertIn("inter_attachment_seams", proof.exclusions)
        self.assertIn(
            "upstream_preview_key_adjacency_binding", proof.exclusions
        )
        self.assertNotIn("release_authority", proof.scope)
        self.assertIn("rational-trig", proof.rounding_profile)
        self.assertEqual(
            "q9-per-layer-plus-q4096-half-step-v1",
            proof.numeric_enclosure_profile,
        )

    def test_coupled_four_bone_gain_can_certify_after_subdivision(self):
        left = sample(overlay={
            "pelvis-spine": -10.0, "spine-chest": -5.0,
            "chest-neck": 3.0, "neck-head": 2.0,
        }, tick=10)
        right = sample(overlay={
            "pelvis-spine": 10.0, "spine-chest": 5.0,
            "chest-neck": -3.0, "neck-head": -2.0,
        }, tick=20)

        proof = prove_body_sway_sampled_linear_segment(
            self.context, left, right
        )

        self.assertEqual("continuous_structural_certified", proof.status)
        self.assertGreater(proof.evaluated_box_count, 1)
        self.assertEqual(
            "coupled-four-bone-lambda-in-closed-unit-interval",
            proof.gain_model,
        )
        self.assertEqual(
            "adaptive-interval-box-subdivision-no-point-sampling",
            proof.proof_method,
        )

    def test_unproved_canvas_box_is_indeterminate_not_safe_or_rejected(self):
        proof = prove_body_sway_sampled_linear_segment(
            self.context,
            sample(translation=(0.0, 0.0), tick=0),
            sample(translation=(500.0, 0.0), tick=50_000),
            budget=BodySwayIntervalProofBudget(max_depth=0, max_boxes=1),
        )

        self.assertEqual("indeterminate", proof.status)
        self.assertIn("canvas_containment_unproven", proof.reason_codes)
        self.assertIn("subdivision_depth_exhausted", proof.reason_codes)
        self.assertEqual(1, proof.indeterminate_terminal_box_count)
        self.assertNotIn("rejected", proof.status)

    def test_effort_limit_never_converts_uncertainty_into_a_pass(self):
        rig, target = exact_rig_and_target(failing_mesh=True)
        context = prepare_body_sway_geometry_context(rig, target)
        left = sample(base={"calf.left": 0.0}, tick=0)
        right = sample(base={"calf.left": 90.0}, tick=50_000)

        proof = prove_body_sway_sampled_linear_segment(
            context, left, right,
            budget=BodySwayIntervalProofBudget(max_depth=0, max_boxes=1),
        )

        self.assertEqual("indeterminate", proof.status)
        self.assertTrue(set(proof.reason_codes) & {
            "minimum_area_ratio_unproven",
            "maximum_edge_stretch_unproven",
        })

    def test_absolute_degenerate_area_threshold_is_an_obligation(self):
        tiny = OutwardInterval(
            SETUP_AREA_EPSILON * 0.5,
            SETUP_AREA_EPSILON * 2.0,
        )
        with patch(
            "autospine_workbench.body_sway_continuous_interval_geometry."
            "_signed_area", return_value=tiny,
        ):
            proof = prove_body_sway_sampled_linear_segment(
                self.context, sample(tick=0), sample(tick=1),
                budget=BodySwayIntervalProofBudget(max_depth=0, max_boxes=1),
            )
        self.assertEqual("indeterminate", proof.status)
        self.assertIn(
            "absolute_triangle_area_unproven", proof.reason_codes
        )
        self.assertIn("platform_libm_equivalence", proof.exclusions)

    def test_endpoints_must_be_canonical_increasing_and_inventory_stable(self):
        left, right = sample(tick=5), sample(tick=5)
        with self.assertRaises(BodySwayContinuousIntervalError):
            prove_body_sway_sampled_linear_segment(self.context, left, right)

        malformed = replace(
            sample(tick=6), overlay_rotation_deg=(
                ("pelvis-spine", 0.0),
                ("spine-chest", 0.0),
                ("chest-neck", 0.0),
            ),
        )
        with self.assertRaises(BodySwayContinuousIntervalError):
            prove_body_sway_sampled_linear_segment(
                self.context, sample(tick=5), malformed
            )

    def test_result_is_frozen_and_serializes_only_bounded_claims(self):
        proof = prove_body_sway_sampled_linear_segment(
            self.context, sample(tick=0), sample(tick=1)
        )
        document = proof.to_dict()
        self.assertNotIn("runtime_safe", document)
        self.assertNotIn("visual_safe", document)
        self.assertNotIn("seam_safe", document)
        with self.assertRaises(FrozenInstanceError):
            proof.status = "forged"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
