"""Tests for bounded common-alpha seam anchor sampling."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from autospine_workbench.seam_anchor_sampling import (
    SAMPLING_PROFILE,
    SeamAnchorSamplingError,
    materialize_sampled_locator_pairs,
    sample_common_alpha_pairs,
    validate_anchor_pairs,
)


def rectangle(left, top, width, height):
    return tuple(
        (y, left, left + width - 1)
        for y in range(top, top + height)
    )


def region(identifier):
    return {
        "id": identifier, "type": "region",
        "canvas_offset_xy": [0, 0], "size": [20, 20],
    }


def triangle_mesh(identifier):
    return {
        "id": identifier, "type": "mesh",
        "canvas_offset_xy": [0, 0],
        "vertices": [[0, 0], [10, 0], [0, 10]],
        "triangles": [0, 1, 2],
    }


class CommonAlphaSamplingTests(unittest.TestCase):
    def test_horizontal_major_axis_uses_equal_deterministic_quantiles(self) -> None:
        left = rectangle(0, 0, 10, 3)
        right = rectangle(2, 0, 7, 3)
        first = sample_common_alpha_pairs(left, right, (2, 0, 7, 3))
        second = sample_common_alpha_pairs(left, right, (2, 0, 7, 3))
        self.assertEqual(first, second)
        self.assertEqual("available", first.status)
        self.assertEqual("x", first.principal_axis)
        self.assertEqual(SAMPLING_PROFILE, first.sampling_profile)
        self.assertEqual(
            ((2.5, 1.5), (4.5, 1.5), (6.5, 1.5), (8.5, 1.5)),
            tuple(pair[0] for pair in first.canvas_point_pairs_xy),
        )
        self.assertTrue(all(a == b for a, b in first.canvas_point_pairs_xy))

    def test_vertical_major_axis_and_requested_count_boundaries(self) -> None:
        runs = rectangle(0, 0, 3, 10)
        two = sample_common_alpha_pairs(
            runs, runs, (0, 0, 3, 10), requested_pair_count=2
        )
        self.assertEqual("y", two.principal_axis)
        self.assertEqual(((1.5, 0.5), (1.5, 9.5)),
                         tuple(pair[0] for pair in two.canvas_point_pairs_xy))
        eight = sample_common_alpha_pairs(
            runs, runs, (0, 0, 3, 10), requested_pair_count=8
        )
        self.assertEqual(8, len(eight.canvas_point_pairs_xy))
        self.assertEqual(sorted(set(
            point[1] for point, _ in eight.canvas_point_pairs_xy
        )), [point[1] for point, _ in eight.canvas_point_pairs_xy])
        for invalid in (1, 9, True):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                SeamAnchorSamplingError, r"\[2, 8\]"
            ):
                sample_common_alpha_pairs(
                    runs, runs, (0, 0, 3, 10),
                    requested_pair_count=invalid,
                )

    def test_gap_and_insufficient_major_coordinates_are_explicit(self) -> None:
        gap = sample_common_alpha_pairs(
            ((0, 0, 2),), ((0, 4, 6),), (0, 0, 7, 1)
        )
        self.assertEqual("unavailable", gap.status)
        self.assertEqual("common_alpha_gap", gap.reason_code)
        one = sample_common_alpha_pairs(
            ((0, 2, 2),), ((0, 2, 2),), (0, 0, 5, 1)
        )
        self.assertEqual("unavailable", one.status)
        self.assertEqual("insufficient_common_alpha_points", one.reason_code)
        self.assertEqual((), one.canvas_point_pairs_xy)

    def test_invalid_runs_and_bbox_fail_before_sampling(self) -> None:
        with self.assertRaisesRegex(SeamAnchorSamplingError, "y-sorted"):
            sample_common_alpha_pairs(
                ((1, 0, 1), (0, 0, 1)), ((0, 0, 1),), (0, 0, 2, 2)
            )
        for bbox in ((0, 0, 0, 2), (0, 0, 2.0, 2), (0, 0, 2)):
            with self.subTest(bbox=bbox), self.assertRaises(
                SeamAnchorSamplingError
            ):
                sample_common_alpha_pairs(
                    ((0, 0, 1),), ((0, 0, 1),), bbox
                )

    def test_fixed_run_and_pixel_budgets_fail_closed(self) -> None:
        two_runs = ((0, 0, 1), (2, 0, 1))
        with patch(
            "autospine_workbench.seam_anchor_sampling.MAX_RUNS_PER_MASK", 1
        ):
            result = sample_common_alpha_pairs(
                two_runs, two_runs, (0, 0, 2, 3)
            )
        self.assertEqual("sampling_budget_exceeded", result.reason_code)
        with patch(
            "autospine_workbench.seam_anchor_sampling.MAX_COMMON_ALPHA_PIXELS", 3
        ):
            result = sample_common_alpha_pairs(
                ((0, 0, 3),), ((0, 0, 3),), (0, 0, 4, 1)
            )
        self.assertEqual("sampling_budget_exceeded", result.reason_code)

    def test_materializes_region_region_and_region_mesh_locators(self) -> None:
        runs = ((0, 0, 3),)
        sampling = sample_common_alpha_pairs(
            runs, runs, (0, 0, 4, 1), requested_pair_count=2
        )
        a, b = region("a"), region("b")
        region_pairs = materialize_sampled_locator_pairs(sampling, a, b)
        self.assertEqual(
            region_pairs,
            materialize_sampled_locator_pairs(sampling, a, b),
        )
        self.assertEqual(2, len(validate_anchor_pairs(
            region_pairs, a, b, principal_axis="x"
        )))
        mesh = triangle_mesh("m")
        mixed = materialize_sampled_locator_pairs(sampling, a, mesh)
        self.assertEqual("mesh-barycentric-q65535",
                         mixed[0]["b"]["locator_type"])

    def test_unavailable_sampling_cannot_materialize(self) -> None:
        unavailable = sample_common_alpha_pairs(
            ((0, 0, 1),), ((0, 3, 4),), (0, 0, 5, 1)
        )
        with self.assertRaisesRegex(SeamAnchorSamplingError, "unavailable"):
            materialize_sampled_locator_pairs(
                unavailable, region("a"), region("b")
            )


if __name__ == "__main__":
    unittest.main()
