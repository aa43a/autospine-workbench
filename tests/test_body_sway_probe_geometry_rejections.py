"""Fail-closed input tests for body-sway structural geometry."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_probe_geometry import (  # noqa: E402
    BodySwayProbeGeometryError,
    evaluate_body_sway_geometry_sample,
)
from autospine_workbench.body_sway_probe_math import (  # noqa: E402
    BodySwayPoseSample,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.body_sway_probe_geometry_helpers import (  # noqa: E402
    exact_rig_and_target,
    sample,
)


def rebind(rig, target):
    target["source"]["p3"]["rig_sha256"] = canonical_sha256(rig)


def mesh(rig):
    return next(row for row in rig["attachments"] if row["type"] == "mesh")


class BodySwayProbeGeometryRejectionTests(unittest.TestCase):
    def assert_rejected(self, rig, target, pose=None):
        with self.assertRaises(BodySwayProbeGeometryError):
            evaluate_body_sway_geometry_sample(
                rig, target, pose if pose is not None else sample()
            )

    def test_forged_pose_sample_relationships_are_rejected(self):
        rig, target = exact_rig_and_target()
        valid = sample(overlay={"spine-chest": 2.0})

        def changed(rows, bone_id, value):
            return tuple((bone, value if bone == bone_id else number)
                         for bone, number in rows)

        reversed_rows = tuple(reversed(valid.base_rotation_deg))
        cases = [
            replace(
                valid, base_rotation_deg=reversed_rows,
                combined_rotation_deg=tuple(reversed(valid.combined_rotation_deg)),
            ),
            replace(valid, overlay_rotation_deg=valid.overlay_rotation_deg[:-1]),
            replace(
                valid,
                combined_rotation_deg=tuple(
                    (bone, value + (1.0 if bone == "spine-chest" else 0.0))
                    for bone, value in valid.combined_rotation_deg
                ),
            ),
            replace(
                valid,
                combined_rotation_deg=(*valid.combined_rotation_deg,
                                       ("unknown-bone", 0.0)),
            ),
            replace(valid, root_translation_xy=(math.nan, 0.0)),
            replace(valid, root_translation_xy=(True, 0.0)),
            replace(
                valid,
                base_rotation_deg=changed(
                    valid.base_rotation_deg, "chest-neck", 0.0000000001
                ),
            ),
            replace(
                valid,
                overlay_rotation_deg=changed(
                    valid.overlay_rotation_deg, "chest-neck", -0.0
                ),
            ),
            replace(valid, root_translation_xy=(0.0000000001, 0.0)),
            replace(valid, root_translation_xy=(-0.0, 0.0)),
        ]
        for forged in cases:
            with self.subTest(forged=forged):
                self.assert_rejected(rig, target, forged)

        class Spoof:
            tick = valid.tick
            base_rotation_deg = valid.base_rotation_deg
            overlay_rotation_deg = valid.overlay_rotation_deg
            combined_rotation_deg = valid.combined_rotation_deg
            root_translation_xy = valid.root_translation_xy

        self.assert_rejected(rig, target, Spoof())

    def test_cross_wired_rig_and_mesh_inventory_are_rejected(self):
        rig, target = exact_rig_and_target()
        rig["attachments"][1]["canvas_offset_xy"][0] += 1.0
        self.assert_rejected(rig, target)

        rig, target = exact_rig_and_target()
        mesh(rig)["id"] = "leg-other"
        rig["slots"][0]["setup_attachment"] = "leg-other"
        rebind(rig, target)
        self.assert_rejected(rig, target)

        rig, target = exact_rig_and_target()
        mesh(rig)["weights"][2] = [
            {"bone": "calf.right", "weight": 1.0}
        ]
        rebind(rig, target)
        self.assert_rejected(rig, target)

    def test_unknown_references_types_and_nonfinite_geometry_are_rejected(self):
        mutations = (
            lambda rig: rig["attachments"][1].update(slot="missing"),
            lambda rig: rig["attachments"][1].update(type="sprite"),
            lambda rig: rig["attachments"][1].update(size=[True, 12.0]),
            lambda rig: rig["attachments"][1].update(
                canvas_offset_xy=[math.inf, 100.0]
            ),
        )
        for mutate in mutations:
            rig, target = exact_rig_and_target()
            mutate(rig)
            try:
                rebind(rig, target)
            except ValueError:  # non-JSON finite values fail before SHA binding
                pass
            with self.subTest(mutate=mutate):
                self.assert_rejected(rig, target)

    def test_bad_topology_uvs_and_setup_degeneracy_are_rejected(self):
        def out_of_range(rig):
            mesh(rig)["triangles"] = [0, 1, 9]

        def bool_index(rig):
            mesh(rig)["triangles"] = [0, 1, True]

        def repeated_index(rig):
            mesh(rig)["triangles"] = [0, 0, 1]

        def collinear(rig):
            row = mesh(rig)
            x, y = row["vertices"][0]
            row["vertices"] = [[x, y], [x + 1, y], [x + 2, y]]

        def bad_uv(rig):
            mesh(rig)["uvs"][1] = [1.01, 0.0]

        def unreferenced(rig):
            row = mesh(rig)
            row["vertices"].append(list(row["vertices"][0]))
            row["uvs"].append([0.5, 0.5])
            row["weights"].append([
                {"bone": "thigh.left", "weight": 1.0}
            ])

        for mutate in (
            out_of_range, bool_index, repeated_index,
            collinear, bad_uv, unreferenced,
        ):
            rig, target = exact_rig_and_target()
            mutate(rig)
            rebind(rig, target)
            with self.subTest(mutate=mutate.__name__):
                self.assert_rejected(rig, target)

    def test_resource_bound_is_fail_closed(self):
        rig, target = exact_rig_and_target()
        with patch(
            "autospine_workbench.body_sway_probe_geometry_context."
            "RIG_VERTEX_LIMIT", 2
        ):
            self.assert_rejected(rig, target)

    def test_production_modules_remain_small_and_claim_scoped(self):
        paths = (
            SRC / "autospine_workbench" / "body_sway_probe_geometry.py",
            SRC / "autospine_workbench" / "body_sway_probe_geometry_inputs.py",
        )
        for path in paths:
            with self.subTest(path=path.name):
                self.assertLess(len(path.read_text(encoding="utf-8").splitlines()),
                                300)
        rig, target = exact_rig_and_target()
        document = evaluate_body_sway_geometry_sample(
            rig, target, sample()
        ).to_dict()
        self.assertEqual(
            {"tick", "status", "fk_status", "bones", "attachments",
             "canvas_failures"},
            set(document),
        )
        self.assertFalse({"raster", "visual", "safety", "seam"} & set(document))


if __name__ == "__main__":
    unittest.main()
