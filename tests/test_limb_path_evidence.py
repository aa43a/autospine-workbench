"""Contract-shaped limb alpha path analysis tests."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.limb_evidence_layers import load_limb_evidence  # noqa: E402
from autospine_workbench.limb_path_evidence import analyze_limb_paths  # noqa: E402
from autospine_workbench.pose_observations import (  # noqa: E402
    PoseJointObservation,
    PoseObservationSet,
)
from tests.png_helpers import write_rgba  # noqa: E402


CANVAS = (80, 80)
CONFIG = {
    "alpha_threshold": 8,
    "component_min_area": 16,
    "component_min_ratio": 0.001,
}
TRANSPARENT = (0, 0, 0, 0)
OPAQUE = (100, 110, 120, 255)


def observations(joints: dict[str, tuple[float, float]]) -> PoseObservationSet:
    return PoseObservationSet(
        project_id="sample",
        image_sha256="a" * 64,
        canvas_size=CANVAS,
        detector_id="diagnostic-prior",
        detector_version="1",
        model_revision="fixture",
        config_sha256="b" * 64,
        runtime="unittest",
        detected_count=1,
        selected_index=0,
        selection_method="single",
        joints={
            joint_id: PoseJointObservation(x, y, 0.8, "visible")
            for joint_id, (x, y) in joints.items()
        },
        document_sha256="c" * 64,
    )


def layer(layer_id: str, role: str, side: str) -> dict:
    return {
        "id": layer_id,
        "canonical_role": role,
        "side": side,
        "disposition": "keep",
        "empty": False,
        "bbox": {"x": 0, "y": 0, "width": 80, "height": 80},
    }


class LimbPathEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def evidence(self, item: dict, pixels: set[tuple[int, int]]):
        asset = Path(self.directory.name) / f"{item['id']}.png"
        rows = [[TRANSPARENT for _ in range(CANVAS[0])] for _ in range(CANVAS[1])]
        for x, y in pixels:
            rows[y][x] = OPAQUE
        write_rgba(asset, rows)
        project = {
            "layers": [item],
            "resolved": {"layers": [item]},
        }
        return load_limb_evidence(
            project,
            {item["id"]: asset},
            CANVAS,
            CONFIG,
            include_contact_roles=True,
        )

    def test_explicit_side_path_is_valid_stable_and_hinge_preserving(self) -> None:
        pixels = {(x, y) for x in range(10, 21) for y in range(5, 76)}
        evidence = self.evidence(layer("arm-left", "body.hand", "left"), pixels)
        pose = observations({
            "shoulder.left": (15, 10),
            "elbow.left": (15, 40),
            "wrist.left": (15, 70),
        })
        first = analyze_limb_paths(evidence, pose, CANVAS, CONFIG)
        second = analyze_limb_paths(evidence, pose, CANVAS, CONFIG)
        self.assertEqual(first, second)
        self.assertEqual(1, len(first.paths))
        path = first.paths[0]
        self.assertEqual("arm.left.path.000", path["path_id"])
        self.assertEqual("valid", path["status"])
        self.assertIn(path["hinge_candidate_xy"], path["polyline_xy"])
        self.assertIn("PATH_PREFERRED", path["flags"])
        self.assertEqual("visible", first.joint_states["elbow.left"]["status"])
        self.assertEqual("absent", first.joint_states["shoulder.right"]["status"])

    def test_single_bilateral_component_is_shared_but_observability_is_merged(self) -> None:
        pixels = {(x, y) for x in range(20, 61) for y in range(5, 76)}
        evidence = self.evidence(layer("legs", "body.leg", "bilateral"), pixels)
        pose = observations({
            "hip.left": (30, 10), "knee.left": (30, 40), "ankle.left": (30, 70),
            "hip.right": (50, 10), "knee.right": (50, 40), "ankle.right": (50, 70),
        })
        sections = analyze_limb_paths(evidence, pose, CANVAS, CONFIG)
        leg_paths = [item for item in sections.paths if item["limb_id"].startswith("leg")]
        self.assertEqual(2, len(leg_paths))
        self.assertEqual({0}, {item["component_id"] for item in leg_paths})
        self.assertTrue(all("BILATERAL_FUSED_COMPONENT" in item["flags"] for item in leg_paths))
        for side in ("left", "right"):
            self.assertEqual("merged", sections.joint_states[f"hip.{side}"]["status"])

    def test_raster_budget_failure_is_explicit_unavailable_evidence(self) -> None:
        pixels = {(x, y) for x in range(10, 31) for y in range(5, 76)}
        evidence = self.evidence(layer("arm-left", "body.hand", "left"), pixels)
        pose = observations({
            "shoulder.left": (15, 10),
            "elbow.left": (15, 40),
            "wrist.left": (15, 70),
        })
        sections = analyze_limb_paths(
            evidence, pose, CANVAS, {**CONFIG, "max_raster_pixels": 100}
        )
        path = sections.paths[0]
        self.assertEqual("unavailable", path["status"])
        self.assertEqual([], path["polyline_xy"])
        self.assertIsNone(path["length_px"])
        self.assertIn("RASTER_BUDGET_EXCEEDED", path["flags"])

    def test_missing_leg_layer_produces_no_shortcut_path(self) -> None:
        pixels = {(x, y) for x in range(10, 21) for y in range(5, 76)}
        evidence = self.evidence(layer("arm-left", "body.hand", "left"), pixels)
        pose = observations({
            "hip.left": (30, 10), "knee.left": (30, 40), "ankle.left": (30, 70),
        })
        sections = analyze_limb_paths(evidence, pose, CANVAS, CONFIG)
        self.assertFalse(any(item["limb_id"].startswith("leg") for item in sections.paths))
        self.assertIn("NO_LEG_SEMANTIC_LAYER", sections.qa_flags)


if __name__ == "__main__":
    unittest.main()
