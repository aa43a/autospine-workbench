"""Representation-aware composite comparison tests."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKBENCH_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.composite_quality import (  # noqa: E402
    CompositeQualityCache,
    compare_composite_pngs,
)
from tests.png_helpers import write_rgba  # noqa: E402


class CompositeQualityTests(unittest.TestCase):
    def test_disabled_cache_skips_pixel_decoding_for_offline_builds(self) -> None:
        metrics = CompositeQualityCache(enabled=False).measure(
            "a" * 64,
            12.5,
            Path("missing-composite.png"),
            Path("missing-embedded.png"),
        )
        self.assertEqual(
            {
                "status": "unavailable",
                "raw_rgba_mae": 12.5,
                "alpha_representation": "not_measured",
            },
            metrics,
        )

    def test_transparent_rgb_vs_flattened_black_is_not_a_visual_failure(self) -> None:
        transparent_white = (255, 255, 255, 0)
        opaque_black = (0, 0, 0, 255)
        opaque_red = (220, 20, 30, 255)
        with tempfile.TemporaryDirectory() as directory:
            composite = Path(directory) / "composite.png"
            embedded = Path(directory) / "embedded.png"
            write_rgba(composite, [[transparent_white, opaque_red], [transparent_white, transparent_white]])
            write_rgba(embedded, [[opaque_black, opaque_red], [opaque_black, opaque_black]])
            metrics = compare_composite_pngs(composite, embedded)
        self.assertGreater(metrics.raw_rgba_mae, 100)
        self.assertEqual("flattened_reference", metrics.alpha_representation)
        self.assertEqual((0, 0, 0), metrics.inferred_background_rgb)
        self.assertEqual(0, metrics.background_matched_rgb_mae)
        self.assertEqual("passed", metrics.status)

    def test_visible_color_difference_remains_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            composite = Path(directory) / "composite.png"
            embedded = Path(directory) / "embedded.png"
            write_rgba(composite, [[(255, 0, 0, 255)]])
            write_rgba(embedded, [[(0, 0, 255, 255)]])
            metrics = compare_composite_pngs(composite, embedded)
        self.assertGreater(metrics.background_matched_rgb_mae, 5)
        self.assertEqual("comparable", metrics.alpha_representation)
        self.assertEqual("manual_required", metrics.status)


if __name__ == "__main__":
    unittest.main()
