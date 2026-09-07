"""Diagnostic distances to unreviewed joint drafts, never accuracy evidence."""
from copy import deepcopy
import math
from statistics import median

from ..resolved_project import canonical_sha256
from .joint_draft import JOINTS, validate_joint_draft

SCHEMA = "autospine.benchmark-joint-comparison/v1"
CORE = {f"{joint}.{side}" for joint in ("shoulder", "hip", "ankle") for side in ("left", "right")}


def _number(value, maximum, *, positive=False):
    # Bounds precede float conversion so arbitrarily large integers fail safely.
    return type(value) in (int, float) and (0 < value if positive else 0 <= value) \
        and value <= maximum and math.isfinite(value)


def _baseline(candidate, baseline):
    if type(baseline) is not dict or baseline.get("schema") != "autospine.benchmark-joint-baseline/v1" \
            or baseline.get("authority") != "none" \
            or baseline.get("candidate_sha256") != canonical_sha256(candidate):
        raise ValueError("benchmark_joint_comparison_baseline_mismatch")
    rows = baseline.get("records")
    if type(rows) is not list or len(rows) != len(JOINTS):
        raise ValueError("benchmark_joint_comparison_records_invalid")
    for joint, row in zip(JOINTS, rows):
        if type(row) is not dict or row.get("joint_id") != joint:
            raise ValueError("benchmark_joint_comparison_records_invalid")
        point = row.get("position")
        if type(point) is not list or len(point) != 2 or any(
                not _number(v, limit) for v, limit in zip(point, candidate["canvas"])):
            raise ValueError("benchmark_joint_comparison_position_invalid")
        if row.get("method") != "audit_bbox_heuristic" or row.get("score_kind") != "heuristic" \
                or not _number(row.get("heuristic_score"), 1):
            raise ValueError("benchmark_joint_comparison_method_invalid")
        if row.get("source") not in ("character-bounds", "layer", "fallback", "derived") \
                or row.get("reason_codes") != ["baseline_requires_review"]:
            raise ValueError("benchmark_joint_comparison_evidence_invalid")
    return rows


def _summary(rows):
    distances = [row["distance_px"] for row in rows if row["distance_px"] is not None]
    normalized = [row["distance_height_ratio"] for row in rows if row["distance_height_ratio"] is not None]
    return {"compared": len(distances), "median_distance_px": median(distances) if distances else None,
            "median_distance_height_ratio": median(normalized) if normalized else None}


def build_joint_comparison(candidate, baseline, draft, *, character_height=None):
    """Caller verifies all source closure and obtains height from composite alpha.

    A supplied height must describe the character silhouette, not canvas height.
    This pure function cannot establish its provenance or review the reference.
    """
    canvas = candidate.get("canvas") if type(candidate) is dict else None
    if type(canvas) is not list or len(canvas) != 2 \
            or any(type(v) is not int or not 0 < v <= 65536 for v in canvas):
        raise ValueError("benchmark_joint_comparison_canvas_invalid")
    draft = validate_joint_draft(candidate, draft)
    candidates = _baseline(candidate, baseline)
    if character_height is not None and (not _number(character_height, canvas[1], positive=True)
                                         or character_height < 1):
        raise ValueError("benchmark_joint_comparison_height_invalid")
    rows = []
    for proposed, reference in zip(candidates, draft["records"]):
        distance = None
        if reference["status"] == "observed":
            distance = math.dist(proposed["position"], reference["position"])
        rows.append({"joint_id": proposed["joint_id"], "reference_status": reference["status"],
                     "candidate_position": deepcopy(proposed["position"]),
                     "reference_position": deepcopy(reference["position"]), "distance_px": distance,
                     "distance_height_ratio": distance / character_height
                     if distance is not None and character_height is not None else None})
    summary = {status: sum(row["reference_status"] == status for row in rows)
               for status in ("observed", "unmarked", "unobservable")}
    summary.update(_summary(rows))
    summary["core"] = _summary([row for row in rows if row["joint_id"] in CORE])
    return {"schema": SCHEMA, "authority": "none", "diagnostic_only": True,
            "reference_kind": "unreviewed_joint_draft", "profile": "draft-joint-distance-v1",
            "source_candidate_sha256": canonical_sha256(candidate),
            "source_baseline_sha256": canonical_sha256(baseline),
            "source_draft_sha256": canonical_sha256(draft), "character_height_px": character_height,
            "records": rows, "summary": summary}


def validate_joint_comparison(candidate, baseline, draft, report, *, character_height=None):
    expected = build_joint_comparison(candidate, baseline, draft, character_height=character_height)
    if type(report) is not dict or canonical_sha256(report) != canonical_sha256(expected):
        raise ValueError("benchmark_joint_comparison_mismatch")
    return deepcopy(expected)
