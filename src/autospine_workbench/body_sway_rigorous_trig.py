"""Rational Taylor enclosures for sine and cosine interval endpoints.

No platform ``sin``/``cos`` result participates in a proof.  A fixed rational
bracket for pi, exact ``Fraction`` range reduction, and the alternating-series
remainder produce mathematical enclosures before conversion back to binary64.
"""

from __future__ import annotations

from fractions import Fraction
import math


_PI_DIGITS = "314159265358979323846264338327950288419716939937510"
_PI_SCALE = 10 ** (len(_PI_DIGITS) - 1)
PI_LOWER = Fraction(int(_PI_DIGITS), _PI_SCALE)
PI_UPPER = Fraction(int(_PI_DIGITS) + 1, _PI_SCALE)
PI_MIDPOINT = (PI_LOWER + PI_UPPER) / 2
# On the reduced |x| <= 1 domain, the next term after 14 terms is below
# 1/28!, already far tighter than one binary64 ulp; it is retained exactly.
_SERIES_TERMS = 14


def rigorous_sine_bounds(lower: float, upper: float) -> tuple[float, float]:
    return _rigorous_trig_bounds(lower, upper, cosine=False)


def rigorous_cosine_bounds(lower: float, upper: float) -> tuple[float, float]:
    return _rigorous_trig_bounds(lower, upper, cosine=True)


def rigorous_pi_float_bounds() -> tuple[float, float]:
    return _lower_float(PI_LOWER), _upper_float(PI_UPPER)


def _rigorous_trig_bounds(
    lower: float, upper: float, *, cosine: bool,
) -> tuple[float, float]:
    left, right = Fraction.from_float(lower), Fraction.from_float(upper)
    if right - left >= 2 * PI_LOWER:
        return -1.0, 1.0
    endpoint_bounds = (
        _point_trig_bounds(left, cosine=cosine),
        _point_trig_bounds(right, cosine=cosine),
    )
    result_lower = min(row[0] for row in endpoint_bounds)
    result_upper = max(row[1] for row in endpoint_bounds)
    maximum_phase = Fraction(0) if cosine else Fraction(1, 2)
    minimum_phase = Fraction(1) if cosine else Fraction(3, 2)
    if _contains_phase(left, right, maximum_phase):
        result_upper = Fraction(1)
    if _contains_phase(left, right, minimum_phase):
        result_lower = Fraction(-1)
    return (
        max(-1.0, _lower_float(result_lower)),
        min(1.0, _upper_float(result_upper)),
    )


def _point_trig_bounds(
    value: Fraction, *, cosine: bool,
) -> tuple[Fraction, Fraction]:
    quadrant = _nearest_integer(value / (PI_MIDPOINT / 2))
    if abs(quadrant) > 2 ** 30:
        return Fraction(-1), Fraction(1)
    phase_lower, phase_upper = _scale_pi(Fraction(quadrant, 2))
    reduced = value - phase_upper, value - phase_lower
    if reduced[0] < -1 or reduced[1] > 1:
        return Fraction(-1), Fraction(1)
    sine = _small_sine_bounds(*reduced)
    cosine_range = _small_cosine_bounds(*reduced)
    quadrant_mod = quadrant % 4
    if cosine:
        choices = (cosine_range, _negate(sine), _negate(cosine_range), sine)
    else:
        choices = (sine, cosine_range, _negate(sine), _negate(cosine_range))
    return choices[quadrant_mod]


def _small_sine_bounds(
    lower: Fraction, upper: Fraction,
) -> tuple[Fraction, Fraction]:
    left = _scalar_sine_bounds(lower)
    right = _scalar_sine_bounds(upper)
    return left[0], right[1]


def _small_cosine_bounds(
    lower: Fraction, upper: Fraction,
) -> tuple[Fraction, Fraction]:
    left = _scalar_cosine_bounds(lower)
    right = _scalar_cosine_bounds(upper)
    result_lower = min(left[0], right[0])
    result_upper = Fraction(1) if lower <= 0 <= upper else max(
        left[1], right[1]
    )
    return result_lower, result_upper


def _scalar_sine_bounds(value: Fraction) -> tuple[Fraction, Fraction]:
    if value < 0:
        return _negate(_scalar_sine_bounds(-value))
    return _alternating_bounds(value, first_power=1)


def _scalar_cosine_bounds(value: Fraction) -> tuple[Fraction, Fraction]:
    return _alternating_bounds(abs(value), first_power=0)


def _alternating_bounds(
    value: Fraction, *, first_power: int,
) -> tuple[Fraction, Fraction]:
    term = value if first_power else Fraction(1)
    total = term
    sign = 1
    power = first_power
    for _index in range(1, _SERIES_TERMS):
        denominator = (power + 1) * (power + 2)
        term = term * value * value / denominator
        sign *= -1
        total += sign * term
        power += 2
    next_term = term * value * value / ((power + 1) * (power + 2))
    next_sign = -sign
    remainder_endpoint = total + next_sign * next_term
    return min(total, remainder_endpoint), max(total, remainder_endpoint)


def _contains_phase(
    lower: Fraction, upper: Fraction, phase: Fraction,
) -> bool:
    center = _nearest_integer(
        (((lower + upper) / 2) / PI_MIDPOINT - phase) / 2
    )
    if abs(center) > 2 ** 30:
        return True
    for index in range(center - 3, center + 4):
        point_lower, point_upper = _scale_pi(phase + 2 * index)
        if point_upper >= lower and point_lower <= upper:
            return True
    return False


def _scale_pi(value: Fraction) -> tuple[Fraction, Fraction]:
    products = value * PI_LOWER, value * PI_UPPER
    return min(products), max(products)


def _negate(value: tuple[Fraction, Fraction]) -> tuple[Fraction, Fraction]:
    return -value[1], -value[0]


def _nearest_integer(value: Fraction) -> int:
    if value < 0:
        return -_nearest_integer(-value)
    return (2 * value.numerator + value.denominator) // (
        2 * value.denominator
    )


def _lower_float(value: Fraction) -> float:
    result = float(value)
    if Fraction.from_float(result) > value:
        result = math.nextafter(result, -math.inf)
    return result


def _upper_float(value: Fraction) -> float:
    result = float(value)
    if Fraction.from_float(result) < value:
        result = math.nextafter(result, math.inf)
    return result
