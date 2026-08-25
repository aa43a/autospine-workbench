"""Deterministic lossless partitioning of RGBA alpha by anatomical side."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import math
from typing import Any, Mapping

from .bilateral_component_assignment import (
    ComponentAssignmentError,
    assign_component_sides,
)
from .png_rgba import MAX_RGBA_BYTES, MAX_RGBA_PIXELS, RgbaImage
from .polyline_distance import (
    MAX_GUIDE_POINTS,
    normalize_polyline,
    squared_distance_to_polyline,
)
from .split_component_policy import (
    default_split_component_policy,
    normalize_split_component_policy,
)


class AlphaBilateralSplitError(ValueError):
    """Raised when an RGBA layer cannot be split without guessing."""


@dataclass(frozen=True, slots=True)
class AlphaBilateralSplit:
    """Two disjoint, full-size RGBA images sharing one canvas offset."""

    left: RgbaImage
    right: RgbaImage
    canvas_offset_xy: tuple[int, int]
    left_foreground_pixels: int
    right_foreground_pixels: int
    tie_foreground_pixels: int
    component_analysis: dict[str, object] | None

    @property
    def foreground_pixels(self) -> int:
        return self.left_foreground_pixels + self.right_foreground_pixels


def split_alpha_bilateral(
    image: RgbaImage | bytes | bytearray | memoryview,
    *,
    canvas_offset_xy: Sequence[int],
    left_polyline_xy: Iterable[Sequence[float]],
    right_polyline_xy: Iterable[Sequence[float]],
    width: int | None = None,
    height: int | None = None,
    component_policy: Mapping[str, Any] | None = None,
) -> AlphaBilateralSplit:
    """Run current v1.2 component-cohesive bilateral assignment.

    Polylines and pixel coordinates are in canvas space. Pixel centers follow
    the existing alpha-geometry convention: local pixel ``(x, y)`` maps to
    ``(offset_x + x, offset_y + y)``. Verified fused layers use the historical
    pixel-nearest rule; pair-mode residual ties resolve by guide then ``left``.

    ``image`` may be the project's decoded :class:`RgbaImage` or raw RGBA
    bytes accompanied by ``width`` and ``height``. Fully transparent source
    RGB is intentionally cleared because it has no source-over contribution.
    """

    raw_policy = (
        default_split_component_policy()
        if component_policy is None
        else component_policy
    )
    try:
        policy = normalize_split_component_policy(raw_policy)
    except ValueError as exc:
        raise AlphaBilateralSplitError(str(exc)) from exc
    return _split_alpha_bilateral(
        image,
        canvas_offset_xy=canvas_offset_xy,
        left_polyline_xy=left_polyline_xy,
        right_polyline_xy=right_polyline_xy,
        width=width,
        height=height,
        component_policy=policy,
    )


def split_alpha_bilateral_v1_1(
    image: RgbaImage | bytes | bytearray | memoryview,
    *,
    canvas_offset_xy: Sequence[int],
    left_polyline_xy: Iterable[Sequence[float]],
    right_polyline_xy: Iterable[Sequence[float]],
    width: int | None = None,
    height: int | None = None,
) -> AlphaBilateralSplit:
    """Replay the immutable v1.1 pixel-nearest algorithm exactly."""

    return _split_alpha_bilateral(
        image,
        canvas_offset_xy=canvas_offset_xy,
        left_polyline_xy=left_polyline_xy,
        right_polyline_xy=right_polyline_xy,
        width=width,
        height=height,
        component_policy=None,
    )


def _split_alpha_bilateral(
    image: RgbaImage | bytes | bytearray | memoryview,
    *,
    canvas_offset_xy: Sequence[int],
    left_polyline_xy: Iterable[Sequence[float]],
    right_polyline_xy: Iterable[Sequence[float]],
    width: int | None,
    height: int | None,
    component_policy: Mapping[str, int | float] | None,
) -> AlphaBilateralSplit:
    source = _normalize_image(image, width, height)
    offset_x, offset_y = _offset(canvas_offset_xy)
    try:
        left_points, left_segments = normalize_polyline(left_polyline_xy, "left")
        right_points, right_segments = normalize_polyline(right_polyline_xy, "right")
    except ValueError as exc:
        raise AlphaBilateralSplitError(str(exc)) from exc
    if left_points == right_points or left_points == tuple(reversed(right_points)):
        raise AlphaBilateralSplitError("left and right polylines must be distinct")

    component_assignment = None
    if component_policy is not None:
        try:
            component_assignment = assign_component_sides(
                source,
                canvas_offset_xy=(offset_x, offset_y),
                left_points=left_points,
                right_points=right_points,
                left_segments=left_segments,
                right_segments=right_segments,
                policy=component_policy,
            )
        except (ComponentAssignmentError, ValueError) as exc:
            raise AlphaBilateralSplitError(str(exc)) from exc

    left_pixels = bytearray(len(source.pixels))
    right_pixels = bytearray(len(source.pixels))
    assigned_sides = component_assignment.sides if component_assignment else None
    left_count = right_count = tie_count = 0
    for index in range(source.width * source.height):
        byte_offset = index * 4
        if source.pixels[byte_offset + 3] == 0:
            continue
        if assigned_sides is None:
            local_x, local_y = index % source.width, index // source.width
            canvas_x, canvas_y = offset_x + local_x, offset_y + local_y
            try:
                left_distance = squared_distance_to_polyline(
                    canvas_x, canvas_y, left_segments
                )
                right_distance = squared_distance_to_polyline(
                    canvas_x, canvas_y, right_segments
                )
            except ValueError as exc:
                raise AlphaBilateralSplitError(str(exc)) from exc
            side = 1 if left_distance <= right_distance else 2
            tie_count += left_distance == right_distance
        else:
            side = assigned_sides[index]
            if side not in (1, 2):
                raise AlphaBilateralSplitError("component assignment left a pixel unassigned")
        target = left_pixels if side == 1 else right_pixels
        target[byte_offset : byte_offset + 4] = source.pixels[byte_offset : byte_offset + 4]
        if side == 1:
            left_count += 1
        else:
            right_count += 1

    if assigned_sides is not None:
        tie_count = component_assignment.guide_tie_pixels

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
        component_analysis=(
            component_assignment.analysis if component_assignment is not None else None
        ),
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
