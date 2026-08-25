"""Dependency-free RGBA PNG read/write contract tests."""

from __future__ import annotations

import binascii
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.png_rgba import (  # noqa: E402
    MAX_RGBA_DIMENSION,
    MAX_RGBA_PIXELS,
    RgbaImage,
    RgbaPngError,
    read_rgba_png,
    write_rgba_png,
)


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


class RgbaPngWriteTests(unittest.TestCase):
    def test_canonical_writer_round_trips_every_rgba_byte(self) -> None:
        image = RgbaImage(
            2,
            2,
            bytes(
                [
                    255, 0, 0, 255,
                    10, 20, 30, 0,
                    40, 50, 60, 127,
                    70, 80, 90, 1,
                ]
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roundtrip.png"
            write_rgba_png(path, image)
            restored = read_rgba_png(path)
        self.assertEqual(image, restored)

    def test_same_pixels_always_encode_to_the_same_bytes(self) -> None:
        image = RgbaImage(1, 2, bytes([1, 2, 3, 4, 5, 6, 7, 8]))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.png"
            second = root / "second.png"
            write_rgba_png(first, image)
            write_rgba_png(second, image)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(
                hashlib.sha256(first.read_bytes()).hexdigest(),
                hashlib.sha256(second.read_bytes()).hexdigest(),
            )

    def test_canonical_stored_deflate_bytes_match_golden_vector(self) -> None:
        image = RgbaImage(1, 2, bytes([1, 2, 3, 4, 5, 6, 7, 8]))
        expected = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000208060000009981b627"
            "00000015494441547801010a00f5ff00010203040005060708008c0025797d6bf1"
            "0000000049454e44ae426082"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "golden.png"
            write_rgba_png(path, image)
            encoded = path.read_bytes()

        self.assertEqual(expected, encoded)
        self.assertEqual(
            "ce1f829a8078a9e5b403e2c3d8d93614c1165e8a50a49c2fc7c0687f3066844a",
            hashlib.sha256(encoded).hexdigest(),
        )

    def test_stored_deflate_block_boundary_round_trips(self) -> None:
        width, height = 256, 64
        pixels = bytes(index % 251 for index in range(width * height * 4))
        image = RgbaImage(width, height, pixels)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "multi-block.png"
            write_rgba_png(path, image)
            restored = read_rgba_png(path)
        self.assertEqual(image, restored)

    def test_decoded_pixel_cap_applies_before_raster_allocation(self) -> None:
        header = struct.pack(">IIBBBBB", MAX_RGBA_PIXELS + 1, 1, 8, 6, 0, 0, 0)
        encoded = (
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", header)
            + png_chunk(b"IDAT", b"x\x01\x03\x00\x00\x00\x00\x01")
            + png_chunk(b"IEND", b"")
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.png"
            path.write_bytes(encoded)
            with self.assertRaisesRegex(RgbaPngError, "exceed"):
                read_rgba_png(path)

    def test_per_axis_cap_rejects_one_pixel_wide_pathological_png(self) -> None:
        header = struct.pack(
            ">IIBBBBB", 1, MAX_RGBA_DIMENSION + 1, 8, 6, 0, 0, 0
        )
        encoded = (
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", header)
            + png_chunk(b"IDAT", b"x\x01\x03\x00\x00\x00\x00\x01")
            + png_chunk(b"IEND", b"")
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "too-tall.png"
            path.write_bytes(encoded)
            with self.assertRaisesRegex(RgbaPngError, "per axis"):
                read_rgba_png(path)

    def test_writer_rejects_invalid_dimensions_and_buffer_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.png"
            for image in (
                RgbaImage(0, 1, b""),
                RgbaImage(1, 1, b"\0" * 3),
                RgbaImage(MAX_RGBA_PIXELS + 1, 1, b""),
            ):
                with self.subTest(image=image), self.assertRaises(RgbaPngError):
                    write_rgba_png(path, image)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
