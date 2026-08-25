from __future__ import annotations

import binascii
import hashlib
from pathlib import Path
import struct
import sys
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from autospine_workbench.png_rgba import RgbaImage, decode_rgba_png, encode_rgba_png
from autospine_workbench.spine42_atlas import (
    ATLAS_MAX_SIZE,
    ATLAS_PADDING,
    Spine42AtlasError,
    build_spine42_atlas,
)


def _png(width: int, height: int, pixels: bytes) -> bytes:
    return encode_rgba_png(RgbaImage(width, height, pixels))


def _chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def _rgb_png() -> bytes:
    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(b"\x00\x10\x20\x30"))
        + _chunk(b"IEND", b"")
    )


def _crop(image: RgbaImage, x: int, y: int, width: int, height: int) -> bytes:
    rows = []
    for row in range(height):
        start = ((y + row) * image.width + x) * 4
        rows.append(image.pixels[start : start + width * 4])
    return b"".join(rows)


class Spine42AtlasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.head_pixels = bytes(
            (
                255, 0, 0, 255,
                0, 255, 0, 128,
                0, 0, 255, 64,
                10, 20, 30, 0,
            )
        )
        self.arm_pixels = bytes((1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12))
        self.sources = [
            ("head", _png(2, 2, self.head_pixels)),
            ("arm.left", _png(1, 3, self.arm_pixels)),
        ]

    def test_reconstructs_every_source_pixel_without_rotation_or_trim(self) -> None:
        result = build_spine42_atlas(self.sources, page_name="hero.png")
        atlas = decode_rgba_png(result.png_bytes)
        by_name = {item.name: item for item in result.placements}

        head = by_name["head"]
        arm = by_name["arm.left"]
        self.assertEqual(
            self.head_pixels,
            _crop(atlas, head.x, head.y, head.width, head.height),
        )
        self.assertEqual(
            self.arm_pixels,
            _crop(atlas, arm.x, arm.y, arm.width, arm.height),
        )
        self.assertEqual(ATLAS_PADDING, result.padding)
        self.assertLessEqual(result.width, ATLAS_MAX_SIZE)
        self.assertLessEqual(result.height, ATLAS_MAX_SIZE)

        occupied = {
            (x, y)
            for item in result.placements
            for y in range(item.y, item.y + item.height)
            for x in range(item.x, item.x + item.width)
        }
        for y in range(atlas.height):
            for x in range(atlas.width):
                if (x, y) not in occupied:
                    self.assertEqual(b"\x00\x00\x00\x00", _crop(atlas, x, y, 1, 1))

    def test_same_inputs_have_stable_content_hashes(self) -> None:
        first = build_spine42_atlas(self.sources, page_name="hero.png")
        second = build_spine42_atlas(self.sources, page_name="hero.png")

        self.assertEqual(first, second)
        self.assertEqual(
            "7f18e8cb26e315af005a7cc7b74cdfb764f72918fe9e42ffbaed73a668cd4689",
            hashlib.sha256(first.png_bytes).hexdigest(),
        )
        self.assertEqual(
            "365ab5d0ae2a9a1ec661e281ceb7583a9cde0e2d00974546a4fab9d1a8907ed7",
            hashlib.sha256(first.atlas_bytes).hexdigest(),
        )
        self.assertEqual(first.png_bytes, second.png_bytes)
        self.assertEqual(first.atlas_bytes, second.atlas_bytes)

    def test_input_order_does_not_affect_any_output(self) -> None:
        forward = build_spine42_atlas(self.sources, page_name="hero.png")
        reverse = build_spine42_atlas(list(reversed(self.sources)), page_name="hero.png")

        self.assertEqual(forward, reverse)
        self.assertEqual(["arm.left", "head"], [item.name for item in forward.placements])

    def test_equal_png_content_is_not_inferred_as_an_attachment_alias(self) -> None:
        png = self.sources[0][1]
        result = build_spine42_atlas([("head", png), ("head.shadow", png)])

        self.assertEqual(2, len(result.placements))
        self.assertNotEqual(
            (result.placements[0].x, result.placements[0].y),
            (result.placements[1].x, result.placements[1].y),
        )
        self.assertEqual(
            result.placements[0].source_sha256,
            result.placements[1].source_sha256,
        )

    def test_emits_spine42_single_page_legacy_fields_and_metadata(self) -> None:
        result = build_spine42_atlas(dict(self.sources), page_name="hero.png")

        self.assertTrue(result.atlas_text.startswith(
            f"hero.png\nsize: {result.width},{result.height}\n"
            "format: RGBA8888\nfilter: Linear,Linear\nrepeat: none\n"
        ))
        self.assertTrue(result.atlas_text.endswith("  index: -1\n"))
        for item in result.placements:
            block = (
                f"{item.name}\n  rotate: false\n  xy: {item.x}, {item.y}\n"
                f"  size: {item.width}, {item.height}\n"
                f"  orig: {item.width}, {item.height}\n"
                "  offset: 0, 0\n  index: -1\n"
            )
            self.assertIn(block, result.atlas_text)
        metadata = result.placement_metadata()
        self.assertEqual((0, 0), tuple(metadata[0]["offset"]))
        self.assertFalse(metadata[0]["rotate"])
        self.assertEqual(-1, metadata[0]["index"])
        self.assertEqual(result.atlas_text.encode("utf-8"), result.atlas_bytes)

    def test_rejects_duplicate_case_alias_and_dangerous_names(self) -> None:
        png = self.sources[0][1]
        rejected = (
            [("head", png), ("head", png)],
            [("head", png), ("HEAD", png)],
            [("../head", png)],
            [("head/arm", png)],
            [(" head", png)],
        )
        for sources in rejected:
            with self.subTest(sources=[name for name, _ in sources]):
                with self.assertRaises(Spine42AtlasError):
                    build_spine42_atlas(sources)

    def test_rejects_non_rgba_invalid_and_mutable_png_inputs(self) -> None:
        rejected = (_rgb_png(), b"not a png", bytearray(self.sources[0][1]))
        for data in rejected:
            with self.subTest(kind=type(data).__name__):
                with self.assertRaises(Spine42AtlasError):
                    build_spine42_atlas([("head", data)])  # type: ignore[list-item]

    def test_rejects_region_or_page_overflow(self) -> None:
        too_wide = _png(ATLAS_MAX_SIZE - 3, 1, bytes((0, 0, 0, 0)) * (ATLAS_MAX_SIZE - 3))
        with self.assertRaisesRegex(Spine42AtlasError, "cannot fit"):
            build_spine42_atlas([("wide", too_wide)])

        with self.assertRaises(Spine42AtlasError):
            build_spine42_atlas(self.sources, page_name="../hero.png")


if __name__ == "__main__":
    unittest.main()
