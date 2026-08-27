"""Bounded referenced-only alpha cache tests for P10.5a seams."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from autospine_workbench.alpha_geometry import analyze_alpha_image
from autospine_workbench.png_rgba import decode_rgba_png
from autospine_workbench.seam_anchor_alpha_cache import (
    build_seam_alpha_index,
)
from tests.seam_anchor_candidate_helpers import seam_inputs


class SeamAnchorAlphaCacheTests(unittest.TestCase):
    def setUp(self):
        self.inputs = seam_inputs()
        self.attachments = {
            item["id"]: item for item in self.inputs.rig["attachments"]
        }

    def test_irrelevant_attachments_are_never_decoded_or_analyzed_again(self):
        with patch(
            "autospine_workbench.seam_anchor_alpha_cache.decode_rgba_png",
            wraps=decode_rgba_png,
        ) as decode, patch(
            "autospine_workbench.seam_anchor_alpha_cache.analyze_alpha_image",
            wraps=analyze_alpha_image,
        ) as analyze:
            result = build_seam_alpha_index(
                self.inputs, self.attachments, {"torso"}
            )
        self.assertEqual({"torso"}, set(result))
        self.assertEqual(1, decode.call_count)
        self.assertEqual(1, analyze.call_count)

    def test_global_run_budget_clears_partial_cache_and_stops_later_work(self):
        target = "autospine_workbench.seam_anchor_alpha_cache"
        with patch(f"{target}.MAX_TOTAL_ALPHA_RUNS", 1), patch(
            f"{target}.decode_rgba_png", wraps=decode_rgba_png
        ) as decode:
            result = build_seam_alpha_index(
                self.inputs, self.attachments, set(self.attachments)
            )
        self.assertEqual(set(self.attachments), set(result))
        self.assertTrue(all(value is None for value in result.values()))
        self.assertEqual(1, decode.call_count)


if __name__ == "__main__":
    unittest.main()
