"""Parity, rejection, and reuse tests for prepared deterministic LBS."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_skinning import (  # noqa: E402
    MeshSkinningError,
    QUANTIZATION_PER_PIXEL,
    skin_vertices_lbs,
)
from autospine_workbench.mesh_skinning_prepared import (  # noqa: E402
    PreparedSkinningBinding,
    PreparedSkinningPose,
    PreparedSkinningRig,
    evaluate_skinning_pose,
    prepare_skinning_binding,
    prepare_skinning_rig,
    skin_prepared_vertices,
)
from tests.test_mesh_skinning import blend, bone, chain, pure  # noqa: E402


class PreparedSkinningParityTests(unittest.TestCase):
    def setUp(self):
        self.rig_source = chain()
        self.vertices = (
            (0.0, 0.0),
            (10.0, 0.0),
            (15.25, 2.5),
            (1.0 / QUANTIZATION_PER_PIXEL / 2.0,
             -1.0 / QUANTIZATION_PER_PIXEL / 2.0),
        )
        self.weights = (
            pure("root"), pure("child"),
            blend("root", 0.25, "child"), pure("root"),
        )

    def prepared(self, pose):
        rig = prepare_skinning_rig(self.rig_source)
        binding = prepare_skinning_binding(
            rig, self.vertices, self.weights
        )
        return skin_prepared_vertices(
            evaluate_skinning_pose(rig, pose), binding
        )

    def test_direct_api_is_bit_exact_with_legacy_for_multiple_poses(self):
        poses = (
            {},
            {"root": 90.0},
            {"child": -43.5},
            {"root": 17.25, "child": -43.5},
            {"root": 360.0, "child": -720.0},
        )
        for pose in poses:
            with self.subTest(pose=pose):
                self.assertEqual(
                    skin_vertices_lbs(
                        self.rig_source, self.vertices, self.weights, pose
                    ),
                    self.prepared(pose),
                )
        self.assertEqual(
            (1.0 / QUANTIZATION_PER_PIXEL,
             -1.0 / QUANTIZATION_PER_PIXEL),
            self.prepared({})[-1],
        )

    def test_prepared_values_are_frozen_deterministic_detached_snapshots(self):
        before = deepcopy((self.rig_source, self.vertices, self.weights))
        rig = prepare_skinning_rig(self.rig_source)
        binding = prepare_skinning_binding(rig, self.vertices, self.weights)
        pose = evaluate_skinning_pose(rig, {"child": 45.0})
        first = skin_prepared_vertices(pose, binding)
        self.rig_source[0]["setup"]["x"] = 999.0
        self.assertEqual(first, skin_prepared_vertices(pose, binding))
        self.assertEqual(before[1:], (self.vertices, self.weights))
        self.assertEqual(("root", "child"), rig.bone_ids)
        self.assertEqual(len(self.vertices), binding.vertex_count)
        with self.assertRaises(FrozenInstanceError):
            pose._rig = rig  # type: ignore[misc]

    def test_reversed_bone_and_weight_order_remains_deterministic(self):
        pose_values = {"child": -43.5, "root": 17.25}
        first_rig = prepare_skinning_rig(self.rig_source)
        first = skin_prepared_vertices(
            evaluate_skinning_pose(first_rig, pose_values),
            prepare_skinning_binding(
                first_rig, ((12.125, 1.75),),
                (blend("root", 0.2, "child"),),
            ),
        )
        second_rig = prepare_skinning_rig(list(reversed(self.rig_source)))
        second = skin_prepared_vertices(
            evaluate_skinning_pose(second_rig, pose_values),
            prepare_skinning_binding(
                second_rig, ((12.125, 1.75),),
                (tuple(reversed(blend("root", 0.2, "child"))),),
            ),
        )
        self.assertEqual(first, second)

    def test_legacy_entry_point_delegates_every_prepared_stage_once(self):
        import autospine_workbench.mesh_skinning_prepared as prepared

        names = (
            "prepare_skinning_rig", "evaluate_skinning_pose",
            "prepare_skinning_binding", "skin_prepared_vertices",
        )
        patches = [
            patch.object(prepared, name, wraps=getattr(prepared, name))
            for name in names
        ]
        mocks = [item.start() for item in patches]
        try:
            actual = skin_vertices_lbs(
                self.rig_source, self.vertices, self.weights,
                {"root": 12.0},
            )
        finally:
            for item in reversed(patches):
                item.stop()
        self.assertEqual(self.prepared({"root": 12.0}), actual)
        self.assertTrue(all(mock.call_count == 1 for mock in mocks))


class PreparedSkinningRejectionTests(unittest.TestCase):
    def test_each_stage_rejects_malformed_inputs_with_public_error(self):
        invalid_rigs = (
            [],
            [bone("root"), bone("root")],
            [bone("child", parent="missing")],
            [bone("a", parent="b"), bone("b", parent="a")],
        )
        for source in invalid_rigs:
            with self.subTest(source=source), self.assertRaises(
                MeshSkinningError
            ):
                prepare_skinning_rig(source)

        rig = prepare_skinning_rig(chain())
        with self.assertRaisesRegex(MeshSkinningError, "unknown bone"):
            evaluate_skinning_pose(rig, {"missing": 1.0})
        with self.assertRaises(MeshSkinningError):
            evaluate_skinning_pose(rig, {"root": math.nan})
        with self.assertRaisesRegex(MeshSkinningError, "match"):
            prepare_skinning_binding(rig, ((0.0, 0.0),), ())
        with self.assertRaisesRegex(MeshSkinningError, "unknown bone"):
            prepare_skinning_binding(
                rig, ((0.0, 0.0),), (pure("missing"),)
            )

    def test_pose_and_binding_are_exact_type_and_rig_bound(self):
        first = prepare_skinning_rig(chain())
        second = prepare_skinning_rig(chain())
        pose = evaluate_skinning_pose(first, {})
        binding = prepare_skinning_binding(
            second, ((0.0, 0.0),), (pure("root"),)
        )
        with self.assertRaisesRegex(MeshSkinningError, "different rigs"):
            skin_prepared_vertices(pose, binding)
        for wrong_pose, wrong_binding in (
            (object(), binding),
            (pose, object()),
        ):
            with self.subTest(value=(wrong_pose, wrong_binding)), \
                    self.assertRaises(MeshSkinningError):
                skin_prepared_vertices(wrong_pose, wrong_binding)
        with self.assertRaises(MeshSkinningError):
            prepare_skinning_binding(
                object(), ((0.0, 0.0),), (pure("root"),)
            )
        with self.assertRaises(MeshSkinningError):
            evaluate_skinning_pose(object(), {})

    def test_preparation_is_reused_across_many_pose_evaluations(self):
        import autospine_workbench.mesh_skinning_prepared as prepared

        with patch.object(
            prepared, "bones", wraps=prepared.bones
        ) as normalize_bones, patch.object(
            prepared, "vertices", wraps=prepared.vertices
        ) as normalize_vertices, patch.object(
            prepared, "influences", wraps=prepared.influences
        ) as normalize_influences:
            rig = prepare_skinning_rig(chain())
            binding = prepare_skinning_binding(
                rig, ((15.0, 0.0),),
                (blend("root", 0.25, "child"),),
            )
            results = tuple(
                skin_prepared_vertices(
                    evaluate_skinning_pose(rig, {"child": float(angle)}),
                    binding,
                )
                for angle in range(-90, 91, 15)
            )
        self.assertEqual(13, len(results))
        self.assertEqual(1, normalize_bones.call_count)
        self.assertEqual(1, normalize_vertices.call_count)
        self.assertEqual(1, normalize_influences.call_count)

    def test_production_modules_are_below_hard_line_limit(self):
        for name in (
            "mesh_skinning.py", "mesh_skinning_prepared.py",
            "mesh_skinning_prepared_core.py",
        ):
            with self.subTest(name=name):
                self.assertLess(len((
                    SRC / "autospine_workbench" / name
                ).read_text(encoding="utf-8").splitlines()), 300)


if __name__ == "__main__":
    unittest.main()
