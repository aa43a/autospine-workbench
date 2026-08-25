"""Deterministic, fail-closed P3 mesh weight heatmap tests."""

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

from autospine_workbench.mesh_weight_heatmap import (  # noqa: E402
    BALANCED_RGB,
    DISTAL_RGB,
    MeshWeightHeatmapError,
    PROXIMAL_RGB,
    render_mesh_weight_heatmap,
)
from autospine_workbench.png_rgba import RgbaImage  # noqa: E402


PROXIMAL = "thigh.left"
DISTAL = "calf.left"


def source(width: int, height: int, alphas: list[int] | None = None) -> RgbaImage:
    alphas = alphas or [255] * (width * height)
    pixels = bytearray()
    for alpha in alphas:
        pixels.extend((11, 22, 33, alpha))
    return RgbaImage(width, height, bytes(pixels))


def influences(distal_weight: float) -> list[dict]:
    if distal_weight == 0:
        return [{"bone": PROXIMAL, "weight": 1.0}]
    if distal_weight == 1:
        return [{"bone": DISTAL, "weight": 1.0}]
    return [
        {"bone": PROXIMAL, "weight": 1.0 - distal_weight},
        {"bone": DISTAL, "weight": distal_weight},
    ]


def quad(
    width: int,
    height: int,
    weights: tuple[float, float, float, float],
    *,
    image_width: int | None = None,
    image_height: int | None = None,
) -> dict:
    image_width = image_width or width
    image_height = image_height or height
    vertices = [[0, 0], [width, 0], [0, height], [width, height]]
    return {
        "id": "leg-left",
        "type": "mesh",
        "canvas_offset_xy": [25, 40],
        "vertices": vertices,
        "uvs": [[x / image_width, y / image_height] for x, y in vertices],
        "triangles": [0, 1, 3, 0, 3, 2],
        "weights": [influences(value) for value in weights],
    }


def render(image: RgbaImage, attachment: dict) -> RgbaImage:
    return render_mesh_weight_heatmap(
        image,
        attachment,
        proximal_bone_id=PROXIMAL,
        distal_bone_id=DISTAL,
    )


def rgba_rows(image: RgbaImage) -> list[tuple[int, int, int, int]]:
    return [
        tuple(image.pixels[index:index + 4])
        for index in range(0, len(image.pixels), 4)
    ]


class MeshWeightHeatmapColorTests(unittest.TestCase):
    def test_pure_and_balanced_weights_use_the_three_fixed_colors(self) -> None:
        for weight, color in (
            (0.0, PROXIMAL_RGB),
            (0.5, BALANCED_RGB),
            (1.0, DISTAL_RGB),
        ):
            attachment = quad(1, 1, (weight,) * 4)
            with self.subTest(weight=weight):
                self.assertEqual([(*color, 255)], rgba_rows(render(source(1, 1), attachment)))

    def test_barycentric_blend_is_piecewise_linear_and_rounds_half_up(self) -> None:
        attachment = quad(2, 1, (0.0, 1.0, 0.0, 1.0))

        self.assertEqual(
            [(0x67, 0x5C, 0xF1, 255), (0xCC, 0x4D, 0x9E, 255)],
            rgba_rows(render(source(2, 1), attachment)),
        )

    def test_source_alpha_is_byte_exact_and_alpha_zero_rgb_is_black(self) -> None:
        image = source(2, 1, [0, 7])
        result = render(image, quad(2, 1, (0.0, 1.0, 0.0, 1.0)))

        self.assertEqual([(0, 0, 0, 0), (0xCC, 0x4D, 0x9E, 7)], rgba_rows(result))
        self.assertEqual(image.pixels[3::4], result.pixels[3::4])

    def test_shared_diagonal_has_no_crack_and_triangle_order_is_irrelevant(self) -> None:
        image = source(2, 2)
        attachment = quad(2, 2, (0.0, 1.0, 0.0, 1.0))
        first = render(image, attachment)
        changed = deepcopy(attachment)
        changed["triangles"] = [3, 2, 0, 1, 3, 0]
        changed["weights"] = [
            [{key: item[key] for key in reversed(item)} for item in row]
            for row in changed["weights"]
        ]
        changed = {key: changed[key] for key in reversed(changed)}
        second = render(image, changed)

        self.assertEqual(first.pixels, second.pixels)
        self.assertTrue(all(alpha == 255 for *_, alpha in rgba_rows(first)))

    def test_offset_is_validated_but_does_not_change_local_rendering(self) -> None:
        image = source(2, 1)
        attachment = quad(2, 1, (0.0, 1.0, 0.0, 1.0))
        first = render(image, attachment)
        attachment["canvas_offset_xy"] = [-999.5, 1234.25]

        self.assertEqual(first, render(image, attachment))

    def test_l_shaped_fixture_covers_real_alpha_shape_without_filling_hole(self) -> None:
        vertices = [
            [0, 0], [1, 0], [0, 1], [1, 1],
            [0, 2], [1, 2], [2, 1], [2, 2],
        ]
        attachment = {
            "type": "mesh",
            "canvas_offset_xy": [7, 9],
            "vertices": vertices,
            "uvs": [[x / 2, y / 2] for x, y in vertices],
            "triangles": [
                0, 1, 3, 0, 3, 2,
                2, 3, 4, 3, 5, 4,
                3, 6, 7, 3, 7, 5,
            ],
            "weights": [influences(y / 2) for _x, y in vertices],
        }

        result = render(source(2, 2, [255, 0, 255, 255]), attachment)

        self.assertEqual(
            [
                (0x67, 0x5C, 0xF1, 255), (0, 0, 0, 0),
                (0xCC, 0x4D, 0x9E, 255), (0xCC, 0x4D, 0x9E, 255),
            ],
            rgba_rows(result),
        )

    def test_result_is_immutable_repeatable_and_inputs_are_unchanged(self) -> None:
        image = source(2, 1)
        attachment = quad(2, 1, (0.0, 1.0, 0.0, 1.0))
        before = deepcopy(attachment)
        first, second = render(image, attachment), render(image, attachment)

        self.assertEqual(first.pixels, second.pixels)
        self.assertEqual(before, attachment)
        with self.assertRaises(FrozenInstanceError):
            first.pixels = b""  # type: ignore[misc]


class MeshWeightHeatmapTamperTests(unittest.TestCase):
    def test_non_mesh_bad_image_size_uv_and_offset_fail_closed(self) -> None:
        base = quad(2, 1, (0.0, 1.0, 0.0, 1.0))
        cases = []
        changed = deepcopy(base)
        changed["type"] = "region"
        cases.append((source(2, 1), changed, "must be a mesh"))
        cases.append((RgbaImage(2, 1, b"bad"), base, "image is invalid"))
        cases.append((source(3, 1), base, "dimensions"))
        changed = deepcopy(base)
        changed["uvs"][1][0] = 0.75
        cases.append((source(2, 1), changed, "dimensions"))
        changed = deepcopy(base)
        changed["canvas_offset_xy"] = [math.nan, 0]
        cases.append((source(2, 1), changed, "finite"))
        for image, attachment, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                MeshWeightHeatmapError, message
            ):
                render(image, attachment)

    def test_flat_triangle_contract_and_topology_tampering_are_rejected(self) -> None:
        mutations = (
            lambda item: item.update(triangles=[0, 1]),
            lambda item: item.update(triangles=[0, 1, 9]),
            lambda item: item.update(triangles=[0, 3, 1, 0, 3, 2]),
            lambda item: item.update(triangles=[0, 1, 3, 0, 1, 3]),
            lambda item: item["vertices"].append([1, 0.5]),
        )
        for mutate in mutations:
            attachment = quad(2, 1, (0.0, 1.0, 0.0, 1.0))
            mutate(attachment)
            with self.subTest(mutation=mutate), self.assertRaises(
                MeshWeightHeatmapError
            ):
                render(source(2, 1), attachment)

    def test_weight_cardinality_bones_fields_finiteness_and_sums_are_strict(self) -> None:
        def change_weight(attachment, row):
            attachment["weights"][0] = row

        mutations = (
            lambda item: item["weights"].pop(),
            lambda item: change_weight(item, [{"bone": PROXIMAL, "weight": math.nan}]),
            lambda item: change_weight(item, [{"bone": "spine", "weight": 1.0}]),
            lambda item: change_weight(item, [{"bone": PROXIMAL, "weight": 0.0}]),
            lambda item: change_weight(item, [
                {"bone": PROXIMAL, "weight": 0.4},
                {"bone": DISTAL, "weight": 0.5},
            ]),
            lambda item: change_weight(item, [
                {"bone": PROXIMAL, "weight": 0.5},
                {"bone": PROXIMAL, "weight": 0.5},
            ]),
            lambda item: change_weight(item, [
                {"bone": PROXIMAL, "weight": 1.0, "extra": True}
            ]),
        )
        for mutate in mutations:
            attachment = quad(2, 1, (0.0, 1.0, 0.0, 1.0))
            mutate(attachment)
            with self.subTest(mutation=mutate), self.assertRaises(
                MeshWeightHeatmapError
            ):
                render(source(2, 1), attachment)

    def test_huge_integer_vertex_and_weight_use_the_domain_error(self) -> None:
        huge = 10 ** 10_000
        mutations = (
            lambda item: item["vertices"][0].__setitem__(0, huge),
            lambda item: item["weights"][0][0].__setitem__("weight", huge),
        )
        for mutate in mutations:
            attachment = quad(2, 1, (0.0, 1.0, 0.0, 1.0))
            mutate(attachment)
            with self.subTest(mutation=mutate), self.assertRaisesRegex(
                MeshWeightHeatmapError, "finite"
            ):
                render(source(2, 1), attachment)

    def test_perceptible_uncovered_source_pixel_fails_but_alpha_seven_is_allowed(self) -> None:
        attachment = quad(
            1, 1, (0.0, 1.0, 0.0, 1.0), image_width=2, image_height=1
        )
        with self.assertRaisesRegex(MeshWeightHeatmapError, "uncovered"):
            render(source(2, 1, [255, 255]), attachment)

        self.assertEqual(
            (0, 0, 0, 7),
            rgba_rows(render(source(2, 1, [255, 7]), attachment))[1],
        )

    def test_geometric_overlap_with_inconsistent_weights_is_rejected(self) -> None:
        attachment = quad(2, 2, (0.0, 0.0, 0.0, 0.0))
        attachment["vertices"] += deepcopy(attachment["vertices"])
        attachment["uvs"] += deepcopy(attachment["uvs"])
        attachment["triangles"] += [4, 5, 7, 4, 7, 6]
        attachment["weights"] += [influences(1.0) for _ in range(4)]

        with self.assertRaisesRegex(MeshWeightHeatmapError, "inconsistent"):
            render(source(2, 2), attachment)

    def test_invalid_or_identical_bone_ids_are_rejected(self) -> None:
        image = source(1, 1)
        attachment = quad(1, 1, (0.0,) * 4)
        for proximal, distal in (("../bad", DISTAL), (PROXIMAL, PROXIMAL)):
            with self.subTest(proximal=proximal, distal=distal), self.assertRaises(
                MeshWeightHeatmapError
            ):
                render_mesh_weight_heatmap(
                    image,
                    attachment,
                    proximal_bone_id=proximal,
                    distal_bone_id=distal,
                )


if __name__ == "__main__":
    unittest.main()
