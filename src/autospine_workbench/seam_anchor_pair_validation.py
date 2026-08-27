"""Exact ordering and nonintersection contract for seam locator pairs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .seam_anchor_locators import (
    SeamAnchorLocatorError,
    resolve_attachment_locator_exact,
)


MIN_ANCHOR_PAIRS = 2
MAX_ANCHOR_PAIRS = 8
PAIR_ORDER_POLICY = "strict_on_both_principal_axes"
CONNECTOR_INTERSECTION_POLICY = "reject_intersection_or_touch_exact"


class SeamAnchorUnsupportedError(SeamAnchorLocatorError):
    """Raised for an explicitly unsupported version-one attachment pair."""

    reason_code = "unsupported_in_v1"


@dataclass(frozen=True, slots=True)
class ResolvedAnchorPair:
    pair_id: str
    point_a_xy: tuple[float, float]
    point_b_xy: tuple[float, float]


def validate_anchor_pairs(
    pairs: Sequence[Mapping[str, Any]],
    attachment_a: Mapping[str, Any], attachment_b: Mapping[str, Any], *,
    principal_axis: str,
) -> tuple[ResolvedAnchorPair, ...]:
    """Validate two-to-eight canonical, ordered, disjoint locator pairs."""

    if PAIR_ORDER_POLICY != "strict_on_both_principal_axes" \
            or CONNECTOR_INTERSECTION_POLICY \
            != "reject_intersection_or_touch_exact":
        raise SeamAnchorLocatorError("Seam anchor pair policy is unsupported")

    kind_a = attachment_a.get("type") \
        if isinstance(attachment_a, Mapping) else None
    kind_b = attachment_b.get("type") \
        if isinstance(attachment_b, Mapping) else None
    if kind_a == kind_b == "mesh":
        raise SeamAnchorUnsupportedError("mesh-mesh is unsupported_in_v1")
    if kind_a not in ("region", "mesh") or kind_b not in ("region", "mesh"):
        raise SeamAnchorLocatorError("attachment type must be region or mesh")
    if principal_axis not in ("x", "y"):
        raise SeamAnchorLocatorError("principal_axis must be x or y")
    if isinstance(pairs, (str, bytes)) or not isinstance(pairs, Sequence):
        raise SeamAnchorLocatorError("anchor pairs must be a sequence")
    if not MIN_ANCHOR_PAIRS <= len(pairs) <= MAX_ANCHOR_PAIRS:
        raise SeamAnchorLocatorError("anchor pair count must lie in [2, 8]")
    resolved: list[ResolvedAnchorPair] = []
    exact: list[tuple[
        tuple[Fraction, Fraction], tuple[Fraction, Fraction]
    ]] = []
    keys_a: set[tuple[Any, ...]] = set()
    keys_b: set[tuple[Any, ...]] = set()
    for index, raw in enumerate(pairs):
        if not isinstance(raw, Mapping) \
                or set(raw) != {"pair_id", "a", "b"}:
            raise SeamAnchorLocatorError("anchor pair fields are invalid")
        if raw.get("pair_id") != f"anchor.{index:03d}":
            raise SeamAnchorLocatorError(
                "anchor pair ids must be canonical and ordered"
            )
        if not isinstance(raw["a"], Mapping) \
                or not isinstance(raw["b"], Mapping):
            raise SeamAnchorLocatorError(
                "anchor pair locators must be objects"
            )
        point_a = resolve_attachment_locator_exact(raw["a"], attachment_a)
        point_b = resolve_attachment_locator_exact(raw["b"], attachment_b)
        key_a, key_b = _locator_key(raw["a"]), _locator_key(raw["b"])
        if key_a in keys_a or key_b in keys_b:
            raise SeamAnchorLocatorError("anchor endpoints must be unique")
        keys_a.add(key_a)
        keys_b.add(key_b)
        exact.append((point_a, point_b))
        resolved.append(ResolvedAnchorPair(
            raw["pair_id"], tuple(map(float, point_a)),
            tuple(map(float, point_b)),
        ))
    axis = 0 if principal_axis == "x" else 1
    if any(
        first[0][axis] >= second[0][axis]
        or first[1][axis] >= second[1][axis]
        for first, second in zip(exact, exact[1:])
    ):
        raise SeamAnchorLocatorError(
            "anchor pairs must be strictly ordered on the principal axis"
        )
    for index, first in enumerate(exact):
        for second in exact[index + 1:]:
            if _segments_intersect(first[0], first[1], second[0], second[1]):
                raise SeamAnchorLocatorError(
                    "anchor connectors must not intersect or touch"
                )
    return tuple(resolved)


def _segments_intersect(a, b, c, d) -> bool:
    first = _orientation(a, b, c)
    second = _orientation(a, b, d)
    third = _orientation(c, d, a)
    fourth = _orientation(c, d, b)
    if first == 0 and _on_segment(a, b, c):
        return True
    if second == 0 and _on_segment(a, b, d):
        return True
    if third == 0 and _on_segment(c, d, a):
        return True
    if fourth == 0 and _on_segment(c, d, b):
        return True
    return ((first > 0) != (second > 0)
            and (third > 0) != (fourth > 0))


def _on_segment(a, b, point) -> bool:
    return (min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= point[1] <= max(a[1], b[1]))


def _orientation(a, b, c):
    return ((b[0] - a[0]) * (c[1] - a[1])
            - (b[1] - a[1]) * (c[0] - a[0]))


def _locator_key(locator):
    if locator.get("locator_type") == "region-local-q4096":
        return (locator["attachment_id"], locator["locator_type"],
                *locator["local_xy_q4096"])
    return (locator["attachment_id"], locator.get("locator_type"),
            locator.get("triangle_index"), *locator.get("vertex_indices", ()),
            *locator.get("weights_q65535", ()))
