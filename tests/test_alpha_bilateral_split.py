"""Lossless anatomical-side alpha partition tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
import math
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.alpha_bilateral_split import (  # noqa: E402
    AlphaBilateralSplitError,
    MAX_GUIDE_POINTS,
    split_alpha_bilateral,
)
from autospine_workbench.png_rgba import MAX_RGBA_PIXELS, RgbaImage  # noqa: E402


def rgba(rows: list[list[tuple[int, int, int, int]]]) -> RgbaImage:
    pixels = bytes(channel for row in rows for pixel in row for channel in pixel)
    return RgbaImage(len(rows[0]), len(rows), pixels)


def source_over(bottom: bytes, top: bytes) -> bytes:
    output = bytearray(len(bottom))
    for offset in range(0, len(bottom), 4):
        source_alpha = top[offset + 3]
        destination_alpha = bottom[offset + 3]
        alpha = source_alpha + (destination_alpha * (255 - source_alpha) + 127) // 255
        for channel in range(3):
            premultiplied = top[offset + channel] * source_alpha + (
                bottom[offset + channel] * destination_alpha * (255 - source_alpha) + 127
            ) // 255
            output[offset + channel] = (
                (premultiplied + alpha // 2) // alpha if alpha else 0
            )
        output[offset + 3] = alpha
    return bytes(output)


def normalized_over_transparent(image: RgbaImage) -> bytes:
    return source_over(bytes(len(image.pixels)), image.pixels)


class AlphaBilateralSplitTests(unittest.TestCase):
    def test_nearest_segments_use_canvas_offset_and_ties_choose_left(self) -> None:
        image = rgba(
            [[
                (10, 20, 30, 255),
                (40, 50, 60, 128),
                (70, 80, 90, 64),
                (100, 110, 120, 192),
                (130, 140, 150, 255),
            ]]
        )
        result = split_alpha_bilateral(
            image,
            canvas_offset_xy=(100, 200),
            left_polyline_xy=((100, 199), (100, 201)),
            right_polyline_xy=((104, 199), (104, 201)),
        )

        self.assertEqual((100, 200), result.canvas_offset_xy)
        self.assertEqual((3, 2, 1), (
            result.left_foreground_pixels,
            result.right_foreground_pixels,
            result.tie_foreground_pixels,
        ))
        self.assertEqual(image.pixels[:12], result.left.pixels[:12])
        self.assertEqual(bytes(8), result.right.pixels[:8])
        self.assertEqual(image.pixels[12:], result.right.pixels[12:])
        self.assertEqual(bytes(8), result.left.pixels[12:])
        self.assertEqual(
            "b859ceb0c98145f87c1e0296957378f23591433bc4eef03141394ee7bcc543b4",
            hashlib.sha256(result.left.pixels).hexdigest(),
        )
        self.assertEqual(
            "55ec6fedf767fee9f370927252e46b43ca4bbb35d3fc32e703dfe9dc75a42be9",
            hashlib.sha256(result.right.pixels).hexdigest(),
        )

    def test_outputs_are_disjoint_and_recompose_exactly_in_either_order(self) -> None:
        image = rgba(
            [
                [(9, 8, 7, 0), (20, 30, 40, 1), (50, 60, 70, 127)],
                [(80, 90, 100, 128), (110, 120, 130, 254), (140, 150, 160, 255)],
            ]
        )
        result = split_alpha_bilateral(
            image,
            canvas_offset_xy=(-5, 11),
            left_polyline_xy=((-5, 10), (-5, 13)),
            right_polyline_xy=((-3, 10), (-3, 13)),
        )
        expected = normalized_over_transparent(image)

        self.assertEqual(expected, source_over(result.left.pixels, result.right.pixels))
        self.assertEqual(expected, source_over(result.right.pixels, result.left.pixels))
        for offset in range(0, len(image.pixels), 4):
            source_alpha = image.pixels[offset + 3]
            left_alpha = result.left.pixels[offset + 3]
            right_alpha = result.right.pixels[offset + 3]
            if source_alpha:
                self.assertEqual(1, int(bool(left_alpha)) + int(bool(right_alpha)))
                chosen = result.left.pixels if left_alpha else result.right.pixels
                self.assertEqual(image.pixels[offset : offset + 4], chosen[offset : offset + 4])
            else:
                self.assertEqual(bytes(4), result.left.pixels[offset : offset + 4])
                self.assertEqual(bytes(4), result.right.pixels[offset : offset + 4])

    def test_raw_bytes_and_decoded_image_are_value_deterministic(self) -> None:
        image = rgba(
            [[(1, 2, 3, 255), (4, 5, 6, 200), (7, 8, 9, 100), (10, 11, 12, 255)]]
        )
        arguments = {
            "canvas_offset_xy": (0, 0),
            "left_polyline_xy": ((0.0, -1.0), (0.0, 1.0)),
            "right_polyline_xy": ((3.0, -1.0), (3.0, 1.0)),
        }
        decoded = split_alpha_bilateral(image, **arguments)
        raw = split_alpha_bilateral(
            memoryview(image.pixels), width=image.width, height=image.height, **arguments
        )

        self.assertEqual(decoded, raw)
        for _ in range(5):
            self.assertEqual(decoded, split_alpha_bilateral(image, **arguments))

    def test_polyline_distance_uses_segments_not_only_joint_vertices(self) -> None:
        image = rgba([[(1, 2, 3, 255), (0, 0, 0, 0), (4, 5, 6, 255)]])
        result = split_alpha_bilateral(
            image,
            canvas_offset_xy=(0, 0),
            left_polyline_xy=((0, 1), (10, 1)),
            right_polyline_xy=((2, -1), (2, -0.5)),
        )

        self.assertEqual(1, result.left_foreground_pixels)
        self.assertEqual(1, result.right_foreground_pixels)
        self.assertEqual(image.pixels[:4], result.left.pixels[:4])
        self.assertEqual(image.pixels[8:12], result.right.pixels[8:12])

    def test_squared_distance_tie_on_angled_segments_is_left_stable(self) -> None:
        image = rgba([[(1, 2, 3, 255), (4, 5, 6, 255), (7, 8, 9, 255)]])
        result = split_alpha_bilateral(
            image,
            canvas_offset_xy=(0, 0),
            left_polyline_xy=((-1, -1), (1, 1)),
            right_polyline_xy=((1, -1), (3, 1)),
        )

        self.assertEqual((2, 1, 1), (
            result.left_foreground_pixels,
            result.right_foreground_pixels,
            result.tie_foreground_pixels,
        ))

    def test_resource_caps_fail_before_decoding_or_unbounded_guide_consumption(self) -> None:
        visible = rgba([[(1, 2, 3, 255), (4, 5, 6, 255)]])
        base = {
            "canvas_offset_xy": (0, 0),
            "left_polyline_xy": ((0, -1), (0, 1)),
            "right_polyline_xy": ((1, -1), (1, 1)),
        }
        with self.assertRaisesRegex(AlphaBilateralSplitError, "exceeds"):
            split_alpha_bilateral(
                b"",
                width=MAX_RGBA_PIXELS + 1,
                height=1,
                **base,
            )
        with self.assertRaisesRegex(
            AlphaBilateralSplitError, f"exceeds {MAX_GUIDE_POINTS} points"
        ):
            split_alpha_bilateral(
                visible,
                **{
                    **base,
                    "left_polyline_xy": ((0, y) for y in range(MAX_GUIDE_POINTS + 1)),
                },
            )

    def test_empty_or_degenerate_inputs_fail_loud(self) -> None:
        visible = rgba([[(1, 2, 3, 255), (4, 5, 6, 255)]])
        base = {
            "canvas_offset_xy": (0, 0),
            "left_polyline_xy": ((0, -1), (0, 1)),
            "right_polyline_xy": ((1, -1), (1, 1)),
        }
        invalid_calls = (
            lambda: split_alpha_bilateral(bytes(4), width=None, height=1, **base),
            lambda: split_alpha_bilateral(bytes(3), width=1, height=1, **base),
            lambda: split_alpha_bilateral(visible, width=True, **base),
            lambda: split_alpha_bilateral(RgbaImage(1, 1, bytes(4)), **base),
            lambda: split_alpha_bilateral(visible, **{**base, "canvas_offset_xy": (0, 0.5)}),
            lambda: split_alpha_bilateral(visible, **{**base, "left_polyline_xy": ()}),
            lambda: split_alpha_bilateral(
                visible, **{**base, "left_polyline_xy": ((0, 0), (0, 0))}
            ),
            lambda: split_alpha_bilateral(
                visible, **{**base, "left_polyline_xy": ((0, 0), (math.nan, 1))}
            ),
            lambda: split_alpha_bilateral(
                visible,
                **{
                    **base,
                    "left_polyline_xy": ((0, -1), (0, 1)),
                    "right_polyline_xy": ((0, 1), (0, -1)),
                },
            ),
        )
        for call in invalid_calls:
            with self.subTest(call=call):
                with self.assertRaises(AlphaBilateralSplitError):
                    call()

    def test_one_sided_assignment_is_rejected_as_degenerate(self) -> None:
        image = rgba([[(1, 2, 3, 255), (4, 5, 6, 255)]])
        with self.assertRaisesRegex(AlphaBilateralSplitError, "one side empty"):
            split_alpha_bilateral(
                image,
                canvas_offset_xy=(0, 0),
                left_polyline_xy=((0, -1), (0, 1)),
                right_polyline_xy=((100, -1), (100, 1)),
            )


if __name__ == "__main__":
    unittest.main()
