"""Deterministic structural evidence rows for dynamic seam probe v2."""

from __future__ import annotations

import math

from .body_sway_dynamic_seam_evidence_profile_v2 import (
    EVIDENCE_MODEL,
    OVERLAP_REASON,
    SEGMENT_CERTIFIED_STATUS,
    THRESHOLD,
    body_sway_dynamic_seam_segment_sha256_v2,
)


class BodySwayDynamicSeamEvidenceRowsV2Error(ValueError):
    """Raised when raw interval evidence cannot form finite v2 rows."""


def structure_dynamic_seam_segment_v2(raw):
    relationships = [_relationship(row) for row in raw["relationships"]]
    certified = raw["status"] == "continuous_anchor_proximity_certified"
    row = {
        "left_tick": raw["left_tick"], "right_tick": raw["right_tick"],
        "status": SEGMENT_CERTIFIED_STATUS if certified else "indeterminate",
        "reason_codes": list(raw["reason_codes"]),
        "relationships": relationships,
        "max_squared_anchor_residual_upper_px2":
            _finite_or_none(raw["max_squared_distance_upper_px2"]),
        "threshold_squared_px2": raw["threshold_squared_px2"],
        "evaluated_box_count": raw["evaluated_box_count"],
        "certified_terminal_box_count": raw["certified_terminal_box_count"],
        "indeterminate_terminal_box_count":
            raw["indeterminate_terminal_box_count"],
        "maximum_depth_reached": raw["maximum_depth_reached"],
        "relationship_count": raw["relationship_count"],
        "pair_count": raw["pair_count"],
        "backend": {
            "time_model": raw["time_model"],
            "gain_model": raw["gain_model"],
            "proof_method": raw["proof_method"],
            "rounding_profile": raw["rounding_profile"],
            "scope": list(raw["scope"]),
            "exclusions": list(raw["exclusions"]),
            "metric_interpretation": raw["metric_interpretation"],
        },
    }
    row["segment_evidence_sha256"] = (
        body_sway_dynamic_seam_segment_sha256_v2(row)
    )
    return row


def summarize_dynamic_seam_segments_v2(
    segments, upstream_status, upstream_certified, inventory,
):
    certified = sum(row["status"] == SEGMENT_CERTIFIED_STATUS
                    for row in segments)
    reasons = {reason for row in segments for reason in row["reason_codes"]}
    if not upstream_certified:
        reasons.add("upstream_continuous_preview_model_structural_unproven")
    maxima = [row["max_squared_anchor_residual_upper_px2"]
              for row in segments]
    maximum = None if any(value is None for value in maxima) \
        else max(maxima, default=None)
    rows = [relationship for segment in segments
            for relationship in segment["relationships"]]
    return {
        "segment_count": len(segments),
        "certified_segment_count": certified,
        "indeterminate_segment_count": len(segments) - certified,
        "evaluated_box_count": sum(row["evaluated_box_count"]
                                   for row in segments),
        "certified_terminal_box_count": sum(
            row["certified_terminal_box_count"] for row in segments
        ),
        "indeterminate_terminal_box_count": sum(
            row["indeterminate_terminal_box_count"] for row in segments
        ),
        "maximum_depth_reached": max(
            (row["maximum_depth_reached"] for row in segments), default=0
        ),
        "relationship_count": inventory["relationship_count"],
        "anchor_pair_count": inventory["anchor_pair_count"],
        "segment_relationship_count": len(rows),
        "finite_anchor_residual_relationship_count": sum(
            row["status"] == "finite_upper_bound" for row in rows
        ),
        "overlap_not_evaluated_relationship_count": len(rows),
        "max_squared_anchor_residual_upper_px2": maximum,
        "threshold_squared_px2": THRESHOLD["max_squared_anchor_gap_px2"],
        "upstream_continuous_preview_model_status": upstream_status,
        "all_anchor_residual_segments_certified": (
            bool(segments) and certified == len(segments)
        ),
        "reason_codes": sorted(reasons),
    }


def _relationship(raw):
    maximum = _finite_or_none(raw["max_squared_distance_upper_px2"])
    within = None if maximum is None else maximum <= (
        THRESHOLD["max_squared_anchor_gap_px2"]
    )
    return {
        "relationship_id": raw["relationship_id"],
        "status": "finite_upper_bound" if maximum is not None
            else "indeterminate",
        "pairs": [{
            "pair_id": pair["pair_id"],
            "max_squared_anchor_residual_upper_px2": _finite_or_none(
                pair["max_squared_distance_upper_px2"]
            ),
        } for pair in raw["pairs"]],
        "anchor_residual": {
            "model": EVIDENCE_MODEL["anchor_residual"],
            "max_squared_upper_px2": maximum,
            "within_engineering_tolerance": within,
        },
        "gap_proxy": {
            "model": EVIDENCE_MODEL["gap_proxy"],
            "max_squared_upper_px2": maximum,
            "within_engineering_tolerance": within,
            "raster_gap_claimed": False,
        },
        "overlap": {
            "model": EVIDENCE_MODEL["overlap"],
            "status": "not_evaluated", "reason_code": OVERLAP_REASON,
            "raster_overlap_claimed": False,
        },
    }


def _finite_or_none(value):
    if value is None:
        return None
    if type(value) is not float or not math.isfinite(value) or value < 0.0:
        raise BodySwayDynamicSeamEvidenceRowsV2Error(
            "Dynamic seam v2 residual bound is not finite"
        )
    return value


__all__ = [
    "BodySwayDynamicSeamEvidenceRowsV2Error",
    "structure_dynamic_seam_segment_v2",
    "summarize_dynamic_seam_segments_v2",
]
