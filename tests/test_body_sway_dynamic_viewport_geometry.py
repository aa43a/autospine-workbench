"""Reviewed world-viewport containment tests for sampled and interval paths."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_continuous_interval_geometry import (  # noqa: E402
    assess_body_sway_interval_box,
)
from autospine_workbench.body_sway_interval_arithmetic import (  # noqa: E402
    OutwardInterval,
)
from autospine_workbench.body_sway_probe_geometry import (  # noqa: E402
    evaluate_prepared_body_sway_geometry_sample,
)
from autospine_workbench.body_sway_probe_geometry_context import (  # noqa: E402
    BodySwayProbeGeometryError,
    prepare_body_sway_geometry_context,
    prepare_body_sway_geometry_context_for_viewport,
)
from tests.body_sway_probe_geometry_helpers import (  # noqa: E402
    exact_rig_and_target,
    sample,
)


class BodySwayDynamicViewportGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rig, cls.target = exact_rig_and_target()
        cls.default = prepare_body_sway_geometry_context(
            cls.rig, cls.target,
        )
        cls.dynamic = prepare_body_sway_geometry_context_for_viewport(
            cls.rig, cls.target,
            {"x": -1024.0, "y": -1024.0,
             "width": 2048.0, "height": 2048.0},
        )

    def test_sampled_containment_uses_reviewed_origin_and_extent(self):
        moved = sample(translation=(-500.0, -500.0))
        fixed = evaluate_prepared_body_sway_geometry_sample(
            self.default, moved,
        )
        dynamic = evaluate_prepared_body_sway_geometry_sample(
            self.dynamic, moved,
        )
        self.assertTrue(fixed.canvas_failures)
        self.assertEqual((), dynamic.canvas_failures)
        self.assertEqual((-1024.0, -1024.0), self.dynamic.canvas_origin)
        self.assertEqual((2048.0, 2048.0), self.dynamic.canvas_size)

    def test_interval_containment_uses_the_same_dynamic_viewport(self):
        moved = sample(translation=(-500.0, -500.0), tick=0)
        moved_after = sample(translation=(-500.0, -500.0), tick=1)
        arguments = {
            "left_base_rotation_deg": dict(moved.base_rotation_deg),
            "right_base_rotation_deg": dict(moved_after.base_rotation_deg),
            "left_overlay_rotation_deg": dict(moved.overlay_rotation_deg),
            "right_overlay_rotation_deg":
                dict(moved_after.overlay_rotation_deg),
            "left_root_translation_xy": moved.root_translation_xy,
            "right_root_translation_xy": moved_after.root_translation_xy,
            "time_fraction": OutwardInterval.point(0.5),
            "gain": OutwardInterval.point(1.0),
        }
        fixed = assess_body_sway_interval_box(self.default, **arguments)
        dynamic = assess_body_sway_interval_box(self.dynamic, **arguments)
        self.assertIn("canvas_containment_unproven", fixed.reason_codes)
        self.assertNotIn(
            "canvas_containment_unproven", dynamic.reason_codes,
        )
        self.assertGreater(dynamic.bounds.canvas_margin_lower_px, 0.0)

    def test_viewport_contract_is_exact_and_positive(self):
        invalid = (
            {"x": 0, "y": 0, "width": 10},
            {"x": 0, "y": 0, "width": 0, "height": 10},
            {"x": 0, "y": 0, "width": 10, "height": -1},
            {"x": 0, "y": 0, "width": 10, "height": 10,
             "path": "private"},
        )
        for viewport in invalid:
            with self.subTest(viewport=viewport), self.assertRaises(
                BodySwayProbeGeometryError
            ):
                prepare_body_sway_geometry_context_for_viewport(
                    self.rig, self.target, viewport,
                )


if __name__ == "__main__":
    unittest.main()
