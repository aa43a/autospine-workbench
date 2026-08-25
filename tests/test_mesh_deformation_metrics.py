"""Deterministic indexed-mesh deformation metric tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_deformation_metrics import (  # noqa: E402
    DeformationMetricsError,
    measure_deformation,
)


SETUP = ((0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0))
TRIANGLES = ((0, 1, 2), (0, 2, 3))


def measure(posed=SETUP, triangles=TRIANGLES, **thresholds):
    return measure_deformation(SETUP, posed, triangles, **thresholds)


class PassingDeformationTests(unittest.TestCase):
    def test_identity_has_exact_pinned_metrics_and_zero_crack_gap(self) -> None:
        result = measure()

        self.assertEqual("passed", result.status)
        self.assertEqual((), result.reasons)
        self.assertEqual(4, result.metrics.vertex_count)
        self.assertEqual(2, result.metrics.triangle_count)
        self.assertEqual(0, result.metrics.non_finite_count)
        self.assertEqual(0, result.metrics.flipped_count)
        self.assertEqual(0, result.metrics.degenerate_count)
        self.assertEqual(1.0, result.metrics.min_signed_area_ratio)
        self.assertEqual(1.0, result.metrics.max_signed_area_ratio)
        self.assertEqual(1.0, result.metrics.max_edge_stretch_ratio)
        self.assertEqual(0.0, result.metrics.interior_crack_gap_px)

    def test_rigid_rotation_passes_without_float_boundary_noise(self) -> None:
        angle = math.radians(37.0)
        cosine, sine = math.cos(angle), math.sin(angle)
        posed = tuple(
            (cosine * x - sine * y + 11.0, sine * x + cosine * y - 7.0)
            for x, y in SETUP
        )

        result = measure(posed)

        self.assertEqual("passed", result.status)
        self.assertAlmostEqual(1.0, result.metrics.min_signed_area_ratio, places=12)
        self.assertAlmostEqual(1.0, result.metrics.max_signed_area_ratio, places=12)
        self.assertAlmostEqual(1.0, result.metrics.max_edge_stretch_ratio, places=12)

    def test_result_and_nested_metrics_are_frozen(self) -> None:
        result = measure()
        with self.assertRaises(FrozenInstanceError):
            result.status = "rejected"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            result.metrics.flipped_count = 4  # type: ignore[misc]


class RejectedDeformationTests(unittest.TestCase):
    def test_mirror_flips_every_triangle(self) -> None:
        result = measure(tuple((-x, y) for x, y in SETUP))

        self.assertEqual("rejected", result.status)
        self.assertEqual(2, result.metrics.flipped_count)
        self.assertEqual(-1.0, result.metrics.min_signed_area_ratio)
        self.assertIn("flipped_triangles", result.reasons)
        self.assertIn("minimum_area_ratio", result.reasons)

    def test_single_triangle_flip_is_counted(self) -> None:
        posed = (*SETUP[:2], (1.0, -1.0), SETUP[3])
        result = measure(posed)

        self.assertEqual(1, result.metrics.flipped_count)
        self.assertEqual("rejected", result.status)
        self.assertIn("flipped_triangles", result.reasons)

    def test_collapse_is_both_flipped_and_degenerate(self) -> None:
        result = measure(((0, 0), (4, 0), (4, 0), (0, 0)))

        self.assertEqual(2, result.metrics.flipped_count)
        self.assertEqual(2, result.metrics.degenerate_count)
        self.assertEqual(0.0, result.metrics.min_signed_area_ratio)
        self.assertEqual(
            (
                "degenerate_triangles",
                "flipped_triangles",
                "minimum_area_ratio",
            ),
            result.reasons,
        )

    def test_excessive_edge_stretch_is_rejected(self) -> None:
        posed = tuple((4.0 * x, y) for x, y in SETUP)
        result = measure(posed)

        self.assertEqual(4.0, result.metrics.max_signed_area_ratio)
        self.assertEqual(4.0, result.metrics.max_edge_stretch_ratio)
        self.assertEqual(("maximum_edge_stretch",), result.reasons)

    def test_threshold_boundaries_are_strict_and_conservative(self) -> None:
        self.assertEqual(
            ("minimum_area_ratio",),
            measure(min_area_ratio=1.0).reasons,
        )
        self.assertEqual(
            ("maximum_area_ratio",),
            measure(max_area_ratio=1.0).reasons,
        )
        self.assertEqual(
            ("maximum_edge_stretch",),
            measure(max_edge_stretch=1.0).reasons,
        )

    def test_non_finite_input_returns_rejected_none_metrics_not_nan(self) -> None:
        posed = (*SETUP[:2], (math.nan, math.inf), SETUP[3])
        result = measure(posed)

        self.assertEqual("rejected", result.status)
        self.assertEqual(("non_finite",), result.reasons)
        self.assertEqual(2, result.metrics.non_finite_count)
        self.assertIsNone(result.metrics.min_signed_area_ratio)
        self.assertIsNone(result.metrics.max_signed_area_ratio)
        self.assertIsNone(result.metrics.max_edge_stretch_ratio)
        for value in (
            result.metrics.interior_crack_gap_px,
            result.metrics.flipped_count,
            result.metrics.degenerate_count,
        ):
            self.assertFalse(isinstance(value, float) and math.isnan(value))


class DeformationContractTests(unittest.TestCase):
    def test_cardinality_coordinate_shape_and_thresholds_are_validated(self) -> None:
        cases = (
            ((SETUP[:-1], SETUP, TRIANGLES, {}), "cardinality"),
            ((SETUP, (*SETUP[:3], (1,)), TRIANGLES, {}), "two coordinates"),
            ((SETUP, SETUP, TRIANGLES, {"min_area_ratio": -1}), "0 <= minimum"),
            ((SETUP, SETUP, TRIANGLES, {"max_area_ratio": math.inf}), "finite"),
            ((SETUP, SETUP, TRIANGLES, {"max_edge_stretch": 0}), "positive"),
        )
        for (setup, posed, triangles, thresholds), message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                DeformationMetricsError, message
            ):
                measure_deformation(setup, posed, triangles, **thresholds)

    def test_triangle_indices_winding_and_setup_area_are_validated(self) -> None:
        cases = (
            (((0, 1),), "three indices"),
            (((0, 1, True),), "integers"),
            (((0, 0, 1),), "distinct"),
            (((0, 1, 8),), "outside vertex"),
            (((0, 2, 1),), "positive area"),
            (((0, 1, 1),), "distinct"),
        )
        for triangles, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                DeformationMetricsError, message
            ):
                measure(triangles=triangles)

        collinear = ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0))
        with self.assertRaisesRegex(DeformationMetricsError, "positive area"):
            measure_deformation(collinear, collinear, ((0, 1, 2),))

    def test_duplicate_and_non_manifold_topology_fail_closed(self) -> None:
        with self.assertRaisesRegex(DeformationMetricsError, "duplicate"):
            measure(triangles=((0, 1, 2), (1, 2, 0)))

        vertices = ((0, 0), (4, 0), (2, 2), (2, 3), (2, 4))
        with self.assertRaisesRegex(DeformationMetricsError, "more than two"):
            measure_deformation(
                vertices,
                vertices,
                ((0, 1, 2), (0, 1, 3), (0, 1, 4)),
            )

    def test_reasons_and_metrics_are_deterministic(self) -> None:
        posed = ((0, 0), (12, 0), (0, -3), (0, 0))
        first = measure(posed)
        second = measure(posed)

        self.assertEqual(first, second)
        self.assertEqual(tuple(sorted(first.reasons)), first.reasons)
        numeric_values = (
            first.metrics.min_signed_area_ratio,
            first.metrics.max_signed_area_ratio,
            first.metrics.max_edge_stretch_ratio,
            first.metrics.interior_crack_gap_px,
        )
        self.assertTrue(
            all(value is None or math.isfinite(value) for value in numeric_values)
        )


if __name__ == "__main__":
    unittest.main()
