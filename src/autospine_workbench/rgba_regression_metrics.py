"""Deterministic exact-shape RGBA regression metrics."""

from __future__ import annotations

from typing import Any

from .png_rgba import RgbaImage


class RgbaRegressionMetricsError(ValueError):
    """Raised when two decoded rasters cannot be compared exactly."""


def compute_rgba_regression_metrics(
    actual: RgbaImage,
    expected: RgbaImage,
) -> dict[str, Any]:
    """Compare two same-size RGBA rasters without image re-encoding."""

    if type(actual) is not RgbaImage or type(expected) is not RgbaImage:
        raise RgbaRegressionMetricsError(
            "RGBA regression requires two exact decoded images"
        )
    if (actual.width, actual.height) != (expected.width, expected.height):
        raise RgbaRegressionMetricsError(
            "RGBA regression image dimensions differ"
        )
    left, right = actual.pixels, expected.pixels
    if len(left) != len(right) or not left or len(left) % 4:
        raise RgbaRegressionMetricsError(
            "RGBA regression buffers have an invalid shape"
        )
    differing_pixels = 0
    total_delta = 0
    max_delta = 0
    for offset in range(0, len(left), 4):
        deltas = tuple(
            abs(left[offset + channel] - right[offset + channel])
            for channel in range(4)
        )
        differing_pixels += int(any(deltas))
        total_delta += sum(deltas)
        max_delta = max(max_delta, *deltas)
    pixels = len(left) // 4
    return {
        "differing_pixels": differing_pixels,
        "differing_pixel_ratio": differing_pixels / pixels,
        "mean_absolute_error": total_delta / len(left),
        "max_channel_delta": max_delta,
    }


__all__ = [
    "RgbaRegressionMetricsError", "compute_rgba_regression_metrics",
]
