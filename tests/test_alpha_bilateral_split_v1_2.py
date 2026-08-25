"""Component-cohesive bilateral alpha split v1.2 tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.alpha_bilateral_split import (  # noqa: E402
    AlphaBilateralSplitError,
    split_alpha_bilateral,
    split_alpha_bilateral_v1_1,
)
from autospine_workbench.png_rgba import RgbaImage  # noqa: E402


def mask_image(width: int, height: int, spans: list[tuple[int, int, int]]) -> RgbaImage:
    pixels = bytearray(width * height * 4)
    for y, start, end in spans:
        for x in range(start, end + 1):
            offset = (y * width + x) * 4
            pixels[offset : offset + 4] = bytes((x + 1, y + 2, 99, 255))
    return RgbaImage(width, height, bytes(pixels))


def opaque_side(image: RgbaImage, x: int, y: int) -> bool:
    return image.pixels[(y * image.width + x) * 4 + 3] > 0


def set_alpha(image: RgbaImage, x: int, y: int, alpha: int) -> RgbaImage:
    pixels = bytearray(image.pixels)
    offset = (y * image.width + x) * 4
    pixels[offset : offset + 4] = bytes((x + 1, y + 2, 99, alpha))
    return RgbaImage(image.width, image.height, bytes(pixels))


class ComponentCohesiveSplitTests(unittest.TestCase):
    def test_clear_two_component_pair_keeps_each_component_whole(self) -> None:
        image = mask_image(
            14,
            4,
            [(y, 1, 5) for y in range(4)] + [(y, 9, 13) for y in range(4)],
        )
        arguments = {
            "canvas_offset_xy": (0, 0),
            "left_polyline_xy": ((1, -1), (1, 5)),
            "right_polyline_xy": ((8, -1), (8, 5)),
        }

        result = split_alpha_bilateral(image, **arguments)
        legacy = split_alpha_bilateral_v1_1(image, **arguments)

        self.assertEqual((20, 20), (
            result.left_foreground_pixels, result.right_foreground_pixels
        ))
        self.assertTrue(all(opaque_side(result.left, x, y) for y in range(4) for x in range(1, 6)))
        self.assertTrue(all(opaque_side(result.right, x, y) for y in range(4) for x in range(9, 14)))
        self.assertTrue(opaque_side(legacy.right, 5, 0), "v1.1 proves the old cut")
        self.assertTrue(opaque_side(result.left, 5, 0), "v1.2 keeps that core intact")

        first_hashes = (
            hashlib.sha256(result.left.pixels).hexdigest(),
            hashlib.sha256(result.right.pixels).hexdigest(),
        )
        for _ in range(5):
            repeated = split_alpha_bilateral(image, **arguments)
            self.assertEqual(result, repeated)
            self.assertEqual(first_hashes, (
                hashlib.sha256(repeated.left.pixels).hexdigest(),
                hashlib.sha256(repeated.right.pixels).hexdigest(),
            ))

    def test_verified_single_fused_core_replays_v1_1_byte_exactly(self) -> None:
        image = mask_image(10, 4, [(y, 1, 8) for y in range(4)])
        arguments = {
            "canvas_offset_xy": (0, 0),
            "left_polyline_xy": ((1, -1), (1, 4)),
            "right_polyline_xy": ((8, -1), (8, 4)),
        }

        current = split_alpha_bilateral(image, **arguments)
        legacy = split_alpha_bilateral_v1_1(image, **arguments)

        self.assertEqual(legacy.left, current.left)
        self.assertEqual(legacy.right, current.right)
        self.assertEqual(
            (
                legacy.left_foreground_pixels,
                legacy.right_foreground_pixels,
                legacy.tie_foreground_pixels,
            ),
            (
                current.left_foreground_pixels,
                current.right_foreground_pixels,
                current.tie_foreground_pixels,
            ),
        )
        self.assertEqual(
            "verified_fused_pixel_fallback", current.component_analysis["mode"]
        )
        self.assertGreater(current.left_foreground_pixels, 0)
        self.assertGreater(current.right_foreground_pixels, 0)

    def test_minor_perceptible_component_crossing_midline_stays_whole(self) -> None:
        image = mask_image(
            50,
            20,
            [(y, 0, 19) for y in range(20)]
            + [(y, 30, 49) for y in range(20)]
            + [(10, 23, 25)],
        )

        result = split_alpha_bilateral(
            image,
            canvas_offset_xy=(0, 0),
            left_polyline_xy=((0, -1), (0, 21)),
            right_polyline_xy=((49, -1), (49, 21)),
        )

        minor_sides = {
            "left" if opaque_side(result.left, x, 10) else "right"
            for x in range(23, 26)
        }
        self.assertEqual({"left"}, minor_sides)
        self.assertEqual(803, result.foreground_pixels)

    def test_two_component_bijection_tie_fails_closed(self) -> None:
        image = mask_image(
            12,
            9,
            [(y, 4, 7) for y in range(4)] + [(y, 4, 7) for y in range(5, 9)],
        )
        with self.assertRaisesRegex(AlphaBilateralSplitError, "ambiguous"):
            split_alpha_bilateral(
                image,
                canvas_offset_xy=(0, 0),
                left_polyline_xy=((0, -1), (0, 10)),
                right_polyline_xy=((11, -1), (11, 10)),
            )

    def test_alpha_1_7_15_residuals_follow_nearest_assigned_core(self) -> None:
        image = mask_image(
            12,
            4,
            [(y, 0, 3) for y in range(4)] + [(y, 8, 11) for y in range(4)],
        )
        image = set_alpha(image, 3, 3, 16)
        for x, y, alpha in ((4, 0, 1), (7, 1, 7), (6, 2, 15)):
            image = set_alpha(image, x, y, alpha)

        result = split_alpha_bilateral(
            image,
            canvas_offset_xy=(0, 0),
            left_polyline_xy=((0, -1), (0, 5)),
            right_polyline_xy=((11, -1), (11, 5)),
        )

        self.assertTrue(opaque_side(result.left, 4, 0))
        self.assertTrue(opaque_side(result.left, 3, 3), "alpha=16 belongs to the core")
        self.assertTrue(opaque_side(result.right, 7, 1))
        self.assertTrue(opaque_side(result.right, 6, 2))
        self.assertEqual(35, result.foreground_pixels)

    def test_three_significant_components_fail_closed(self) -> None:
        image = mask_image(
            16,
            4,
            [(y, 0, 3) for y in range(4)]
            + [(y, 6, 9) for y in range(4)]
            + [(y, 12, 15) for y in range(4)],
        )
        with self.assertRaisesRegex(AlphaBilateralSplitError, "one fused core or two"):
            split_alpha_bilateral(
                image,
                canvas_offset_xy=(0, 0),
                left_polyline_xy=((0, -1), (0, 5)),
                right_polyline_xy=((15, -1), (15, 5)),
            )

    def test_unreliable_single_core_is_not_silently_treated_as_fused(self) -> None:
        image = mask_image(24, 4, [(y, 1, 5) for y in range(4)])
        with self.assertRaisesRegex(AlphaBilateralSplitError, "both distal guides"):
            split_alpha_bilateral(
                image,
                canvas_offset_xy=(0, 0),
                left_polyline_xy=((1, -1), (1, 4)),
                right_polyline_xy=((22, -1), (22, 4)),
            )


if __name__ == "__main__":
    unittest.main()
