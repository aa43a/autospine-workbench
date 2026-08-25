"""Single-snapshot in-memory RGBA PNG decoding tests."""

from __future__ import annotations

import binascii
from copy import deepcopy
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import autospine_workbench.png_rgba as png_rgba  # noqa: E402
from autospine_workbench.png_rgba import (  # noqa: E402
    RgbaImage,
    RgbaPngError,
    decode_rgba_png,
    encode_rgba_png,
    read_rgba_png,
)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _rgb_png() -> bytes:
    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(bytes((0, 10, 20, 30))))
        + _chunk(b"IEND", b"")
    )


def _truncated_idat(encoded: bytes) -> bytes:
    position = 8 + 12 + 13
    length = struct.unpack(">I", encoded[position:position + 4])[0]
    return encoded[:position + 8 + max(1, length // 2)]


class RgbaPngByteDecodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.image = RgbaImage(
            2, 2,
            bytes((255, 0, 0, 255, 10, 20, 30, 0,
                   40, 50, 60, 127, 70, 80, 90, 1)),
        )
        self.encoded = encode_rgba_png(self.image)

    def test_canonical_bytes_match_pillow_and_dependency_free_paths(self) -> None:
        ordinary = decode_rgba_png(self.encoded, source_name="canonical.png")
        with patch.object(png_rgba, "_PillowImage", None):
            fallback = decode_rgba_png(self.encoded, source_name="canonical.png")
        self.assertEqual(self.image, ordinary)
        self.assertEqual(ordinary, fallback)

    def test_truncated_idat_fails_in_both_decoders(self) -> None:
        truncated = _truncated_idat(self.encoded)
        with self.assertRaises(RgbaPngError):
            decode_rgba_png(truncated, source_name="truncated.png")
        with patch.object(png_rgba, "_PillowImage", None):
            with self.assertRaisesRegex(RgbaPngError, "Truncated PNG chunk"):
                decode_rgba_png(truncated, source_name="truncated.png")

    def test_wrong_mode_and_signature_are_rejected_in_both_decoders(self) -> None:
        for value in (_rgb_png(), b"not a png"):
            with self.subTest(value=value[:8]):
                with self.assertRaises(RgbaPngError):
                    decode_rgba_png(value, source_name="invalid.png")
                with patch.object(png_rgba, "_PillowImage", None):
                    with self.assertRaises(RgbaPngError):
                        decode_rgba_png(value, source_name="invalid.png")

    def test_source_name_is_used_without_mutating_input(self) -> None:
        original = deepcopy(self.encoded)
        with self.assertRaisesRegex(RgbaPngError, "memory-fixture.png"):
            decode_rgba_png(b"invalid", source_name="memory-fixture.png")
        self.assertEqual(original, self.encoded)
        self.assertIsInstance(decode_rgba_png(self.encoded), RgbaImage)

    def test_path_reader_reads_once_then_decodes_that_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "single-read.png"
            path.write_bytes(self.encoded)
            original_read = Path.read_bytes
            calls: list[Path] = []

            def tracked_read(candidate: Path) -> bytes:
                calls.append(candidate)
                return original_read(candidate)

            with patch.object(Path, "read_bytes", tracked_read):
                restored = read_rgba_png(path)
        self.assertEqual(self.image, restored)
        self.assertEqual([path], calls)

    def test_byte_and_source_name_types_fail_closed(self) -> None:
        for value in (bytearray(self.encoded), memoryview(self.encoded), "png"):
            with self.subTest(value=type(value)), self.assertRaisesRegex(
                RgbaPngError, "must be bytes"
            ):
                decode_rgba_png(value)  # type: ignore[arg-type]
        with self.assertRaisesRegex(RgbaPngError, "source name"):
            decode_rgba_png(self.encoded, source_name="")


if __name__ == "__main__":
    unittest.main()
