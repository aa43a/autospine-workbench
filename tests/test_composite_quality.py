"""Representation-aware composite comparison tests."""

from __future__ import annotations

import binascii
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKBENCH_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.composite_quality import compare_composite_pngs  # noqa: E402


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)


def write_rgba(path: Path, rows: list[list[tuple[int, int, int, int]]]) -> None:
    height, width = len(rows), len(rows[0])
    raw = b"".join(b"\x00" + bytes(channel for pixel in row for channel in pixel) for row in rows)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b""))


class CompositeQualityTests(unittest.TestCase):
    def test_transparent_rgb_vs_flattened_black_is_not_a_visual_failure(self) -> None:
        transparent_white = (255, 255, 255, 0)
        opaque_black = (0, 0, 0, 255)
        opaque_red = (220, 20, 30, 255)
        with tempfile.TemporaryDirectory() as directory:
            composite = Path(directory) / "composite.png"
            embedded = Path(directory) / "embedded.png"
            write_rgba(composite, [[transparent_white, opaque_red], [transparent_white, transparent_white]])
            write_rgba(embedded, [[opaque_black, opaque_red], [opaque_black, opaque_black]])
            metrics = compare_composite_pngs(composite, embedded)
        self.assertGreater(metrics.raw_rgba_mae, 100)
        self.assertEqual("flattened_reference", metrics.alpha_representation)
        self.assertEqual((0, 0, 0), metrics.inferred_background_rgb)
        self.assertEqual(0, metrics.background_matched_rgb_mae)
        self.assertEqual("passed", metrics.status)

    def test_visible_color_difference_remains_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            composite = Path(directory) / "composite.png"
            embedded = Path(directory) / "embedded.png"
            write_rgba(composite, [[(255, 0, 0, 255)]])
            write_rgba(embedded, [[(0, 0, 255, 255)]])
            metrics = compare_composite_pngs(composite, embedded)
        self.assertGreater(metrics.background_matched_rgb_mae, 5)
        self.assertEqual("comparable", metrics.alpha_representation)
        self.assertEqual("manual_required", metrics.status)


if __name__ == "__main__":
    unittest.main()
