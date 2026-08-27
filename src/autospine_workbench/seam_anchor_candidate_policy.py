"""Closed reason and state matrix for generated seam-anchor options."""

from __future__ import annotations

from collections.abc import Mapping

from .seam_anchor_sampling import (
    DEFAULT_ANCHOR_PAIRS,
    MIN_ANCHOR_PAIRS,
    SAMPLING_PROFILE,
)


_SOURCE_ISSUES = {
    "SOURCE_LAYER_MISSING", "SOURCE_LAYER_CROSSWIRE",
    "SOURCE_ROLE_MISSING_OR_UNSUPPORTED", "SOURCE_ROLE_CONFLICT",
    "SOURCE_SIDE_MISSING_OR_UNSUPPORTED", "SOURCE_SIDE_CONFLICT",
    "ATTACHMENT_TYPE_UNSUPPORTED", "ATTACHMENT_NOT_SETUP_VISIBLE",
}
ABSENCE_REASON_CODES = frozenset({
    "PARENT_ROLE_MISSING", "CHILD_ROLE_MISSING",
    "PARENT_SIDE_UNAVAILABLE", "CHILD_SIDE_UNAVAILABLE",
})
RELATIONSHIP_REASON_CODES = frozenset({
    *ABSENCE_REASON_CODES,
    *(f"{prefix}_{issue}" for prefix in ("PARENT", "CHILD")
      for issue in _SOURCE_ISSUES),
    "MESH_MESH_UNSUPPORTED", "MULTIPLE_CANDIDATE_PAIRS",
    "NO_SUPPORTED_CANDIDATE_PAIR",
    "RELATION_CANDIDATE_PAIR_BUDGET_EXCEEDED",
})
NO_CONTACT_REASON_CODES = frozenset({
    "SAMPLING_BUDGET_EXCEEDED", "CONTACT_OVERLAP_BELOW_THRESHOLD",
    "CONTACT_MASK_EMPTY", "CONTACT_GAP_TOO_LARGE", "CONTACT_UNOBSERVABLE",
})
OVERLAP_UNAVAILABLE_REASON_CODES = frozenset({
    "SAMPLING_BUDGET_EXCEEDED", "INSUFFICIENT_COMMON_ALPHA_POINTS",
    "LOCATOR_UNREPRESENTABLE",
})
GAP_UNAVAILABLE_REASON_CODES = frozenset({
    "GAP_LOCATOR_UNSUPPORTED_IN_V1",
})
OPTION_REASON_CODES = frozenset({
    *NO_CONTACT_REASON_CODES,
    *OVERLAP_UNAVAILABLE_REASON_CODES,
    *GAP_UNAVAILABLE_REASON_CODES,
})
ALL_REASON_CODES = frozenset({
    *RELATIONSHIP_REASON_CODES, *OPTION_REASON_CODES,
})


class SeamAnchorCandidatePolicyError(ValueError):
    """Raised when a sealed document describes impossible compiler state."""


def require_option_policy(
    row: Mapping[str, object], kinds: tuple[object, object],
    mode: str | None, anchor_count: int,
) -> tuple[str, ...]:
    """Require one state that the pinned compiler can actually emit."""

    status = row.get("status")
    reasons = _reason_tuple(row.get("reason_codes"), OPTION_REASON_CODES)
    axis, sampling = row.get("principal_axis"), row.get("sampling_profile")
    if kinds == ("mesh", "mesh"):
        raise SeamAnchorCandidatePolicyError(
            "Mesh-mesh seam options are never materialized in v1"
        )
    if (axis is None) != (sampling is None) \
            or axis not in (None, "x", "y") \
            or sampling not in (None, SAMPLING_PROFILE):
        raise SeamAnchorCandidatePolicyError(
            "Seam option sampling metadata is inconsistent"
        )
    if mode == "overlap" and axis is not None:
        bbox = row["contact_evidence"]["bbox_xywh"]  # type: ignore[index]
        expected_axis = "x" if bbox[2] >= bbox[3] else "y"
        if axis != expected_axis:
            raise SeamAnchorCandidatePolicyError(
                "Seam principal axis differs from contact geometry"
            )
    if status == "candidate":
        if reasons or mode != "overlap" or axis is None \
                or not MIN_ANCHOR_PAIRS <= anchor_count <= DEFAULT_ANCHOR_PAIRS:
            raise SeamAnchorCandidatePolicyError(
                "Candidate seam option lacks generated locator evidence"
            )
        return reasons
    if status != "unavailable" or anchor_count:
        raise SeamAnchorCandidatePolicyError(
            "Unavailable seam option state is inconsistent"
        )
    if len(reasons) != 1:
        raise SeamAnchorCandidatePolicyError(
            "Unavailable seam option needs one generated reason"
        )
    allowed = _unavailable_reasons(mode, axis)
    if reasons[0] not in allowed:
        raise SeamAnchorCandidatePolicyError(
            "Unavailable seam reason differs from its evidence state"
        )
    return reasons


def require_relationship_policy(
    reasons: tuple[str, ...], option_reasons: set[str],
    option_pairs: set[tuple[str, str]],
) -> None:
    """Cross-check relationship diagnostics against every emitted option."""

    values = set(_reason_tuple(reasons, ALL_REASON_CODES))
    if values & OPTION_REASON_CODES != option_reasons:
        raise SeamAnchorCandidatePolicyError(
            "Relationship option diagnostics are not exact"
        )
    has_options = bool(option_pairs)
    if ("NO_SUPPORTED_CANDIDATE_PAIR" in values) == has_options:
        raise SeamAnchorCandidatePolicyError(
            "Relationship candidate absence reason is inconsistent"
        )
    if has_options and values & ABSENCE_REASON_CODES:
        raise SeamAnchorCandidatePolicyError(
            "A relationship with options cannot report a missing role or side"
        )
    if has_options and "RELATION_CANDIDATE_PAIR_BUDGET_EXCEEDED" in values:
        raise SeamAnchorCandidatePolicyError(
            "A relationship over its pair budget cannot contain options"
        )
    if ("MULTIPLE_CANDIDATE_PAIRS" in values) != (len(option_pairs) > 1):
        raise SeamAnchorCandidatePolicyError(
            "Relationship pair multiplicity reason is inconsistent"
        )


def _unavailable_reasons(mode: str | None, axis: object) -> frozenset[str]:
    if mode is None and axis is None:
        return NO_CONTACT_REASON_CODES
    if mode == "gap" and axis is None:
        return GAP_UNAVAILABLE_REASON_CODES
    if mode == "overlap" and axis in ("x", "y"):
        return OVERLAP_UNAVAILABLE_REASON_CODES
    return frozenset()


def _reason_tuple(value: object, allowed: frozenset[str]) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) \
            or any(not isinstance(item, str) for item in value):
        raise SeamAnchorCandidatePolicyError("Seam reasons are invalid")
    result = tuple(value)
    if result != tuple(sorted(set(result))) \
            or any(item not in allowed or item != item.upper() for item in result):
        raise SeamAnchorCandidatePolicyError(
            "Seam reasons are outside the pinned compiler vocabulary"
        )
    return result
