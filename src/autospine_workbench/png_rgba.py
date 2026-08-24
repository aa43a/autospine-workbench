"""Dependency-free decoding boundary for non-interlaced 8-bit RGBA PNGs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
import zlib

try:
    from PIL import Image as _PillowImage
except ImportError:  # pragma: no cover - minimal runtime path
    _PillowImage = None


class RgbaPngError(ValueError):
    """Raised when a PNG cannot be decoded without changing representation."""


@dataclass(frozen=True, slots=True)
class RgbaImage:
    width: int
    height: int
    pixels: bytes


def read_rgba_png(path: Path) -> RgbaImage:
    path = Path(path)
    if _PillowImage is not None:
        try:
            with _PillowImage.open(path) as image:
                if image.format != "PNG" or image.mode != "RGBA":
                    raise RgbaPngError("Expected an 8-bit RGBA PNG")
                image.load()
                return RgbaImage(image.width, image.height, image.tobytes())
        except RgbaPngError:
            raise
        except (OSError, ValueError) as exc:
            raise RgbaPngError(f"Cannot decode PNG: {path.name}") from exc
    return _read_standard_png(path)


def _read_standard_png(path: Path) -> RgbaImage:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RgbaPngError(f"Cannot read PNG: {path.name}") from exc
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise RgbaPngError(f"Not a PNG: {path.name}")
    width, height, compressed = _read_chunks(data, path.name)
    try:
        filtered = zlib.decompress(compressed)
    except zlib.error as exc:
        raise RgbaPngError(f"Cannot decompress PNG: {path.name}") from exc
    stride = width * 4
    if len(filtered) != height * (stride + 1):
        raise RgbaPngError("PNG scanline size is inconsistent")
    return RgbaImage(width, height, _unfilter(filtered, width, height))


def _read_chunks(data: bytes, filename: str) -> tuple[int, int, bytes]:
    position = 8
    width = height = 0
    compressed = bytearray()
    while position + 12 <= len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        kind = data[position + 4 : position + 8]
        payload_start = position + 8
        payload_end = payload_start + length
        if payload_end + 4 > len(data):
            raise RgbaPngError(f"Truncated PNG chunk: {filename}")
        payload = data[payload_start:payload_end]
        if kind == b"IHDR":
            width, height = _parse_ihdr(payload)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
        position = payload_end + 4
    if width < 1 or height < 1 or not compressed:
        raise RgbaPngError(f"PNG has no image data: {filename}")
    return width, height, bytes(compressed)


def _parse_ihdr(payload: bytes) -> tuple[int, int]:
    if len(payload) != 13:
        raise RgbaPngError("Invalid PNG IHDR")
    width, height, depth, color_type, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", payload
    )
    if (depth, color_type, compression, filtering, interlace) != (8, 6, 0, 0, 0):
        raise RgbaPngError("Expected a non-interlaced 8-bit RGBA PNG")
    return width, height


def _unfilter(filtered: bytes, width: int, height: int) -> bytes:
    stride = width * 4
    output = bytearray(height * stride)
    source_offset = 0
    for row in range(height):
        filter_type = filtered[source_offset]
        source_offset += 1
        row_start = row * stride
        for column in range(stride):
            raw = filtered[source_offset + column]
            left = output[row_start + column - 4] if column >= 4 else 0
            above = output[row_start + column - stride] if row else 0
            diagonal = output[row_start + column - stride - 4] if row and column >= 4 else 0
            value = _unfilter_byte(filter_type, raw, left, above, diagonal)
            output[row_start + column] = value & 0xFF
        source_offset += stride
    return bytes(output)


def _unfilter_byte(kind: int, raw: int, left: int, above: int, diagonal: int) -> int:
    if kind == 0:
        return raw
    if kind == 1:
        return raw + left
    if kind == 2:
        return raw + above
    if kind == 3:
        return raw + ((left + above) // 2)
    if kind == 4:
        return raw + _paeth(left, above, diagonal)
    raise RgbaPngError(f"Unsupported PNG filter {kind}")


def _paeth(left: int, above: int, diagonal: int) -> int:
    prediction = left + above - diagonal
    distances = (
        (abs(prediction - left), left),
        (abs(prediction - above), above),
        (abs(prediction - diagonal), diagonal),
    )
    return min(distances, key=lambda item: item[0])[1]
