"""Pose-conditioned alpha clearance path tests."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.alpha_paths import trace_alpha_clearance_path  # noqa: E402


def rectangle(left: int, top: int, right: int, bottom: int) -> list[tuple[int, int, int]]:
    return [(y, left, right) for y in range(top, bottom + 1)]


def foreground(runs: list[tuple[int, int, int]]) -> set[tuple[int, int]]:
    return {(x, y) for y, start, end in runs for x in range(start, end + 1)}


class AlphaClearancePathTests(unittest.TestCase):
    def test_straight_tube_prefers_interior_and_caps_polyline(self) -> None:
        runs = rectangle(0, 0, 300, 8)
        anchors = {"proximal": (1, 4), "hinge": (150, 4), "distal": (299, 4)}
        result = trace_alpha_clearance_path(runs, anchors)
        self.assertLessEqual(len(result.polyline_xy), 128)
        self.assertIn("POLYLINE_DOWNSAMPLED", result.flags)
        self.assertGreater(result.length_px or 0, 295)
        self.assertGreater(result.median_clearance_px or 0, 1)
        self.assertTrue(set(result.polyline_xy) <= foreground(runs))
        self.assertIn(result.hinge_candidate_xy, result.polyline_xy)

    def test_l_tube_visits_pose_hinge_and_stays_in_mask(self) -> None:
        runs = rectangle(0, 0, 6, 24) + rectangle(0, 19, 25, 25)
        anchors = {"proximal": (3, 1), "hinge": (3, 22), "distal": (24, 22)}
        result = trace_alpha_clearance_path(runs, anchors)
        self.assertEqual((3, 22), result.hinge_candidate_xy)
        self.assertIn(result.hinge_candidate_xy, result.polyline_xy)
        self.assertTrue(set(result.polyline_xy) <= foreground(runs))
        self.assertNotIn("ANCHORS_DISCONNECTED", result.flags)
        self.assertIsNotNone(result.error_radius_px)

    def test_y_branch_tie_break_is_stable(self) -> None:
        runs: list[tuple[int, int, int]] = []
        for y in range(0, 11):
            runs.append((y, 4 + y, 6 + y))
            runs.append((y, 24 - y, 26 - y))
        runs.extend(rectangle(14, 10, 16, 30))
        anchors = {"proximal": (15, 29), "hinge": (15, 10), "distal": (5, 0)}
        first = trace_alpha_clearance_path(runs, anchors)
        second = trace_alpha_clearance_path(reversed(runs), anchors)
        self.assertEqual(first, second)
        self.assertEqual((15, 10), first.hinge_candidate_xy)
        self.assertTrue(set(first.polyline_xy) <= foreground(runs))

    def test_disconnected_projected_anchors_fail_closed(self) -> None:
        runs = rectangle(0, 0, 2, 2) + rectangle(10, 0, 12, 2)
        anchors = {"proximal": (0, 1), "hinge": (2, 1), "distal": (12, 1)}
        result = trace_alpha_clearance_path(runs, anchors)
        self.assertEqual((), result.polyline_xy)
        self.assertIn("ANCHORS_DISCONNECTED", result.flags)
        self.assertEqual((12, 1), result.projected_anchors["distal"].xy)

    def test_raster_and_search_budgets_return_flags(self) -> None:
        sparse = [(0, 0, 0), (100, 100, 100)]
        anchors = {"proximal": (0, 0), "hinge": (50, 50), "distal": (100, 100)}
        raster_limited = trace_alpha_clearance_path(
            sparse, anchors, max_raster_pixels=100
        )
        self.assertIn("RASTER_BUDGET_EXCEEDED", raster_limited.flags)
        self.assertEqual(0, raster_limited.search_nodes)

        tube = rectangle(0, 0, 30, 6)
        search_limited = trace_alpha_clearance_path(
            tube,
            {"proximal": (1, 3), "hinge": (15, 3), "distal": (29, 3)},
            max_search_nodes=1,
        )
        self.assertIn("SEARCH_BUDGET_EXCEEDED", search_limited.flags)
        self.assertEqual(1, search_limited.search_nodes)
        self.assertEqual((), search_limited.polyline_xy)

    def test_anchor_projection_reports_residual_and_is_deterministic(self) -> None:
        runs = rectangle(5, 5, 15, 11)
        anchors = {"proximal": (1, 8), "hinge": (10, 3), "distal": (20, 8)}
        result = trace_alpha_clearance_path(runs, anchors)
        self.assertIn("ANCHORS_PROJECTED_TO_ALPHA", result.flags)
        self.assertEqual((5, 8), result.projected_anchors["proximal"].xy)
        self.assertEqual((10, 5), result.projected_anchors["hinge"].xy)
        self.assertEqual((15, 8), result.projected_anchors["distal"].xy)
        self.assertGreater(result.projected_anchors["hinge"].residual_px, 0)
        self.assertTrue(set(result.polyline_xy) <= foreground(runs))


if __name__ == "__main__":
    unittest.main()
