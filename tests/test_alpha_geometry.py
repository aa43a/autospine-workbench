"""Alpha run/component geometry tests."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.alpha_geometry import analyze_alpha_png  # noqa: E402
from tests.png_helpers import write_rgba  # noqa: E402


TRANSPARENT = (0, 0, 0, 0)
VISIBLE = (20, 30, 40, 255)


class AlphaGeometryTests(unittest.TestCase):
    def test_components_are_8_connected_stable_and_canvas_offset_aware(self) -> None:
        rows = [[TRANSPARENT for _ in range(7)] for _ in range(6)]
        for x, y in ((1, 1), (2, 1), (2, 2), (3, 3), (5, 4), (5, 5)):
            rows[y][x] = VISIBLE
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.png"
            write_rgba(path, rows)
            geometry = analyze_alpha_png(path, canvas_offset_xy=(100, 200))

        self.assertEqual(2, len(geometry.components))
        self.assertEqual([4, 2], [item.area for item in geometry.components])
        self.assertEqual((101, 201, 3, 3), geometry.components[0].bbox_xywh)
        self.assertEqual((102.0, 201.75), geometry.components[0].centroid_xy)
        self.assertEqual(frozenset({0, 1}), geometry.significant_component_ids(min_area=1))

    def test_nearest_foreground_can_filter_noise_components(self) -> None:
        rows = [[TRANSPARENT for _ in range(8)] for _ in range(4)]
        for x in range(2, 6):
            rows[2][x] = VISIBLE
        rows[0][7] = VISIBLE
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.png"
            write_rgba(path, rows)
            geometry = analyze_alpha_png(path)

        all_hit = geometry.nearest_foreground(7, 0)
        significant = geometry.significant_component_ids(min_area=2)
        filtered_hit = geometry.nearest_foreground(7, 0, component_ids=significant)
        self.assertEqual(1, all_hit.component_id)
        self.assertEqual((5.0, 2.0), filtered_hit.xy)
        self.assertAlmostEqual(8**0.5, filtered_hit.distance_px)

    def test_empty_alpha_and_invalid_threshold_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.png"
            write_rgba(path, [[TRANSPARENT]])
            geometry = analyze_alpha_png(path)
        self.assertEqual(0, geometry.foreground_area)
        self.assertIsNone(geometry.nearest_foreground(0, 0))
        with self.assertRaises(ValueError):
            analyze_alpha_png(path, threshold=0)


if __name__ == "__main__":
    unittest.main()
