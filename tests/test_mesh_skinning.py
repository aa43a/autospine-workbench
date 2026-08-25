"""Deterministic inverse-setup linear-blend skinning tests."""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_skinning import (  # noqa: E402
    MeshSkinningError,
    skin_vertices_lbs,
)


def bone(
    bone_id: str,
    *,
    parent: str | None = None,
    x: float = 0.0,
    y: float = 0.0,
    rotation: float = 0.0,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    length: float = 10.0,
) -> dict:
    return {
        "id": bone_id,
        "parent": parent,
        "setup": {
            "x": x,
            "y": y,
            "rotation_deg": rotation,
            "scale_x": scale_x,
            "scale_y": scale_y,
            "length": length,
        },
    }


def chain() -> list[dict]:
    return [bone("root"), bone("child", parent="root", x=10.0)]


def pure(bone_id: str) -> tuple[dict, ...]:
    return ({"bone": bone_id, "weight": 1.0},)


def blend(first: str, first_weight: float, second: str) -> tuple[dict, ...]:
    return (
        {"bone": first, "weight": first_weight},
        {"bone": second, "weight": 1.0 - first_weight},
    )


def signed_area_twice(points: tuple[tuple[float, float], ...]) -> float:
    total = 0.0
    for index, first in enumerate(points):
        second = points[(index + 1) % len(points)]
        total += first[0] * second[1] - first[1] * second[0]
    return total


class MeshSkinningMathTests(unittest.TestCase):
    def test_setup_pose_is_identity_and_uses_half_up_quantization(self) -> None:
        rigs = chain()
        rigs[0]["setup"].update(scale_x=2.0, scale_y=3.0)
        quantum = 1.0 / 4096.0
        vertices = ((0.0, 0.0), (10.0, 0.0), (15.25, 2.5), (quantum / 2, -quantum / 2))
        weights = (pure("root"), pure("child"), blend("root", 0.25, "child"), pure("root"))

        result = skin_vertices_lbs(rigs, vertices, weights, {})

        self.assertEqual(
            ((0.0, 0.0), (10.0, 0.0), (15.25, 2.5), (quantum, -quantum)),
            result,
        )

    def test_parent_only_rotation_is_rigid_for_all_descendant_weights(self) -> None:
        vertices = ((10.0, 0.0), (14.0, 0.0), (10.0, 3.0))
        weights = (pure("root"), pure("child"), blend("root", 0.25, "child"))

        posed = skin_vertices_lbs(chain(), vertices, weights, {"root": 90.0})

        self.assertEqual(((0.0, 10.0), (0.0, 14.0), (-3.0, 10.0)), posed)
        self.assertEqual(abs(signed_area_twice(vertices)), abs(signed_area_twice(posed)))

    def test_hierarchy_applies_parent_then_child_local_rotation(self) -> None:
        result = skin_vertices_lbs(
            chain(),
            ((5.0, 0.0), (10.0, 0.0), (20.0, 0.0)),
            (pure("root"), pure("child"), pure("child")),
            {"root": 90.0, "child": 90.0},
        )

        self.assertEqual(((0.0, 5.0), (0.0, 10.0), (-10.0, 10.0)), result)

    def test_two_bone_result_is_weighted_inverse_setup_deformation(self) -> None:
        result = skin_vertices_lbs(
            chain(),
            ((15.0, 0.0),),
            (blend("root", 0.25, "child"),),
            {"child": 90.0},
        )

        # Root leaves (15, 0) fixed; child rotates it to (10, 5) around (10, 0).
        self.assertEqual(((11.25, 3.75),), result)

    def test_spatially_mirrored_positive_scale_rig_is_supported(self) -> None:
        mirrored = [
            bone("root", x=10.0, rotation=180.0),
            bone("child", parent="root", x=10.0),
        ]

        result = skin_vertices_lbs(
            mirrored,
            ((5.0, 0.0), (-5.0, 0.0)),
            (pure("root"), pure("child")),
            {"root": 90.0},
        )

        self.assertEqual(((10.0, -5.0), (10.0, -15.0)), result)

    def test_output_is_deterministic_across_input_and_weight_order(self) -> None:
        rigs = chain()
        vertices = ((12.125, 1.75),)
        first = skin_vertices_lbs(
            rigs,
            vertices,
            (blend("root", 0.2, "child"),),
            {"root": 17.25, "child": -43.5},
        )
        reversed_weights = tuple(reversed(blend("root", 0.2, "child")))
        second = skin_vertices_lbs(
            list(reversed(rigs)),
            vertices,
            (reversed_weights,),
            {"child": -43.5, "root": 17.25},
        )

        self.assertEqual(first, second)
        self.assertEqual(first, skin_vertices_lbs(rigs, vertices, (blend("root", 0.2, "child"),), {"root": 17.25, "child": -43.5}))


class MeshSkinningValidationTests(unittest.TestCase):
    def test_invalid_hierarchies_fail_closed(self) -> None:
        cases = {
            "empty": [],
            "duplicate": [bone("root"), bone("root")],
            "missing parent": [bone("child", parent="missing")],
            "cycle": [bone("a", parent="b"), bone("b", parent="a")],
        }
        for label, rigs in cases.items():
            with self.subTest(label=label), self.assertRaises(MeshSkinningError):
                skin_vertices_lbs(rigs, ((0.0, 0.0),), (pure(rigs[0]["id"] if rigs else "root"),), {})

    def test_zero_length_and_non_positive_scales_fail_closed(self) -> None:
        for field, value in (("length", 0.0), ("scale_x", 0.0), ("scale_y", -1.0)):
            rig = bone("root")
            rig["setup"][field] = value
            with self.subTest(field=field), self.assertRaises(MeshSkinningError):
                skin_vertices_lbs([rig], ((0.0, 0.0),), (pure("root"),), {})

    def test_non_finite_setup_pose_vertex_and_weight_are_rejected(self) -> None:
        cases = []
        for field, value in (("x", math.nan), ("rotation_deg", math.inf)):
            rig = bone("root")
            rig["setup"][field] = value
            cases.append(([rig], ((0.0, 0.0),), (pure("root"),), {}))
        cases.extend(
            (
                ([bone("root")], ((math.nan, 0.0),), (pure("root"),), {}),
                ([bone("root")], ((0.0, 0.0),), (({"bone": "root", "weight": math.inf},),), {}),
                ([bone("root")], ((0.0, 0.0),), (pure("root"),), {"root": math.nan}),
            )
        )
        for case in cases:
            with self.subTest(case=case), self.assertRaises(MeshSkinningError):
                skin_vertices_lbs(*case)

    def test_unknown_pose_and_weight_bones_are_rejected(self) -> None:
        rig = [bone("root")]
        with self.assertRaisesRegex(MeshSkinningError, "unknown bone"):
            skin_vertices_lbs(rig, ((0.0, 0.0),), (pure("missing"),), {})
        with self.assertRaisesRegex(MeshSkinningError, "unknown bone"):
            skin_vertices_lbs(rig, ((0.0, 0.0),), (pure("root"),), {"missing": 1.0})

    def test_weight_shape_positivity_uniqueness_and_sum_are_enforced(self) -> None:
        rig = chain()
        invalid = (
            (),
            (pure("root")[0], pure("child")[0], {"bone": "root", "weight": 0.1}),
            ({"bone": "root", "weight": 0.0},),
            ({"bone": "root", "weight": -0.1}, {"bone": "child", "weight": 1.1}),
            ({"bone": "root", "weight": 0.4}, {"bone": "child", "weight": 0.5}),
            ({"bone": "root", "weight": 0.5}, {"bone": "root", "weight": 0.5}),
        )
        for influences in invalid:
            with self.subTest(influences=influences), self.assertRaises(MeshSkinningError):
                skin_vertices_lbs(rig, ((0.0, 0.0),), (influences,), {})

    def test_vertex_weight_counts_and_shapes_must_match(self) -> None:
        rig = [bone("root")]
        with self.assertRaisesRegex(MeshSkinningError, "non-empty"):
            skin_vertices_lbs(rig, (), (), {})
        with self.assertRaisesRegex(MeshSkinningError, "match"):
            skin_vertices_lbs(rig, ((0.0, 0.0),), (), {})
        with self.assertRaisesRegex(MeshSkinningError, "two coordinates"):
            skin_vertices_lbs(rig, ((0.0,),), (pure("root"),), {})

    def test_all_bone_references_use_safe_portable_rigir_ids(self) -> None:
        invalid_ids = ("unsafe id", "/root", "a" * 129)
        for invalid in invalid_ids:
            with self.subTest(source="bone", invalid=invalid), self.assertRaisesRegex(
                MeshSkinningError, "safe RigIR"
            ):
                skin_vertices_lbs([bone(invalid)], ((0.0, 0.0),), (pure(invalid),), {})
            with self.subTest(source="parent", invalid=invalid), self.assertRaisesRegex(
                MeshSkinningError, "safe RigIR"
            ):
                skin_vertices_lbs(
                    [bone("root"), bone("child", parent=invalid)],
                    ((0.0, 0.0),),
                    (pure("root"),),
                    {},
                )
            with self.subTest(source="pose", invalid=invalid), self.assertRaisesRegex(
                MeshSkinningError, "safe RigIR"
            ):
                skin_vertices_lbs(
                    [bone("root")], ((0.0, 0.0),), (pure("root"),), {invalid: 1.0}
                )
            with self.subTest(source="weight", invalid=invalid), self.assertRaisesRegex(
                MeshSkinningError, "safe RigIR"
            ):
                skin_vertices_lbs(
                    [bone("root")], ((0.0, 0.0),), (pure(invalid),), {}
                )


if __name__ == "__main__":
    unittest.main()
