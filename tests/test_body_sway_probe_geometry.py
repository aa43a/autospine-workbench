"""Positive and sampled-failure tests for body-sway structural geometry."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_probe_geometry import (  # noqa: E402
    evaluate_body_sway_geometry_sample,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.body_sway_probe_geometry_helpers import (  # noqa: E402
    attachment,
    exact_rig_and_target,
    sample,
)


class BodySwayProbeGeometryTests(unittest.TestCase):
    def test_region_mesh_full_fk_and_shared_index_evidence_pass(self):
        rig, target = exact_rig_and_target()
        result = evaluate_body_sway_geometry_sample(
            rig, target, sample(overlay={"pelvis-spine": 10.0})
        )

        self.assertEqual("passed", result.status)
        self.assertEqual("passed", result.fk_status)
        self.assertEqual(17, len(result.bones))
        self.assertEqual(sorted(bone["id"] for bone in rig["bones"]),
                         [bone.bone_id for bone in result.bones])
        for bone in result.bones:
            self.assertTrue(all(math.isfinite(value) for value in (
                *bone.origin_xy, bone.rotation_deg, *bone.endpoint_xy,
            )))
        pelvis = next(bone for bone in result.bones
                      if bone.bone_id == "pelvis-spine")
        self.assertEqual(-80.0, pelvis.rotation_deg)

        mesh = attachment(result, "leg-left")
        region = attachment(result, "torso")
        self.assertEqual("mesh", mesh.attachment_type)
        self.assertEqual("passed", mesh.shared_index_topology_status)
        self.assertEqual("passed", mesh.deformation.status)
        self.assertEqual(3, len(mesh.posed_vertices_xy))
        self.assertEqual("region", region.attachment_type)
        self.assertEqual("not_applicable", region.shared_index_topology_status)
        self.assertIsNone(region.deformation)
        self.assertEqual(4, len(region.posed_vertices_xy))
        self.assertEqual((), result.canvas_failures)

    def test_root_translation_moves_fk_and_every_attachment(self):
        rig, target = exact_rig_and_target()
        baseline = evaluate_body_sway_geometry_sample(rig, target, sample())
        moved = evaluate_body_sway_geometry_sample(
            rig, target, sample(translation=(3.5, -4.0))
        )

        for before, after in zip(baseline.bones, moved.bones, strict=True):
            self.assertEqual((3.5, -4.0), (
                after.origin_xy[0] - before.origin_xy[0],
                after.origin_xy[1] - before.origin_xy[1],
            ))
            self.assertEqual((3.5, -4.0), (
                after.endpoint_xy[0] - before.endpoint_xy[0],
                after.endpoint_xy[1] - before.endpoint_xy[1],
            ))
        for before, after in zip(
            baseline.attachments, moved.attachments, strict=True
        ):
            for bind, posed in zip(
                before.posed_vertices_xy, after.posed_vertices_xy, strict=True
            ):
                self.assertEqual((3.5, -4.0),
                                 (posed[0] - bind[0], posed[1] - bind[1]))
        self.assertEqual(
            attachment(baseline, "leg-left").deformation.metrics,
            attachment(moved, "leg-left").deformation.metrics,
        )

    def test_canvas_escape_is_explicit_sample_rejection(self):
        rig, target = exact_rig_and_target()
        result = evaluate_body_sway_geometry_sample(
            rig, target, sample(translation=(500.0, 0.0))
        )

        self.assertEqual("rejected", result.status)
        self.assertEqual("passed", result.fk_status)
        self.assertTrue(result.canvas_failures)
        self.assertTrue(all("right" in failure.sides
                            for failure in result.canvas_failures))
        self.assertEqual({"leg-left", "torso"}, {
            failure.attachment_id for failure in result.canvas_failures
        })
        self.assertTrue(all(row.canvas_status == "rejected"
                            for row in result.attachments))

    def test_posed_flip_and_stretch_are_structural_rejections(self):
        rig, target = exact_rig_and_target()
        mesh = next(row for row in rig["attachments"]
                    if row["id"] == "leg-left")
        hinge = mesh["vertices"][0]
        mesh["vertices"] = [
            list(hinge), [hinge[0], hinge[1] - 4.0],
            [hinge[0] + 4.0, hinge[1]],
        ]
        mesh["weights"] = [
            [{"bone": "thigh.left", "weight": 1.0}],
            [{"bone": "thigh.left", "weight": 1.0}],
            [{"bone": "calf.left", "weight": 1.0}],
        ]
        target["source"]["p3"]["rig_sha256"] = canonical_sha256(rig)
        flipped = evaluate_body_sway_geometry_sample(
            rig, target, sample(base={"calf.left": 180.0})
        )
        assessment = attachment(flipped, "leg-left").deformation
        self.assertEqual("rejected", assessment.status)
        self.assertGreater(assessment.metrics.flipped_count, 0)
        self.assertIn("flipped_triangles", assessment.reasons)

        stretched_rig, stretched_target = exact_rig_and_target(
            failing_mesh=True
        )
        stretched = evaluate_body_sway_geometry_sample(
            stretched_rig, stretched_target,
            sample(base={"calf.left": 90.0}),
        )
        assessment = attachment(stretched, "leg-left").deformation
        self.assertEqual("rejected", assessment.status)
        self.assertIn("maximum_edge_stretch", assessment.reasons)

    def test_result_is_deterministic_frozen_and_input_preserving(self):
        rig, target = exact_rig_and_target()
        pose = sample(overlay={"neck-head": -3.25}, translation=(1.0, -1.0))
        before = deepcopy((rig, target, pose))
        first = evaluate_body_sway_geometry_sample(rig, target, pose)
        second = evaluate_body_sway_geometry_sample(rig, target, pose)
        self.assertEqual(first, second)
        self.assertEqual(before, (rig, target, pose))
        detached = first.to_dict()
        detached["status"] = "forged"
        self.assertEqual("passed", first.status)
        with self.assertRaises(FrozenInstanceError):
            first.status = "forged"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
