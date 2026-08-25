"""Dependency-free decoding boundary for non-interlaced 8-bit RGBA PNGs."""

from __future__ import annotations

import binascii
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


MAX_RGBA_DIMENSION = 4096
"""Largest accepted width or height, preventing pathological scanline shapes."""

MAX_RGBA_PIXELS = MAX_RGBA_DIMENSION * MAX_RGBA_DIMENSION
"""Largest accepted decoded raster (4096 x 4096 pixels)."""

MAX_RGBA_BYTES = MAX_RGBA_PIXELS * 4
"""64 MiB decoded RGBA ceiling shared by decode and split boundaries."""


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
                _rgba_byte_count(image.width, image.height)
                image.load()
                pixels = image.tobytes()
                if len(pixels) != image.width * image.height * 4:
                    raise RgbaPngError("PNG decoded to an inconsistent RGBA buffer")
                return RgbaImage(image.width, image.height, pixels)
        except RgbaPngError:
            raise
        except (OSError, ValueError) as exc:
            raise RgbaPngError(f"Cannot decode PNG: {path.name}") from exc
    return _read_standard_png(path)


def write_rgba_png(path: Path, image: RgbaImage) -> None:
    """Write one fully specified, cross-zlib-stable RGBA PNG.

    Scanlines always use PNG filter 0.  The zlib stream uses a 32 KiB window,
    no preset dictionary, stored DEFLATE blocks of at most 65535 bytes, and an
    RFC 1950 Adler-32 trailer.  No runtime compressor choices affect bytes.
    """

    try:
        Path(path).write_bytes(encode_rgba_png(image))
    except OSError as exc:
        raise RgbaPngError(f"Cannot write PNG: {Path(path).name}") from exc


def encode_rgba_png(image: RgbaImage) -> bytes:
    """Return the canonical bytes used by :func:`write_rgba_png`."""

    expected = _rgba_byte_count(image.width, image.height)
    if not isinstance(image.pixels, bytes) or len(image.pixels) != expected:
        raise RgbaPngError("RGBA pixel buffer has the wrong size")
    stride = image.width * 4
    scanlines = bytearray()
    for row in range(image.height):
        scanlines.append(0)
        start = row * stride
        scanlines.extend(image.pixels[start : start + stride])
    header = struct.pack(">IIBBBBB", image.width, image.height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", _stored_zlib(bytes(scanlines)))
        + _chunk(b"IEND", b"")
    )


def _chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(kind)
    checksum = binascii.crc32(payload, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def _stored_zlib(payload: bytes) -> bytes:
    """Return a canonical RFC 1950 stream containing stored DEFLATE blocks."""

    blocks = bytearray(b"\x78\x01")
    for start in range(0, len(payload), 65_535):
        block = payload[start : start + 65_535]
        final = start + len(block) == len(payload)
        blocks.append(1 if final else 0)
        length = len(block)
        blocks.extend(struct.pack("<HH", length, length ^ 0xFFFF))
        blocks.extend(block)
    blocks.extend(struct.pack(">I", _adler32(payload)))
    return bytes(blocks)


def _adler32(payload: bytes) -> int:
    first, second = 1, 0
    # 5552 is the largest chunk that keeps the pre-modulo sums in 32 bits.
    for start in range(0, len(payload), 5_552):
        for value in payload[start : start + 5_552]:
            first += value
            second += first
        first %= 65_521
        second %= 65_521
    return (second << 16) | first


def _read_standard_png(path: Path) -> RgbaImage:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise RgbaPngError(f"Cannot read PNG: {path.name}") from exc
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise RgbaPngError(f"Not a PNG: {path.name}")
    width, height, compressed = _read_chunks(data, path.name)
    expected_filtered = height * (width * 4 + 1)
    try:
        decoder = zlib.decompressobj()
        filtered = decoder.decompress(compressed, expected_filtered + 1)
    except zlib.error as exc:
        raise RgbaPngError(f"Cannot decompress PNG: {path.name}") from exc
    if (
        len(filtered) > expected_filtered
        or not decoder.eof
        or decoder.unconsumed_tail
        or decoder.unused_data
    ):
        raise RgbaPngError("PNG decompressed data exceeds its declared dimensions")
    stride = width * 4
    if len(filtered) != expected_filtered:
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
    _rgba_byte_count(width, height)
    return width, height


def _rgba_byte_count(width: object, height: object) -> int:
    if (
        not isinstance(width, int)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or isinstance(height, bool)
        or width < 1
        or height < 1
    ):
        raise RgbaPngError("Image dimensions must be positive integers")
    if width > MAX_RGBA_DIMENSION or height > MAX_RGBA_DIMENSION:
        raise RgbaPngError(
            f"Image dimensions exceed {MAX_RGBA_DIMENSION} pixels per axis"
        )
    pixels = width * height
    if pixels > MAX_RGBA_PIXELS:
        raise RgbaPngError(
            f"Decoded image exceeds {MAX_RGBA_PIXELS} pixels ({MAX_RGBA_BYTES} RGBA bytes)"
        )
    return pixels * 4


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
