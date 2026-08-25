"""Fail-closed mesh topology and geometry invariant tests."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_topology import (  # noqa: E402
    MeshTopologyError,
    validate_mesh_topology,
)


VALID = {
    "vertices_xy": ((0, 0), (8, 0), (0, 8), (8, 8)),
    "uvs": ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)),
    "triangles": ((0, 1, 3), (0, 3, 2)),
    "width_px": 8,
    "height_px": 8,
}


def validate(**changes: object) -> None:
    values = dict(VALID)
    values.update(changes)
    validate_mesh_topology(**values)


class MeshTopologyTests(unittest.TestCase):
    def test_valid_clockwise_canvas_y_down_mesh_passes(self) -> None:
        self.assertIsNone(validate())

    def test_indices_must_be_distinct_integer_and_in_range(self) -> None:
        cases = (
            (((0, 0, 3),), "distinct"),
            (((0, 1, 4),), "range"),
            (((0, 1, True),), "integer"),
        )
        for triangles, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                MeshTopologyError, message
            ):
                validate(triangles=triangles)

    def test_zero_or_negative_canvas_winding_fails(self) -> None:
        with self.assertRaisesRegex(MeshTopologyError, "positive"):
            validate(triangles=((0, 3, 1), (0, 3, 2)))
        with self.assertRaisesRegex(MeshTopologyError, "positive"):
            validate(
                vertices_xy=((0, 0), (4, 0), (8, 0)),
                uvs=((0, 0), (0.5, 0), (1, 0)),
                triangles=((0, 1, 2),),
            )

    def test_duplicate_triangle_is_order_independent(self) -> None:
        with self.assertRaisesRegex(MeshTopologyError, "duplicate triangle"):
            validate(triangles=((0, 1, 3), (1, 3, 0)))

    def test_non_manifold_edge_fails(self) -> None:
        with self.assertRaisesRegex(MeshTopologyError, "more than two"):
            validate(
                vertices_xy=((0, 0), (8, 0), (4, 8), (4, 4), (4, 2)),
                uvs=((0, 0), (1, 0), (0.5, 1), (0.5, 0.5), (0.5, 0.25)),
                triangles=((0, 1, 2), (0, 1, 3), (0, 1, 4)),
            )

    def test_every_vertex_must_be_referenced(self) -> None:
        with self.assertRaisesRegex(MeshTopologyError, "unreferenced"):
            validate(triangles=((0, 1, 3),))

    def test_vertices_and_uvs_must_be_finite_and_bounded(self) -> None:
        cases = (
            (((0, 0), (math.nan, 0), (0, 8), (8, 8)), VALID["uvs"], "finite"),
            (((0, 0), (9, 0), (0, 8), (8, 8)), VALID["uvs"], "bounds"),
            (VALID["vertices_xy"], ((0, 0), (1.1, 0), (0, 1), (1, 1)), "bounds"),
            (VALID["vertices_xy"], ((0, 0), (math.inf, 0), (0, 1), (1, 1)), "finite"),
        )
        for vertices, uvs, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                MeshTopologyError, message
            ):
                validate(vertices_xy=vertices, uvs=uvs)

    def test_uv_count_extent_and_resource_limits_are_validated(self) -> None:
        with self.assertRaisesRegex(MeshTopologyError, "UV count"):
            validate(uvs=VALID["uvs"][:-1])
        with self.assertRaisesRegex(MeshTopologyError, "extent"):
            validate(width_px=0)
        with self.assertRaisesRegex(MeshTopologyError, "vertex limit"):
            validate(max_vertices=3)
        with self.assertRaisesRegex(MeshTopologyError, "triangle limit"):
            validate(max_triangles=1)


if __name__ == "__main__":
    unittest.main()
