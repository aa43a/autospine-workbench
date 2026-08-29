"""Deterministic, non-authoritative suggestions for P10.5b review."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any


FORMAT = "autospine-seam-anchor-review-assist"
FORMAT_VERSION = 1
PROFILE_ID = "contact-overlap-strength-v1"
_Q = Decimal("1000000")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SeamAnchorReviewAssistError(ValueError):
    """Raised when a review-assist projection cannot be built safely."""


def build_seam_anchor_review_assist(
    candidate: dict[str, Any], candidate_sha256: str,
) -> dict[str, Any]:
    """Rank complete overlap options without turning a suggestion into approval."""

    relationships = candidate.get("relationships")
    if type(relationships) is not list or len(relationships) != 6 \
            or type(candidate_sha256) is not str \
            or _SHA256.fullmatch(candidate_sha256) is None:
        raise SeamAnchorReviewAssistError("Seam relationship inventory is invalid")
    suggestions = [_suggestion(row) for row in relationships]
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "profile_id": PROFILE_ID,
        "candidate_sha256": candidate_sha256,
        "human_confirmation_required": True,
        "auto_fill_count": sum(
            row["action"] is not None or row["option_id"] is not None
            for row in suggestions
        ),
        "manual_required_count": sum(
            row["disposition"] in {"compare_options", "manual_required"}
            for row in suggestions
        ),
        "suggestions": suggestions,
    }


def _suggestion(relationship: dict[str, Any]) -> dict[str, Any]:
    if type(relationship) is not dict or type(relationship.get("relationship_id")) is not str:
        raise SeamAnchorReviewAssistError("Seam relationship is invalid")
    identifier = relationship["relationship_id"]
    if relationship.get("status") == "unobservable":
        return {
            "relationship_id": identifier,
            "action": "unobservable",
            "option_id": None,
            "option_evidence_sha256": None,
            "highlight_option_id": None,
            "batch_eligible": True,
            "disposition": "blocked_unobservable",
            "selection_basis": "source_evidence_unobservable",
            "reason_codes": list(relationship.get("reason_codes") or []),
            "metrics": None,
        }
    ranked = []
    for option in relationship.get("options") or []:
        metrics = _overlap_metrics(option)
        if metrics is not None:
            ranked.append((
                -metrics["minimum_overlap_ratio_q1000000"],
                -metrics["area_px"],
                metrics["error_radius_q1000_px"],
                option["option_id"], option, metrics,
            ))
    if not ranked:
        return {
            "relationship_id": identifier,
            "action": None,
            "option_id": None,
            "option_evidence_sha256": None,
            "highlight_option_id": None,
            "batch_eligible": False,
            "disposition": "manual_required",
            "selection_basis": "manual_visual_comparison_required",
            "reason_codes": ["no_zero_gap_overlap_option_for_assist"],
            "metrics": None,
        }
    ranked.sort(key=lambda row: row[:4])
    _score_a, _score_b, _score_c, _identifier, option, metrics = ranked[0]
    if len(ranked) > 1:
        return {
            "relationship_id": identifier,
            "action": None,
            "option_id": None,
            "option_evidence_sha256": None,
            "highlight_option_id": option["option_id"],
            "batch_eligible": False,
            "disposition": "compare_options",
            "selection_basis": "largest_minimum_overlap_ratio_highlight_only",
            "reason_codes": ["multiple_visual_options_require_confirmation"],
            "metrics": metrics,
        }
    return {
        "relationship_id": identifier,
        "action": None,
        "option_id": option["option_id"],
        "option_evidence_sha256": option["evidence_sha256"],
        "highlight_option_id": option["option_id"],
        "batch_eligible": True,
        "disposition": "single_option",
        "selection_basis": "only_complete_overlap_option",
        "reason_codes": [],
        "metrics": metrics,
    }


def _overlap_metrics(option: dict[str, Any]) -> dict[str, int] | None:
    if type(option) is not dict or option.get("status") != "candidate" \
            or option.get("reason_codes") != []:
        return None
    contact = option.get("contact_evidence")
    if type(contact) is not dict or contact.get("mode") != "overlap" \
            or contact.get("gap_distance_px") != 0 \
            or type(contact.get("area")) is not int or contact["area"] <= 0:
        return None
    ratios = contact.get("overlap_ratios")
    if type(ratios) is not list or len(ratios) != 2:
        return None
    try:
        quantized = [_quantize(row, _Q) for row in ratios]
        radius = _quantize(contact.get("error_radius_px"), Decimal("1000"))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if min(quantized) <= 0 or radius < 0:
        return None
    return {
        "minimum_overlap_ratio_q1000000": min(quantized),
        "area_px": contact["area"],
        "error_radius_q1000_px": radius,
    }


def _quantize(value: Any, scale: Decimal) -> int:
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Metric must be finite")
    return int((number * scale).to_integral_value(rounding=ROUND_HALF_UP))
