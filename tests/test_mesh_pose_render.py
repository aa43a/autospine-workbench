"""Deterministic single-attachment posed texture rendering tests."""

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

from autospine_workbench.mesh_pose_render import (  # noqa: E402
    MeshPoseRenderError,
    render_mesh_pose,
)
from autospine_workbench.png_rgba import RgbaImage  # noqa: E402


ROOT_BONE = "thigh.left"
CHILD_BONE = "calf.left"


def bone(
    bone_id: str,
    *,
    parent: str | None = None,
    x: float = 0.0,
    y: float = 0.0,
    length: float = 2.0,
) -> dict:
    return {
        "id": bone_id,
        "parent": parent,
        "setup": {
            "x": x,
            "y": y,
            "rotation_deg": 0.0,
            "scale_x": 1.0,
            "scale_y": 1.0,
            "length": length,
        },
    }


def chain() -> list[dict]:
    return [
        bone(ROOT_BONE, x=2.0, y=3.0),
        bone(CHILD_BONE, parent=ROOT_BONE, x=2.0),
    ]


def pure(bone_id: str) -> list[dict]:
    return [{"bone": bone_id, "weight": 1.0}]


def texture(width: int = 4, height: int = 2, alphas=None) -> RgbaImage:
    alphas = alphas or [255] * (width * height)
    pixels = bytearray()
    for index, alpha in enumerate(alphas):
        x, y = index % width, index // width
        pixels.extend(((20 + 40 * x) % 256, (30 + 50 * y) % 256, 40 + x + y, alpha))
    return RgbaImage(width, height, bytes(pixels))


def mesh(width: int = 4, height: int = 2, *, offset=(2, 2)) -> dict:
    vertices = [[0, 0], [width, 0], [0, height], [width, height]]
    return {
        "id": "leg-left",
        "type": "mesh",
        "canvas_offset_xy": list(offset),
        "vertices": vertices,
        "uvs": [[x / width, y / height] for x, y in vertices],
        "triangles": [0, 1, 3, 0, 3, 2],
        "weights": [
            pure(ROOT_BONE), pure(CHILD_BONE),
            pure(ROOT_BONE), pure(CHILD_BONE),
        ],
    }


def render(
    image=None,
    bones=None,
    attachment=None,
    pose=None,
    *,
    canvas=(8, 7),
) -> RgbaImage:
    return render_mesh_pose(
        image or texture(),
        bones or chain(),
        attachment or mesh(),
        pose or {},
        canvas_width=canvas[0],
        canvas_height=canvas[1],
    )


def pixel(image: RgbaImage, x: int, y: int) -> bytes:
    index = (y * image.width + x) * 4
    return image.pixels[index:index + 4]


class MeshPoseRenderTests(unittest.TestCase):
    def test_nonzero_offset_setup_reconstructs_perceptible_source_byte_exactly(self) -> None:
        image = texture()
        result = render(image=image)

        self.assertEqual((8, 7), (result.width, result.height))
        for y in range(image.height):
            for x in range(image.width):
                self.assertEqual(
                    image.pixels[(y * image.width + x) * 4:(y * image.width + x + 1) * 4],
                    pixel(result, x + 2, y + 2),
                )
        self.assertEqual(b"\0\0\0\0", pixel(result, 0, 0))

    def test_positive_and_negative_bends_produce_distinct_finite_canvases(self) -> None:
        setup = render()
        positive = render(pose={CHILD_BONE: 30.0})
        negative = render(pose={CHILD_BONE: -30.0})

        self.assertNotEqual(setup.pixels, positive.pixels)
        self.assertNotEqual(setup.pixels, negative.pixels)
        self.assertNotEqual(positive.pixels, negative.pixels)
        self.assertTrue(any(positive.pixels[3::4]))
        self.assertTrue(any(negative.pixels[3::4]))

    def test_transparent_texture_and_clear_canvas_background_are_preserved(self) -> None:
        image = texture(alphas=[255, 0, 7, 255, 255, 255, 0, 255])
        result = render(image=image)

        self.assertEqual(b"\0\0\0\0", pixel(result, 3, 2))
        self.assertEqual(image.pixels[8:12], pixel(result, 4, 2))
        self.assertEqual(b"\0\0\0\0", pixel(result, 0, 0))

    def test_shared_edge_triangle_bone_map_and_key_order_are_deterministic(self) -> None:
        image, bones, attachment = texture(), chain(), mesh()
        before = deepcopy((bones, attachment))
        first = render(image, bones, attachment, {ROOT_BONE: 0, CHILD_BONE: 30})
        changed = deepcopy(attachment)
        changed["triangles"] = [3, 2, 0, 1, 3, 0]
        changed["weights"] = [
            [{key: influence[key] for key in reversed(influence)} for influence in row]
            for row in changed["weights"]
        ]
        changed = {key: changed[key] for key in reversed(changed)}
        second = render(
            image,
            list(reversed(bones)),
            changed,
            {CHILD_BONE: 30, ROOT_BONE: 0},
        )

        self.assertEqual(first.pixels, second.pixels)
        self.assertEqual(before, (bones, attachment))

    def test_result_is_frozen_and_repeated_input_is_byte_stable(self) -> None:
        first, second = render(pose={CHILD_BONE: 25}), render(pose={CHILD_BONE: 25})

        self.assertEqual(first.pixels, second.pixels)
        with self.assertRaises(FrozenInstanceError):
            first.pixels = b""  # type: ignore[misc]


class MeshPoseRenderValidationTests(unittest.TestCase):
    def test_unknown_bones_nan_and_huge_numbers_use_domain_error(self) -> None:
        huge = 10 ** 10_000
        cases = []
        attachment = mesh()
        attachment["weights"][0] = pure("missing")
        cases.append((chain(), attachment, {}, "unknown bone"))
        cases.append((chain(), mesh(), {"missing": 2}, "unknown bone"))
        cases.append((chain(), mesh(), {CHILD_BONE: math.nan}, "finite"))
        attachment = mesh()
        attachment["vertices"][0][0] = huge
        cases.append((chain(), attachment, {}, "finite"))
        attachment = mesh()
        attachment["weights"][0][0]["weight"] = huge
        cases.append((chain(), attachment, {}, "invalid"))
        for bones, attachment, pose, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                MeshPoseRenderError, message
            ):
                render(bones=bones, attachment=attachment, pose=pose)

    def test_non_mesh_bad_uv_and_local_topology_fail_closed(self) -> None:
        mutations = (
            lambda item: item.update(type="region"),
            lambda item: item["uvs"][1].__setitem__(0, 0.75),
            lambda item: item.update(triangles=[0, 3, 1, 0, 3, 2]),
            lambda item: item.update(triangles=[0, 1, 9]),
            lambda item: item.update(triangles=[0, 1]),
        )
        for mutate in mutations:
            attachment = mesh()
            mutate(attachment)
            with self.subTest(mutation=mutate), self.assertRaises(
                MeshPoseRenderError
            ):
                render(attachment=attachment)

    def test_flip_degenerate_and_posed_vertices_outside_canvas_are_rejected(self) -> None:
        with self.assertRaisesRegex(MeshPoseRenderError, "deformation|degenerate|flipped"):
            render(pose={CHILD_BONE: 180})
        with self.assertRaisesRegex(MeshPoseRenderError, "outside"):
            render(pose={ROOT_BONE: 180})

    def test_setup_must_cover_every_source_pixel_with_alpha_at_least_eight(self) -> None:
        attachment = mesh(width=2, height=2)
        attachment["uvs"] = [[x / 4, y / 2] for x, y in attachment["vertices"]]

        with self.assertRaisesRegex(MeshPoseRenderError, "reconstruct"):
            render(attachment=attachment)

        low_alpha = texture(alphas=[255, 255, 0, 7, 255, 255, 0, 7])
        self.assertIsInstance(render(image=low_alpha, attachment=attachment), RgbaImage)

    def test_posed_geometric_overlap_with_different_texels_is_rejected(self) -> None:
        attachment = mesh()
        attachment["vertices"] = [
            [0, 0], [2, 0], [0, 2], [2, 2],
            [2, 0], [4, 0], [2, 2], [4, 2],
        ]
        attachment["uvs"] = [[x / 4, y / 2] for x, y in attachment["vertices"]]
        attachment["triangles"] = [
            0, 1, 3, 0, 3, 2,
            4, 5, 7, 4, 7, 6,
        ]
        attachment["weights"] = [
            *[pure(ROOT_BONE) for _ in range(4)],
            *[pure(CHILD_BONE) for _ in range(4)],
        ]

        with self.assertRaisesRegex(MeshPoseRenderError, "inconsistent RGBA"):
            render(attachment=attachment, pose={CHILD_BONE: 180})

    def test_canvas_source_offset_and_raster_budget_are_bounded(self) -> None:
        with self.assertRaisesRegex(MeshPoseRenderError, "canvas size"):
            render(canvas=(5000, 2))
        attachment = mesh(offset=(-1, 2))
        with self.assertRaisesRegex(MeshPoseRenderError, "outside"):
            render(attachment=attachment)

        large_source = texture(40, 40)
        large_mesh = mesh(40, 40, offset=(5, 5))
        large_mesh["weights"] = [pure(ROOT_BONE) for _ in range(4)]
        large_bones = [bone(ROOT_BONE, x=5, y=5, length=40)]
        with patch("autospine_workbench.mesh_pose_render._MAX_SAMPLE_FACTOR", 0):
            with self.assertRaisesRegex(MeshPoseRenderError, "budget"):
                render(
                    large_source,
                    large_bones,
                    large_mesh,
                    {},
                    canvas=(50, 50),
                )

    def test_overlapping_setup_triangles_with_inconsistent_texels_fail(self) -> None:
        attachment = mesh()
        attachment["vertices"] += deepcopy(attachment["vertices"])
        attachment["uvs"] += deepcopy(attachment["uvs"])
        attachment["triangles"] += [4, 5, 7, 4, 7, 6]
        attachment["weights"] += deepcopy(attachment["weights"])
        attachment["uvs"][4:] = [
            [1 - u, v] for u, v in attachment["uvs"][4:]
        ]

        with self.assertRaises(MeshPoseRenderError):
            render(attachment=attachment)


if __name__ == "__main__":
    unittest.main()
