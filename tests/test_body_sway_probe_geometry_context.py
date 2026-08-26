"""Prepared body-sway context parity, reuse, and isolation tests."""

from __future__ import annotations

from dataclasses import replace
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
    evaluate_prepared_body_sway_geometry_sample,
)
from autospine_workbench.body_sway_probe_geometry_context import (  # noqa: E402
    prepare_body_sway_geometry_context,
)
from autospine_workbench.body_sway_probe_profile import (  # noqa: E402
    MAX_AREA_RATIO,
    MAX_EDGE_STRETCH,
    MIN_AREA_RATIO,
)
from autospine_workbench.mesh_deformation_metrics import (  # noqa: E402
    measure_deformation,
)
from tests.body_sway_probe_geometry_helpers import (  # noqa: E402
    attachment,
    exact_rig_and_target,
    sample,
)


class PreparedBodySwayGeometryTests(unittest.TestCase):
    def test_public_and_prepared_paths_are_exact_for_pose_grid(self):
        rig, target = exact_rig_and_target()
        context = prepare_body_sway_geometry_context(rig, target)
        poses = [
            sample(tick=0),
            sample(tick=1, overlay={"pelvis-spine": 10.0}),
            sample(tick=2, base={"calf.left": 45.0}),
            sample(
                tick=3, base={"calf.left": 90.0},
                overlay={"neck-head": -3.25}, translation=(3.5, -4.0),
            ),
            sample(tick=4, translation=(500.0, 0.0)),
        ]
        for pose in poses:
            with self.subTest(tick=pose.tick):
                self.assertEqual(
                    evaluate_body_sway_geometry_sample(rig, target, pose),
                    evaluate_prepared_body_sway_geometry_sample(context, pose),
                )

    def test_prepared_deformation_is_exactly_the_public_metric(self):
        rig, target = exact_rig_and_target(failing_mesh=True)
        context = prepare_body_sway_geometry_context(rig, target)
        for angle in (0.0, 45.0, 90.0, 180.0):
            result = evaluate_prepared_body_sway_geometry_sample(
                context, sample(base={"calf.left": angle})
            )
            mesh = attachment(result, "leg-left")
            prepared = next(
                row for row in context.attachments
                if row.attachment_id == "leg-left"
            )
            expected = measure_deformation(
                mesh.setup_vertices_xy, mesh.posed_vertices_xy,
                prepared.deformation.triangles,
                min_area_ratio=MIN_AREA_RATIO,
                max_area_ratio=MAX_AREA_RATIO,
                max_edge_stretch=MAX_EDGE_STRETCH,
            )
            self.assertEqual(expected, mesh.deformation)

    def test_static_work_runs_once_and_pose_compiles_once_per_tick(self):
        rig, target = exact_rig_and_target()
        import autospine_workbench.body_sway_probe_geometry_context as context_module
        import autospine_workbench.body_sway_probe_geometry as geometry_module

        with patch.object(
            context_module, "normalize_body_sway_static_geometry_input",
            wraps=context_module.normalize_body_sway_static_geometry_input,
        ) as admit, patch.object(
            context_module, "normalize_probe_input",
            wraps=context_module.normalize_probe_input,
        ) as normalize_mesh, patch.object(
            context_module, "prepare_body_sway_deformation",
            wraps=context_module.prepare_body_sway_deformation,
        ) as setup_check:
            context = prepare_body_sway_geometry_context(rig, target)
            self.assertEqual(1, admit.call_count)
            self.assertEqual(1, normalize_mesh.call_count)
            self.assertEqual(1, setup_check.call_count)
            with patch.object(
                geometry_module, "evaluate_skinning_pose",
                wraps=geometry_module.evaluate_skinning_pose,
            ) as pose_compiler:
                for tick in range(5):
                    evaluate_prepared_body_sway_geometry_sample(
                        context, sample(tick=tick)
                    )
                self.assertEqual(5, pose_compiler.call_count)
            self.assertEqual(1, admit.call_count)
            self.assertEqual(1, normalize_mesh.call_count)
            self.assertEqual(1, setup_check.call_count)

    def test_context_is_detached_and_evaluation_has_no_state_growth(self):
        rig, target = exact_rig_and_target()
        context = prepare_body_sway_geometry_context(rig, target)
        before = repr(context)
        expected = evaluate_prepared_body_sway_geometry_sample(
            context, sample(overlay={"neck-head": -2.0})
        )
        rig["bones"][0]["setup"]["x"] += 123.0
        target.clear()
        for _index in range(3):
            self.assertEqual(expected, evaluate_prepared_body_sway_geometry_sample(
                context, sample(overlay={"neck-head": -2.0})
            ))
        self.assertEqual(before, repr(context))

    def test_forged_context_and_static_cross_wire_fail_closed(self):
        rig, target = exact_rig_and_target()
        with self.assertRaisesRegex(
            BodySwayProbeGeometryError, "Prepared.*context",
        ):
            evaluate_prepared_body_sway_geometry_sample(
                object(), sample()  # type: ignore[arg-type]
            )
        context = prepare_body_sway_geometry_context(rig, target)
        forged = replace(context, attachments=(object(),))
        with self.assertRaisesRegex(
            BodySwayProbeGeometryError, "attachment is invalid",
        ):
            evaluate_prepared_body_sway_geometry_sample(forged, sample())
        target["source"]["p3"]["rig_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            BodySwayProbeGeometryError, "binding differs",
        ):
            prepare_body_sway_geometry_context(rig, target)

    def test_production_modules_remain_bounded(self):
        for name in (
            "body_sway_probe_geometry.py",
            "body_sway_probe_geometry_inputs.py",
            "body_sway_probe_geometry_context.py",
            "body_sway_probe_deformation.py",
            "mesh_skinning.py",
            "mesh_skinning_prepared.py",
            "mesh_skinning_prepared_core.py",
        ):
            lines = (SRC / "autospine_workbench" / name).read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertLess(len(lines), 300, name)


if __name__ == "__main__":
    unittest.main()
