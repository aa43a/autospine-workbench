"""Tests for reviewed heading interpretation and root-forward cross-checks."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.heading_evidence_math import (  # noqa: E402
    HeadingEvidenceMathError,
    heading_frame_math,
    map_heading_components,
    unwrap_yaw_degrees,
)


IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
BASIS = {"screen_x": "+X", "screen_y": "-Y", "depth": "+Z"}


class HeadingEvidenceMathTests(unittest.TestCase):
    def test_maps_reviewed_components_and_matches_root_forward(self):
        result = heading_frame_math(
            [0.0, 1.0], ["+X", "+Z"], BASIS, IDENTITY, "+Z"
        )
        self.assertEqual(result["world_direction_xyz"], [0.0, 0.0, 1.0])
        self.assertEqual(result["camera_screen_x_component"], 0.0)
        self.assertEqual(result["camera_depth_component"], 1.0)
        self.assertEqual(result["raw_yaw_deg"], 0.0)
        self.assertEqual(result["root_forward_angle_error_deg"], 0.0)

    def test_respects_signed_component_and_camera_axes(self):
        result = heading_frame_math(
            [1.0, 0.0], ["-X", "+Z"],
            {"screen_x": "-X", "screen_y": "-Y", "depth": "+Z"},
            IDENTITY, "+Z",
        )
        self.assertEqual(result["world_direction_xyz"], [-1.0, 0.0, 0.0])
        self.assertEqual(result["camera_screen_x_component"], 1.0)
        self.assertEqual(result["raw_yaw_deg"], 90.0)
        self.assertEqual(result["root_forward_angle_error_deg"], 90.0)

    def test_unwraps_across_atan_boundary(self):
        self.assertEqual(
            unwrap_yaw_degrees([170.0, -170.0, -160.0]),
            (170.0, 190.0, 200.0),
        )

    def test_component_mapping_does_not_require_root_forward(self):
        result = map_heading_components(
            [0.0, 1.0], ["+X", "+Z"], BASIS
        )
        self.assertEqual(result["world_direction_xyz"], [0.0, 0.0, 1.0])
        self.assertEqual(result["raw_yaw_deg"], 0.0)

    def test_rejects_nonunit_nonfinite_and_degenerate_root_projection(self):
        cases = (
            ([0.0, 0.0], IDENTITY, "+Z"),
            ([float("nan"), 1.0], IDENTITY, "+Z"),
            (
                [0.0, 1.0],
                ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)),
                "+Z",
            ),
        )
        for raw, matrix, forward in cases:
            with self.subTest(raw=raw), self.assertRaises(
                HeadingEvidenceMathError
            ):
                heading_frame_math(
                    raw, ["+X", "+Z"], BASIS, matrix, forward
                )

    def test_reports_known_root_crosscheck_angle(self):
        radians = math.radians(30.0)
        matrix = (
            (math.cos(radians), 0.0, math.sin(radians)),
            (0.0, 1.0, 0.0),
            (-math.sin(radians), 0.0, math.cos(radians)),
        )
        result = heading_frame_math(
            [0.0, 1.0], ["+X", "+Z"], BASIS, matrix, "+Z"
        )
        self.assertAlmostEqual(result["root_forward_angle_error_deg"], 30.0)


if __name__ == "__main__":
    unittest.main()
