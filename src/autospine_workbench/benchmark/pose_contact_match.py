"""Bilateral pose-to-contact diagnostics; missing evidence never becomes a guess."""
from copy import deepcopy
from itertools import permutations
import math

from ..pose_observations import PoseObservationSet
from ..resolved_project import canonical_sha256
from .contact_screen import validate_contact_screen

SCHEMA = "autospine.benchmark-pose-contact-match/v1"
THRESHOLDS = {"min_detector_score": 0.5, "max_distance_diagonal_ratio": 0.08,
              "min_assignment_margin_diagonal_ratio": 0.015}
RELATIONS = (("torso_arm", "shoulder"), ("pelvis_leg", "hip"), ("leg_foot", "ankle"))
WARNINGS = ["semantic_roles_unreviewed", "heuristic_only"]


def _require(condition):
    if not condition:
        raise ValueError("benchmark_pose_contact_match_input_invalid")


def _point(value, canvas):
    _require(type(value) in (list, tuple) and len(value) == 2)
    _require(all(type(v) in (int, float) and 0 <= v <= limit and math.isfinite(v)
                 for v, limit in zip(value, canvas)))
    return list(value)


def _pose(candidate, observations):
    if observations is None:
        return "pose_observations_required"
    _require(isinstance(observations, PoseObservationSet))
    _require(observations.project_id == candidate.get("character_id")
             and observations.image_sha256 == candidate.get("composite_sha256")
             and list(observations.canvas_size) == candidate["canvas"])
    _require(observations.document is not None
             and canonical_sha256(observations.document) == observations.document_sha256)
    adapter = observations.adapter
    if observations.document.get("format_version") != 2 or not adapter:
        return "pose_adapter_v2_required"
    if adapter.get("mirror_state") not in ("mirrored", "not_mirrored"):
        return "pose_mirror_state_required"
    if adapter.get("view_orientation") not in ("front", "three_quarter"):
        return "pose_view_unsupported"
    return None


def _row(joint, relation, reason, anchor=None):
    return {"joint_id": joint, "relation": relation, "status": "blocked", "contact_id": None,
            "position": None, "anchor_xy": anchor, "distance_px": None,
            "reason_codes": [reason] + WARNINGS}


def _match(joint, relation, sites, observations, canvas):
    ids = [f"{joint}.{side}" for side in ("left", "right")]
    anchors, reason = [], None
    for key in ids:
        observed = observations.joints.get(key)
        if observed is None:
            anchors.append(None)
            reason = reason or "bilateral_pose_anchor_required"
            continue
        point = _point((observed.x, observed.y), canvas)
        score = observed.detector_score
        _require(type(score) in (int, float) and 0 <= score <= 1 and math.isfinite(score))
        anchors.append(point)
        if observed.visibility != "visible":
            reason = reason or "pose_anchor_not_visible"
        elif score < THRESHOLDS["min_detector_score"]:
            reason = reason or "pose_anchor_score_low"
    if reason:
        return [_row(key, relation, reason, anchor) for key, anchor in zip(ids, anchors)]
    if len(sites) < 2:
        return [_row(key, relation, "distinct_contact_sites_required", anchor) for key, anchor in zip(ids, anchors)]
    diagonal = math.hypot(*canvas)
    ranked = []
    for a, b in permutations(sites, 2):
        distances = (math.dist(anchors[0], a["representative_xy"]), math.dist(anchors[1], b["representative_xy"]))
        ranked.append((sum(distances), a["contact_id"], b["contact_id"], distances, a, b))
    ranked.sort(key=lambda value: value[:3])
    best = ranked[0]
    if (ranked[1][0]-best[0])/diagonal < THRESHOLDS["min_assignment_margin_diagonal_ratio"]:
        reason = "contact_assignment_ambiguous"
    elif any(distance/diagonal > THRESHOLDS["max_distance_diagonal_ratio"] for distance in best[3]):
        reason = "contact_assignment_too_far"
    if reason:
        return [_row(key, relation, reason, anchor) for key, anchor in zip(ids, anchors)]
    return [{"joint_id": key, "relation": relation, "status": "candidate_requires_review",
             "contact_id": site["contact_id"], "position": deepcopy(site["representative_xy"]),
             "anchor_xy": anchor, "distance_px": distance, "reason_codes": WARNINGS + ["pose_contact_requires_review"]}
            for key, anchor, distance, site in zip(ids, anchors, best[3], best[4:])]


def build_pose_contact_match(candidate, probe, screen, observations=None):
    """Caller replays raw pixels and pose source; output cannot approve anatomy."""
    try:
        validate_contact_screen(candidate, probe, screen)
        pose_reason = _pose(candidate, observations)
        eligible = {c["contact_id"] for r in screen["relations"] for p in r["pairs"] for c in p["contacts"]
                    if c["geometry_status"] != "rejected_deep_overlap"}
        records = []
        for relation, joint in RELATIONS:
            sites = [c for r in probe["relations"] if r["relation"] == relation
                     for p in r["pairs"] for c in p["contacts"] if c["contact_id"] in eligible]
            _require(len(sites) <= 128)
            for site in sites:
                _point(site.get("representative_xy"), candidate["canvas"])
            if pose_reason:
                records.extend(_row(f"{joint}.{side}", relation, pose_reason) for side in ("left", "right"))
            else:
                records.extend(_match(joint, relation, sites, observations, candidate["canvas"]))
        return {"schema": SCHEMA, "authority": "none", "diagnostic_only": True,
                "candidate_sha256": canonical_sha256(candidate), "probe_sha256": canonical_sha256(probe),
                "screen_sha256": canonical_sha256(screen),
                "pose_sha256": observations.document_sha256 if observations is not None else None,
                "algorithm_profile": "pose-contact-bilateral-match-v1", "thresholds": deepcopy(THRESHOLDS),
                "records": records, "summary": {"total": 6,
                    **{status: sum(row["status"] == status for row in records)
                       for status in ("blocked", "candidate_requires_review")}}}
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError("benchmark_pose_contact_match_input_invalid") from exc


def validate_pose_contact_match(candidate, probe, screen, observations, document):
    expected = build_pose_contact_match(candidate, probe, screen, observations)
    if type(document) is not dict or expected != document or canonical_sha256(expected) != canonical_sha256(document):
        raise ValueError("benchmark_pose_contact_match_mismatch")
    return deepcopy(expected)
