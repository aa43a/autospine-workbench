"""Small outward-rounded interval primitives for P10 continuous proofs.

The implementation treats admitted binary64 inputs as exact contract values.
Every arithmetic result is expanded with ``nextafter``.  Trigonometric ranges
also include all enclosed extrema, so callers may prove bounds but may never
infer safety from point samples.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .body_sway_rigorous_trig import (
    rigorous_cosine_bounds,
    rigorous_pi_float_bounds,
    rigorous_sine_bounds,
)


_NEGATIVE_INFINITY = -math.inf
_POSITIVE_INFINITY = math.inf


def _step(value: float, direction: float, count: int = 1) -> float:
    result = value
    for _index in range(count):
        result = math.nextafter(result, direction)
    return result


def round_down(value: float) -> float:
    """Return the next representable value toward negative infinity."""

    return value if value == _NEGATIVE_INFINITY else _step(
        value, _NEGATIVE_INFINITY
    )


def round_up(value: float) -> float:
    """Return the next representable value toward positive infinity."""

    return value if value == _POSITIVE_INFINITY else _step(
        value, _POSITIVE_INFINITY
    )


@dataclass(frozen=True, slots=True)
class OutwardInterval:
    """Closed binary64 interval with outward-rounded basic operations."""

    lower: float
    upper: float

    def __post_init__(self) -> None:
        if math.isnan(self.lower) or math.isnan(self.upper) \
                or self.lower > self.upper:
            raise ValueError("Outward interval bounds are invalid")

    @classmethod
    def point(cls, value: float) -> OutwardInterval:
        if not math.isfinite(value):
            raise ValueError("Outward interval point must be finite")
        return cls(float(value), float(value))

    @property
    def finite(self) -> bool:
        return math.isfinite(self.lower) and math.isfinite(self.upper)

    @property
    def width(self) -> float:
        return round_up(self.upper - self.lower)

    def __add__(self, other: OutwardInterval) -> OutwardInterval:
        lower, upper = self.lower + other.lower, self.upper + other.upper
        if math.isnan(lower) or math.isnan(upper):
            return OutwardInterval(_NEGATIVE_INFINITY, _POSITIVE_INFINITY)
        return OutwardInterval(round_down(lower), round_up(upper))

    def __sub__(self, other: OutwardInterval) -> OutwardInterval:
        lower, upper = self.lower - other.upper, self.upper - other.lower
        if math.isnan(lower) or math.isnan(upper):
            return OutwardInterval(_NEGATIVE_INFINITY, _POSITIVE_INFINITY)
        return OutwardInterval(round_down(lower), round_up(upper))

    def __mul__(self, other: OutwardInterval) -> OutwardInterval:
        products = (
            self.lower * other.lower, self.lower * other.upper,
            self.upper * other.lower, self.upper * other.upper,
        )
        if any(math.isnan(value) for value in products):
            return OutwardInterval(_NEGATIVE_INFINITY, _POSITIVE_INFINITY)
        return OutwardInterval(
            min(round_down(value) for value in products),
            max(round_up(value) for value in products),
        )

    def divide_positive(self, value: float) -> OutwardInterval:
        """Divide by one exact, finite, strictly-positive contract value."""

        if not math.isfinite(value) or value <= 0.0:
            raise ValueError("Positive interval divisor is invalid")
        reciprocal = OutwardInterval(
            round_down(1.0 / value), round_up(1.0 / value)
        )
        return self * reciprocal

    def square(self) -> OutwardInterval:
        maximum = max(self.lower * self.lower, self.upper * self.upper)
        if self.lower <= 0.0 <= self.upper:
            return OutwardInterval(0.0, round_up(maximum))
        minimum = min(self.lower * self.lower, self.upper * self.upper)
        return OutwardInterval(round_down(minimum), round_up(maximum))

    def bisect(self) -> tuple[OutwardInterval, OutwardInterval] | None:
        midpoint = self.lower + (self.upper - self.lower) * 0.5
        if not self.lower < midpoint < self.upper:
            return None
        return (
            OutwardInterval(self.lower, midpoint),
            OutwardInterval(midpoint, self.upper),
        )


ZERO = OutwardInterval.point(0.0)
ONE = OutwardInterval.point(1.0)


def linear_interval(
    left: float, right: float, fraction: OutwardInterval,
) -> OutwardInterval:
    """Bound linear interpolation between two exact binary64 values."""

    return OutwardInterval.point(left) + (
        OutwardInterval.point(right) - OutwardInterval.point(left)
    ) * fraction


def radians_interval(degrees: OutwardInterval) -> OutwardInterval:
    """Convert degrees using the fixed rational bracket for true pi."""

    pi_lower, pi_upper = rigorous_pi_float_bounds()
    return degrees * OutwardInterval(
        round_down(pi_lower / 180.0), round_up(pi_upper / 180.0),
    )


def sine_interval(value: OutwardInterval) -> OutwardInterval:
    if not value.finite:
        return OutwardInterval(-1.0, 1.0)
    return OutwardInterval(*rigorous_sine_bounds(value.lower, value.upper))


def cosine_interval(value: OutwardInterval) -> OutwardInterval:
    if not value.finite:
        return OutwardInterval(-1.0, 1.0)
    return OutwardInterval(*rigorous_cosine_bounds(value.lower, value.upper))

