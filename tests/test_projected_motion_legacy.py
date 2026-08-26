"""Tests for the fail-closed ProjectedMotionIR legacy bridge."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_validation import require_motion_ir  # noqa: E402
from autospine_workbench.projected_motion_legacy import (  # noqa: E402
    ProjectedMotionLegacyError,
    compile_projected_motion_to_motion_ir,
)
from tests.projected_motion_helpers import projected_motion_document  # noqa: E402


def _set_angle(sample: dict, angle_deg: float) -> None:
    radians = math.radians(angle_deg)
    sample["projected_vector_normalized"] = [
        math.cos(radians), math.sin(radians),
    ]
    sample["projected_world_angle_deg"] = angle_deg


def _track(document: dict, role: str, prop: str) -> dict:
    return next(
        track for track in document["tracks"]
        if track["target"] == role and track["property"] == prop
    )


class ProjectedMotionLegacyTests(unittest.TestCase):
    def test_zero_pose_and_root_translation_form_valid_motion_ir(self):
        projected = projected_motion_document(include_child=True)
        projected["root_samples"][1]["screen_translation_normalized"] = [
            0.1234567, -0.25,
        ]

        result = compile_projected_motion_to_motion_ir(projected)

        require_motion_ir(result)
        self.assertEqual(
            [0.0, 0.0],
            [key["value"] for key in _track(
                result, "humanoid.spine.lower", "rotation"
            )["keys"]],
        )
        self.assertEqual(
            [0.12346, -0.25],
            _track(result, "humanoid.root", "translation")["keys"][1]["value"],
        )

    def test_frame_zero_baselines_and_parent_delta_are_setup_local(self):
        projected = projected_motion_document(include_child=True)
        root, child = projected["segment_tracks"]
        _set_angle(root["samples"][0], 10.0)
        _set_angle(root["samples"][1], 25.0)
        _set_angle(child["samples"][0], 30.0)
        _set_angle(child["samples"][1], 55.0)

        result = compile_projected_motion_to_motion_ir(projected)

        self.assertEqual(
            [0.0, 15.0],
            [key["value"] for key in _track(
                result, "humanoid.root", "rotation"
            )["keys"]],
        )
        self.assertEqual(
            [0.0, 10.0],
            [key["value"] for key in _track(
                result, "humanoid.spine.lower", "rotation"
            )["keys"]],
        )

    def test_rejects_any_collapsed_sample(self):
        projected = projected_motion_document(
            collapsed=True, include_child=True,
        )
        with self.assertRaisesRegex(
            ProjectedMotionLegacyError, "rejects collapsed.*frame 0",
        ):
            compile_projected_motion_to_motion_ir(projected)

    def test_markers_are_copied_without_aliasing(self):
        projected = projected_motion_document(include_child=True)
        projected["markers"] = [{
            "kind": "contact",
            "limb": "leg.left",
            "start_tick": 0,
            "end_tick": 33333,
            "mode": "annotation_only",
        }]
        result = compile_projected_motion_to_motion_ir(projected)
        self.assertEqual(projected["markers"], result["markers"])
        self.assertIsNot(projected["markers"], result["markers"])


if __name__ == "__main__":
    unittest.main()
