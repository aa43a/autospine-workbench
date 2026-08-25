"""Deterministic alpha-supported regular-grid mesh tests."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.alpha_grid_mesh import (  # noqa: E402
    AlphaGridMeshError,
    MAX_ATTACHMENT_TRIANGLES,
    MAX_ATTACHMENT_VERTICES,
    build_alpha_grid_mesh,
)
from autospine_workbench.png_rgba import RgbaImage  # noqa: E402


def rgba_image(alpha_rows: list[list[int]]) -> RgbaImage:
    height = len(alpha_rows)
    width = len(alpha_rows[0])
    pixels = bytes(
        channel
        for row in alpha_rows
        for alpha in row
        for channel in (20, 40, 60, alpha)
    )
    return RgbaImage(width, height, pixels)


def solid(width: int, height: int, alpha: int = 255) -> RgbaImage:
    return rgba_image([[alpha] * width for _ in range(height)])


class AlphaGridMeshGeometryTests(unittest.TestCase):
    def test_solid_16_by_16_step_8_has_shared_row_major_vertices(self) -> None:
        mesh = build_alpha_grid_mesh(solid(16, 16), grid_step_px=8)

        self.assertEqual(9, len(mesh.vertices_xy))
        self.assertEqual(8, len(mesh.triangles))
        self.assertEqual(
            ((0, 0), (8, 0), (16, 0), (0, 8), (8, 8), (16, 8),
             (0, 16), (8, 16), (16, 16)),
            mesh.vertices_xy,
        )
        self.assertEqual((0.0, 0.0), mesh.uvs[0])
        self.assertEqual((1.0, 1.0), mesh.uvs[-1])
        self.assertEqual((0, 1, 4), mesh.triangles[0])
        self.assertEqual((0, 4, 3), mesh.triangles[1])
        self.assertEqual((1, 2, 4), mesh.triangles[2])
        self.assertEqual((2, 5, 4), mesh.triangles[3])

    def test_remainder_edges_end_exactly_at_source_extent(self) -> None:
        mesh = build_alpha_grid_mesh(solid(17, 17), grid_step_px=8)

        self.assertEqual(16, len(mesh.vertices_xy))
        self.assertEqual(18, len(mesh.triangles))
        self.assertIn((17, 17), mesh.vertices_xy)
        index = mesh.vertices_xy.index((17, 17))
        self.assertEqual((1.0, 1.0), mesh.uvs[index])
        self.assertEqual((16, 16, 17, 17), mesh.active_cells_xyxy[-1])

    def test_threshold_is_inclusive_and_below_threshold_is_empty(self) -> None:
        mesh = build_alpha_grid_mesh(solid(8, 8, alpha=8), grid_step_px=8)
        self.assertEqual(64, mesh.foreground_pixels)
        with self.assertRaisesRegex(AlphaGridMeshError, "no foreground"):
            build_alpha_grid_mesh(solid(8, 8, alpha=7), grid_step_px=8)

    def test_every_foreground_pixel_is_covered_despite_a_grid_hole(self) -> None:
        rows = [[255] * 24 for _ in range(24)]
        for y in range(8, 16):
            for x in range(8, 16):
                rows[y][x] = 0
        mesh = build_alpha_grid_mesh(rgba_image(rows), grid_step_px=8)

        self.assertNotIn((8, 8, 16, 16), mesh.active_cells_xyxy)
        for y, row in enumerate(rows):
            for x, alpha in enumerate(row):
                if alpha >= 8:
                    self.assertTrue(
                        any(left <= x < right and top <= y < bottom
                            for left, top, right, bottom in mesh.active_cells_xyxy)
                    )

    def test_same_inputs_produce_byte_for_byte_equal_value(self) -> None:
        image = solid(17, 17)
        first = build_alpha_grid_mesh(image, grid_step_px=6)
        second = build_alpha_grid_mesh(image, grid_step_px=6)
        self.assertEqual(first, second)


class AlphaGridMeshEvidenceTests(unittest.TestCase):
    def test_attachment_limits_are_the_pinned_profile_values(self) -> None:
        self.assertEqual(4096, MAX_ATTACHMENT_VERTICES)
        self.assertEqual(8192, MAX_ATTACHMENT_TRIANGLES)

    def test_empty_and_less_than_64_foreground_pixels_fail_closed(self) -> None:
        with self.assertRaisesRegex(AlphaGridMeshError, "no foreground"):
            build_alpha_grid_mesh(solid(8, 8, alpha=0), grid_step_px=8)
        rows = [[0] * 8 for _ in range(8)]
        for index in range(63):
            rows[index // 8][index % 8] = 255
        with self.assertRaisesRegex(AlphaGridMeshError, "at least 64"):
            build_alpha_grid_mesh(rgba_image(rows), grid_step_px=8)

    def test_two_significant_islands_fail_closed(self) -> None:
        rows = [[0] * 24 for _ in range(8)]
        for y in range(8):
            for x in range(8):
                rows[y][x] = rows[y][x + 16] = 255
        with self.assertRaisesRegex(AlphaGridMeshError, "exactly one significant"):
            build_alpha_grid_mesh(rgba_image(rows), grid_step_px=8)

    def test_diagonally_touching_blocks_are_one_8_connected_component(self) -> None:
        rows = [[0] * 16 for _ in range(16)]
        for y in range(8):
            for x in range(8):
                rows[y][x] = 255
                rows[y + 8][x + 8] = 255
        mesh = build_alpha_grid_mesh(rgba_image(rows), grid_step_px=8)
        self.assertEqual((128,), mesh.component_areas)

    def test_significant_component_must_cover_99_percent(self) -> None:
        rows = [[255] * 32 for _ in range(32)]
        rows.extend([[0] * 32 for _ in range(2)])
        for x in range(15):
            rows[33][x] = 255
        with self.assertRaisesRegex(AlphaGridMeshError, "99 percent"):
            build_alpha_grid_mesh(rgba_image(rows), grid_step_px=8)

    def test_sub_significant_noise_is_allowed_only_with_99_percent_coverage(self) -> None:
        rows = [[255] * 50 for _ in range(40)]
        rows.extend([[0] * 50 for _ in range(2)])
        for x in range(15):
            rows[41][x] = 255
        mesh = build_alpha_grid_mesh(rgba_image(rows), grid_step_px=8)
        self.assertEqual((2000, 15), mesh.component_areas)

    def test_attachment_resource_limits_fail_before_returning_a_mesh(self) -> None:
        with patch("autospine_workbench.alpha_grid_mesh.MAX_ATTACHMENT_VERTICES", 8):
            with self.assertRaisesRegex(AlphaGridMeshError, "vertex limit"):
                build_alpha_grid_mesh(solid(16, 16), grid_step_px=8)
        with patch("autospine_workbench.alpha_grid_mesh.MAX_ATTACHMENT_TRIANGLES", 7):
            with self.assertRaisesRegex(AlphaGridMeshError, "triangle limit"):
                build_alpha_grid_mesh(solid(16, 16), grid_step_px=8)

    def test_invalid_image_threshold_and_step_fail_closed(self) -> None:
        invalid = RgbaImage(8, 8, b"short")
        cases = (
            (invalid, 8, 8, "RGBA image"),
            (solid(8, 8), True, 8, "grid step"),
            (solid(8, 8), 8, 0, "alpha threshold"),
        )
        for image, step, threshold, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                AlphaGridMeshError, message
            ):
                build_alpha_grid_mesh(
                    image, grid_step_px=step, alpha_threshold=threshold
                )


if __name__ == "__main__":
    unittest.main()
