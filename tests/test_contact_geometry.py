from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.alpha_geometry import analyze_alpha_png  # noqa: E402
from autospine_workbench.contact_geometry import (  # noqa: E402
    contact_between_alpha,
    contact_between_runs,
    intersect_canvas_runs,
)
from tests.png_helpers import write_rgba  # noqa: E402


TRANSPARENT = (0, 0, 0, 0)
VISIBLE = (30, 40, 50, 255)


def rectangle(x0: int, y0: int, width: int, height: int):
    return tuple((y, x0, x0 + width - 1) for y in range(y0, y0 + height))


class ContactGeometryTests(unittest.TestCase):
    def test_single_overlap_reports_exact_statistics(self) -> None:
        result = contact_between_runs(rectangle(0, 0, 20, 20), rectangle(10, 10, 20, 20))

        self.assertEqual(16, result.min_lobe_area)
        self.assertEqual((), result.qa_flags)
        self.assertEqual(1, len(result.contacts))
        contact = result.contacts[0]
        self.assertEqual("overlap.000", contact.id)
        self.assertEqual("overlap", contact.mode)
        self.assertEqual(100, contact.area)
        self.assertEqual((10, 10, 10, 10), contact.bbox_xywh)
        self.assertEqual((14.5, 14.5), contact.centroid_xy)
        self.assertEqual((8.25, 8.25), contact.variance_xy)
        self.assertEqual(4.062019, contact.error_radius)
        self.assertEqual((0.25, 0.25), (contact.overlap_ratio_a, contact.overlap_ratio_b))
        self.assertEqual((14.0, 14.0), contact.representative_xy)

    def test_two_lobes_have_stable_area_then_bbox_ids(self) -> None:
        runs = tuple(
            sorted(
                rectangle(0, 0, 4, 4) + rectangle(10, 10, 4, 4),
                key=lambda item: (item[0], item[1]),
            )
        )
        result = contact_between_runs(runs, runs)

        self.assertEqual(["overlap.000", "overlap.001"], [item.id for item in result.contacts])
        self.assertEqual([16, 16], [item.area for item in result.contacts])
        self.assertEqual([(0, 0, 4, 4), (10, 10, 4, 4)], [item.bbox_xywh for item in result.contacts])

    def test_diagonal_touch_is_one_eight_connected_lobe(self) -> None:
        runs = rectangle(0, 0, 4, 2) + rectangle(4, 2, 4, 2)
        result = contact_between_runs(runs, runs)

        self.assertEqual(1, len(result.contacts))
        self.assertEqual(16, result.contacts[0].area)
        self.assertEqual((0, 0, 8, 4), result.contacts[0].bbox_xywh)

    def test_gap_within_limit_emits_midpoint_and_endpoints(self) -> None:
        result = contact_between_runs(((0, 0, 20),), ((0, 23, 43),), max_gap=3)

        self.assertEqual((), result.qa_flags)
        contact = result.contacts[0]
        self.assertEqual("gap", contact.mode)
        self.assertEqual(3.0, contact.gap_distance_px)
        self.assertEqual((20.0, 0.0), contact.source_xy_a)
        self.assertEqual((23.0, 0.0), contact.source_xy_b)
        self.assertEqual((21.5, 0.0), contact.representative_xy)
        self.assertEqual(1.5, contact.error_radius)

    def test_gap_outside_limit_is_explicit(self) -> None:
        result = contact_between_runs(((0, 0, 20),), ((0, 23, 43),), max_gap=2)

        self.assertEqual((), result.contacts)
        self.assertEqual(("CONTACT_GAP_TOO_LARGE",), result.qa_flags)

    def test_repeated_analysis_is_value_deterministic(self) -> None:
        left = rectangle(0, 0, 30, 30)
        right = rectangle(7, 4, 30, 30)
        first = contact_between_runs(left, right, max_gap=5)
        for _ in range(10):
            self.assertEqual(first, contact_between_runs(left, right, max_gap=5))

    def test_negative_canvas_offset_has_exact_variance(self) -> None:
        runs = rectangle(-4, -3, 4, 4)
        contact = contact_between_runs(runs, runs).contacts[0]

        self.assertEqual((-4, -3, 4, 4), contact.bbox_xywh)
        self.assertEqual((-2.5, -1.5), contact.centroid_xy)
        self.assertEqual((1.25, 1.25), contact.variance_xy)

    def test_canvas_run_intersection_supports_offset_bilateral_masks(self) -> None:
        rows_a = [[TRANSPARENT for _ in range(6)] for _ in range(4)]
        rows_b = [[TRANSPARENT for _ in range(6)] for _ in range(4)]
        for y in (1, 2):
            for x in range(1, 5):
                rows_a[y][x] = VISIBLE
        for y in (0, 1, 2):
            for x in range(0, 4):
                rows_b[y][x] = VISIBLE
        with tempfile.TemporaryDirectory() as directory:
            path_a, path_b = Path(directory) / "left.png", Path(directory) / "right.png"
            write_rgba(path_a, rows_a)
            write_rgba(path_b, rows_b)
            alpha_a = analyze_alpha_png(path_a, canvas_offset_xy=(100, 200))
            alpha_b = analyze_alpha_png(path_b, canvas_offset_xy=(102, 201))

        self.assertEqual(((201, 102, 104), (202, 102, 104)), intersect_canvas_runs(
            alpha_a.canvas_runs(), alpha_b.canvas_runs()
        ))
        # Six pixels are real contact but intentionally below the production lobe threshold.
        analysis = contact_between_alpha(alpha_a, alpha_b)
        self.assertEqual((), analysis.contacts)
        self.assertEqual(("CONTACT_OVERLAP_BELOW_THRESHOLD",), analysis.qa_flags)

    def test_invalid_noncanonical_runs_and_gap_are_rejected(self) -> None:
        for runs in (((0, 2, 1),), ((0, 0, 1), (0, 2, 3)), ((1, 0, 1), (0, 0, 1))):
            with self.subTest(runs=runs):
                with self.assertRaises(ValueError):
                    contact_between_runs(runs, ())
        for gap in (-1, 257, float("nan"), True):
            with self.subTest(gap=gap):
                with self.assertRaises(ValueError):
                    contact_between_runs((), (), max_gap=gap)


if __name__ == "__main__":
    unittest.main()
