"""Detached exact moments for P10.5d dynamic seam locators.

These values are preparation data only.  They make no dynamic-seam, runtime,
visual-quality, or release claim until a later interval pose evaluator consumes
them and records its own bounded proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
from typing import TypeAlias

from .body_sway_interval_arithmetic import OutwardInterval


FractionPoint: TypeAlias = tuple[Fraction, Fraction]


@dataclass(frozen=True, slots=True)
class PreparedDynamicSeamInfluence:
    """One detached bone influence retained from a referenced bind vertex."""

    bone_index: int
    bone_id: str
    weight: Fraction


@dataclass(frozen=True, slots=True)
class PreparedDynamicSeamVertex:
    """One locator-referenced bind vertex and its exact rational weight."""

    vertex_index: int | None
    locator_weight: Fraction
    setup_canvas_xy: FractionPoint
    influences: tuple[PreparedDynamicSeamInfluence, ...]


@dataclass(frozen=True, slots=True)
class PreparedDynamicSeamMoment:
    """Affine LBS coefficients for one bone in one prepared locator."""

    bone_index: int
    bone_id: str
    affine_weight: Fraction
    setup_x_moment: Fraction
    setup_y_moment: Fraction


@dataclass(frozen=True, slots=True)
class OutwardDynamicSeamMoment:
    """Tight binary64 outward enclosure of one exact prepared moment."""

    bone_index: int
    bone_id: str
    affine_weight: OutwardInterval
    setup_x_moment: OutwardInterval
    setup_y_moment: OutwardInterval


def prepare_dynamic_seam_moments(
    vertices: tuple[PreparedDynamicSeamVertex, ...],
) -> tuple[PreparedDynamicSeamMoment, ...]:
    """Aggregate only referenced vertex/influence terms by stable bone id."""

    if type(vertices) is not tuple or not vertices:
        raise ValueError("Dynamic seam vertices must be a non-empty tuple")
    totals: dict[tuple[int, str], list[Fraction]] = {}
    locator_total = Fraction(0)
    for vertex in vertices:
        if type(vertex) is not PreparedDynamicSeamVertex:
            raise ValueError("Dynamic seam vertex preparation is invalid")
        _require_fraction(vertex.locator_weight, "locator weight")
        if vertex.locator_weight < 0:
            raise ValueError("Dynamic seam locator weight must be nonnegative")
        locator_total += vertex.locator_weight
        x, y = vertex.setup_canvas_xy
        _require_fraction(x, "setup x")
        _require_fraction(y, "setup y")
        if type(vertex.influences) is not tuple or not vertex.influences:
            raise ValueError("Dynamic seam influences must be a non-empty tuple")
        seen = set()
        for influence in vertex.influences:
            if type(influence) is not PreparedDynamicSeamInfluence:
                raise ValueError("Dynamic seam influence is invalid")
            _require_fraction(influence.weight, "influence weight")
            identity = influence.bone_index, influence.bone_id
            if type(influence.bone_index) is not int \
                    or not isinstance(influence.bone_id, str) \
                    or not influence.bone_id or identity in seen \
                    or influence.weight <= 0:
                raise ValueError("Dynamic seam influence identity is invalid")
            seen.add(identity)
            coefficient = vertex.locator_weight * influence.weight
            row = totals.setdefault(
                (influence.bone_index, influence.bone_id),
                [Fraction(0), Fraction(0), Fraction(0)],
            )
            row[0] += coefficient
            row[1] += coefficient * x
            row[2] += coefficient * y
    if locator_total != 1:
        raise ValueError("Dynamic seam locator weights must sum exactly to one")
    return tuple(
        PreparedDynamicSeamMoment(index, bone_id, *totals[(index, bone_id)])
        for index, bone_id in sorted(totals, key=lambda item: item[1])
        if totals[(index, bone_id)][0] != 0
    )


def outward_dynamic_seam_moments(
    moments: tuple[PreparedDynamicSeamMoment, ...],
) -> tuple[OutwardDynamicSeamMoment, ...]:
    """Convert exact prepared coefficients for later interval-pose injection."""

    if type(moments) is not tuple or not moments:
        raise ValueError("Dynamic seam moments must be a non-empty tuple")
    result = []
    for moment in moments:
        if type(moment) is not PreparedDynamicSeamMoment:
            raise ValueError("Dynamic seam moment preparation is invalid")
        result.append(OutwardDynamicSeamMoment(
            moment.bone_index, moment.bone_id,
            fraction_to_outward_interval(moment.affine_weight),
            fraction_to_outward_interval(moment.setup_x_moment),
            fraction_to_outward_interval(moment.setup_y_moment),
        ))
    return tuple(result)


def fraction_to_outward_interval(value: Fraction) -> OutwardInterval:
    """Return the tight binary64 interval containing one exact fraction."""

    _require_fraction(value, "outward fraction")
    try:
        nearest = float(value)
    except OverflowError as exc:
        raise ValueError("Outward fraction is outside finite binary64") from exc
    if not math.isfinite(nearest):
        raise ValueError("Outward fraction is outside finite binary64")
    represented = Fraction.from_float(nearest)
    if represented == value:
        return OutwardInterval.point(nearest)
    if represented < value:
        return OutwardInterval(nearest, math.nextafter(nearest, math.inf))
    return OutwardInterval(math.nextafter(nearest, -math.inf), nearest)


def _require_fraction(value, label: str) -> Fraction:
    if type(value) is not Fraction:
        raise ValueError(f"Dynamic seam {label} must be an exact Fraction")
    return value
