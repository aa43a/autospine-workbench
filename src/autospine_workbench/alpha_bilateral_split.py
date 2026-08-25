"""Deterministic lossless partitioning of RGBA alpha by anatomical side."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import math
from typing import Any

from .png_rgba import MAX_RGBA_BYTES, MAX_RGBA_PIXELS, RgbaImage


class AlphaBilateralSplitError(ValueError):
    """Raised when an RGBA layer cannot be split without guessing."""


MAX_GUIDE_POINTS = 8
"""Maximum anchors per anatomical-side guide at authoring and replay."""


@dataclass(frozen=True, slots=True)
class AlphaBilateralSplit:
    """Two disjoint, full-size RGBA images sharing one canvas offset."""

    left: RgbaImage
    right: RgbaImage
    canvas_offset_xy: tuple[int, int]
    left_foreground_pixels: int
    right_foreground_pixels: int
    tie_foreground_pixels: int

    @property
    def foreground_pixels(self) -> int:
        return self.left_foreground_pixels + self.right_foreground_pixels


@dataclass(frozen=True, slots=True)
class _Segment:
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    delta_x: float
    delta_y: float
    length_squared: float


def split_alpha_bilateral(
    image: RgbaImage | bytes | bytearray | memoryview,
    *,
    canvas_offset_xy: Sequence[int],
    left_polyline_xy: Iterable[Sequence[float]],
    right_polyline_xy: Iterable[Sequence[float]],
    width: int | None = None,
    height: int | None = None,
) -> AlphaBilateralSplit:
    """Assign every non-transparent pixel to its nearest side polyline.

    Polylines and pixel coordinates are in canvas space. Pixel centers follow
    the existing alpha-geometry convention: local pixel ``(x, y)`` maps to
    ``(offset_x + x, offset_y + y)``. Exact distance ties go to ``left``.

    ``image`` may be the project's decoded :class:`RgbaImage` or raw RGBA
    bytes accompanied by ``width`` and ``height``. Fully transparent source
    RGB is intentionally cleared because it has no source-over contribution.
    """

    source = _normalize_image(image, width, height)
    offset_x, offset_y = _offset(canvas_offset_xy)
    left_points, left_segments = _polyline(left_polyline_xy, "left")
    right_points, right_segments = _polyline(right_polyline_xy, "right")
    if left_points == right_points or left_points == tuple(reversed(right_points)):
        raise AlphaBilateralSplitError("left and right polylines must be distinct")

    left_pixels = bytearray(len(source.pixels))
    right_pixels = bytearray(len(source.pixels))
    left_count = right_count = tie_count = 0
    for index in range(source.width * source.height):
        byte_offset = index * 4
        if source.pixels[byte_offset + 3] == 0:
            continue
        local_x, local_y = index % source.width, index // source.width
        canvas_x, canvas_y = offset_x + local_x, offset_y + local_y
        left_distance = _squared_distance_to_polyline(canvas_x, canvas_y, left_segments)
        right_distance = _squared_distance_to_polyline(canvas_x, canvas_y, right_segments)
        target = left_pixels if left_distance <= right_distance else right_pixels
        target[byte_offset : byte_offset + 4] = source.pixels[byte_offset : byte_offset + 4]
        if left_distance <= right_distance:
            left_count += 1
            tie_count += left_distance == right_distance
        else:
            right_count += 1

    if left_count + right_count == 0:
        raise AlphaBilateralSplitError("RGBA image has no alpha-positive pixels")
    if left_count == 0 or right_count == 0:
        raise AlphaBilateralSplitError("bilateral split leaves one side empty")
    return AlphaBilateralSplit(
        left=RgbaImage(source.width, source.height, bytes(left_pixels)),
        right=RgbaImage(source.width, source.height, bytes(right_pixels)),
        canvas_offset_xy=(offset_x, offset_y),
        left_foreground_pixels=left_count,
        right_foreground_pixels=right_count,
        tie_foreground_pixels=tie_count,
    )


def _normalize_image(
    value: RgbaImage | bytes | bytearray | memoryview,
    width: int | None,
    height: int | None,
) -> RgbaImage:
    if isinstance(value, RgbaImage):
        actual_width = _positive_int(value.width, "image width")
        actual_height = _positive_int(value.height, "image height")
        if width is not None:
            if _positive_int(width, "image width") != actual_width:
                raise AlphaBilateralSplitError("width conflicts with decoded image")
        if height is not None:
            if _positive_int(height, "image height") != actual_height:
                raise AlphaBilateralSplitError("height conflicts with decoded image")
        expected = _checked_rgba_byte_count(actual_width, actual_height)
        pixels = _pixel_bytes(value.pixels, expected)
    else:
        actual_width = _positive_int(width, "image width")
        actual_height = _positive_int(height, "image height")
        expected = _checked_rgba_byte_count(actual_width, actual_height)
        pixels = _pixel_bytes(value, expected)
    return RgbaImage(actual_width, actual_height, pixels)


def _pixel_bytes(value: Any, expected: int) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise AlphaBilateralSplitError("pixels must be an RGBA byte buffer")
    if len(value) != expected:
        raise AlphaBilateralSplitError("RGBA byte length does not match image dimensions")
    try:
        return bytes(value)
    except (TypeError, ValueError) as exc:
        raise AlphaBilateralSplitError("pixels must be an RGBA byte buffer") from exc


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise AlphaBilateralSplitError(f"{label} must be a positive integer")
    return value


def _checked_rgba_byte_count(width: int, height: int) -> int:
    pixels = width * height
    if pixels > MAX_RGBA_PIXELS:
        raise AlphaBilateralSplitError(
            f"RGBA image exceeds {MAX_RGBA_PIXELS} pixels ({MAX_RGBA_BYTES} bytes)"
        )
    return pixels * 4


def _offset(value: Any) -> tuple[int, int]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or len(value) != 2
        or any(not isinstance(item, int) or isinstance(item, bool) for item in value)
    ):
        raise AlphaBilateralSplitError("canvas offset must contain two integers")
    result = (value[0], value[1])
    try:
        finite = all(math.isfinite(float(item)) for item in result)
    except OverflowError:
        finite = False
    if not finite:
        raise AlphaBilateralSplitError("canvas offset is outside the finite coordinate range")
    return result


def _polyline(
    value: Iterable[Sequence[float]], label: str
) -> tuple[tuple[tuple[float, float], ...], tuple[_Segment, ...]]:
    if isinstance(value, (str, bytes, bytearray)):
        raise AlphaBilateralSplitError(f"{label} polyline must be an iterable of points")
    try:
        iterator = iter(value)
    except TypeError as exc:
        raise AlphaBilateralSplitError(
            f"{label} polyline must be an iterable of points"
        ) from exc
    points_list: list[tuple[float, float]] = []
    for index, item in enumerate(iterator):
        if index == MAX_GUIDE_POINTS:
            raise AlphaBilateralSplitError(
                f"{label} polyline exceeds {MAX_GUIDE_POINTS} points"
            )
        points_list.append(_point(item, label))
    points = tuple(points_list)
    if len(points) < 2:
        raise AlphaBilateralSplitError(f"{label} polyline needs at least two points")
    segments: list[_Segment] = []
    for start, end in zip(points, points[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length_squared = dx * dx + dy * dy
        if (
            not math.isfinite(dx)
            or not math.isfinite(dy)
            or not math.isfinite(length_squared)
        ):
            raise AlphaBilateralSplitError(f"{label} polyline exceeds the finite coordinate range")
        if length_squared == 0:
            raise AlphaBilateralSplitError(f"{label} polyline has a zero-length segment")
        segments.append(
            _Segment(start[0], start[1], end[0], end[1], dx, dy, length_squared)
        )
    return points, tuple(segments)


def _point(value: Any, label: str) -> tuple[float, float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or len(value) != 2
    ):
        raise AlphaBilateralSplitError(f"{label} polyline points must contain two numbers")
    numbers: list[float] = []
    for item in value:
        if not isinstance(item, (int, float)) or isinstance(item, bool):
            raise AlphaBilateralSplitError(f"{label} polyline points must contain two numbers")
        try:
            number = float(item)
        except OverflowError as exc:
            raise AlphaBilateralSplitError(f"{label} polyline points must be finite") from exc
        if not math.isfinite(number):
            raise AlphaBilateralSplitError(f"{label} polyline points must be finite")
        numbers.append(number)
    return numbers[0], numbers[1]


def _squared_distance_to_polyline(
    x: int, y: int, segments: tuple[_Segment, ...]
) -> float:
    """Return nearest squared distance without sqrt or normalized vectors.

    Segment projection is classified by ``dot <= 0`` and
    ``dot >= length_squared``.  Interior distance is the specified
    ``cross_squared / length_squared`` expression.  Segments are visited in
    authoring order and side equality is resolved only by the caller's
    declared left tie-break.
    """

    best = math.inf
    for segment in segments:
        relative_x, relative_y = x - segment.start_x, y - segment.start_y
        projection = relative_x * segment.delta_x + relative_y * segment.delta_y
        if projection <= 0:
            distance = relative_x * relative_x + relative_y * relative_y
        elif projection >= segment.length_squared:
            end_x, end_y = x - segment.end_x, y - segment.end_y
            distance = end_x * end_x + end_y * end_y
        else:
            cross = relative_x * segment.delta_y - relative_y * segment.delta_x
            distance = (cross * cross) / segment.length_squared
        if not math.isfinite(projection) or not math.isfinite(distance):
            raise AlphaBilateralSplitError("pixel-to-polyline distance is not finite")
        best = min(best, distance)
    return best
