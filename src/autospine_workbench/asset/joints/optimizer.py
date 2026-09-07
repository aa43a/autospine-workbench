"""Deterministic bounded contact blend with finite backtracking feasibility."""
from copy import deepcopy
import math

from ...pose_observations import PoseObservationSet
from ...resolved_project import canonical_sha256

SCHEMA = "autospine.joint-optimization/v1"
JOINTS = tuple(f"{name}.{side}" for name in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")
               for side in ("left", "right"))
CONTACT_JOINTS = tuple(f"{name}.{side}" for name in ("shoulder", "hip", "ankle") for side in ("left", "right"))
STEPS = (1, .5, .25, .125, .0625, .03125, .015625, .0078125, 0)
BONES = tuple((f"{a}.{s}", f"{b}.{s}") for s in ("left", "right")
              for a, b in (("shoulder", "elbow"), ("elbow", "wrist"), ("hip", "knee"), ("knee", "ankle")))


def _require(condition):
    if not condition:
        raise ValueError("joint_optimization_input_invalid")


def _point(point, canvas):
    _require(type(point) in (list, tuple) and len(point) == 2)
    _require(all(type(v) in (int, float) and 0 <= v <= limit and math.isfinite(v)
                 for v, limit in zip(point, canvas)))
    return list(point)


def _validate_inputs(candidate, observations, match):
    _require(type(candidate) is dict and candidate.get("schema") == "autospine.benchmark-semantic-candidates/v1"
             and candidate.get("authority") == "none")
    canvas = candidate.get("canvas")
    _require(type(canvas) is list and len(canvas) == 2 and all(type(v) is int and 0 < v <= 4096 for v in canvas))
    pose_sha = None
    if observations is not None:
        _require(isinstance(observations, PoseObservationSet) and observations.document is not None
                 and observations.project_id == candidate.get("character_id")
                 and observations.image_sha256 == candidate.get("composite_sha256")
                 and list(observations.canvas_size) == canvas)
        pose_sha = canonical_sha256(observations.document)
        _require(pose_sha == observations.document_sha256)
    _require(type(match) is dict and match.get("schema") == "autospine.benchmark-pose-contact-match/v1"
             and match.get("authority") == "none" and match.get("diagnostic_only") is True
             and match.get("candidate_sha256") == canonical_sha256(candidate) and match.get("pose_sha256") == pose_sha)
    records = match.get("records")
    _require(type(records) is list and len(records) == 6)
    used_contacts = set()
    for joint, row in zip(CONTACT_JOINTS, records):
        _require(type(row) is dict and row.get("joint_id") == joint
                 and row.get("status") in ("blocked", "candidate_requires_review"))
        if row["status"] == "candidate_requires_review":
            _require(observations is not None and joint in observations.joints and type(row.get("contact_id")) is str)
            _require(row["contact_id"] not in used_contacts)
            used_contacts.add(row["contact_id"])
            _point(row.get("position"), canvas)
            anchor = _point(row.get("anchor_xy"), canvas)
            original = observations.joints[joint]
            _require(anchor == [original.x, original.y])
        else:
            _require(row.get("position") is None and row.get("contact_id") is None)
    return canvas, pose_sha


def _pose_points(observations, canvas):
    if observations is None:
        return {}, "pose_observations_required"
    adapter = observations.adapter
    if observations.document.get("format_version") != 2 or not adapter:
        return {}, "pose_adapter_v2_required"
    if adapter.get("mirror_state") not in ("mirrored", "not_mirrored"):
        return {}, "pose_mirror_state_required"
    if adapter.get("view_orientation") not in ("front", "three_quarter"):
        return {}, "pose_view_unsupported"
    points = {}
    for joint in JOINTS:
        row = observations.joints.get(joint)
        if row is None:
            return {}, "complete_limb_pose_required"
        score = row.detector_score
        _require(type(score) in (int, float) and 0 <= score <= 1 and math.isfinite(score))
        if row.visibility != "visible" or score < .5:
            return {}, "pose_anchor_not_eligible"
        points[joint] = _point((row.x, row.y), canvas)
    return points, None


def optimize_joints(candidate, observations, match):
    """Caller replays the complete match closure before invoking this pure core."""
    try:
        canvas, pose_sha = _validate_inputs(candidate, observations, match)
        diagonal = math.hypot(*canvas)
        minimum, max_shift = max(1, diagonal*.001), diagonal*.04
        report = {"schema": SCHEMA, "authority": "none", "diagnostic_only": True,
                  "candidate_sha256": canonical_sha256(candidate), "pose_sha256": pose_sha,
                  "match_sha256": canonical_sha256(match), "algorithm_profile": "pose-contact-bounded-blend-v1",
                  "status": "blocked", "reason_codes": [], "joints": [], "accepted_step": None,
                  "constraints": {"min_detector_score": .5, "min_bone_length_px": minimum,
                                  "max_displacement_px": max_shift, "contact_weight": .35,
                                  "bone_length_ratio": [.75, 1.25], "step_schedule": list(STEPS)}}
        points, reason = _pose_points(observations, canvas)
        if reason:
            report["reason_codes"] = [reason]
            return report
        lengths = {bone: math.dist(points[bone[0]], points[bone[1]]) for bone in BONES}
        if any(length < minimum for length in lengths.values()):
            report["reason_codes"] = ["pose_bone_degenerate"]
            return report
        delta = {joint: [0, 0] for joint in JOINTS}
        for row in match["records"]:
            if row["status"] != "candidate_requires_review":
                continue
            joint = row["joint_id"]
            shift = [(v-p)*.35 for v, p in zip(row["position"], points[joint])]
            distance = math.hypot(*shift)
            factor = min(1, max_shift/distance) if distance else 1
            delta[joint] = [value*factor for value in shift]
        for step in STEPS:
            proposed = {joint: [p+step*d for p, d in zip(points[joint], delta[joint])] for joint in JOINTS}
            bounded = all(0 <= v <= limit for point in proposed.values() for v, limit in zip(point, canvas))
            bounded = bounded and all(math.dist(points[joint], proposed[joint]) <= max_shift for joint in JOINTS)
            feasible = all(max(minimum, .75*length) <= math.dist(proposed[a], proposed[b]) <= 1.25*length
                           for (a, b), length in lengths.items())
            if not bounded or not feasible:
                continue
            report.update(status="candidate_requires_review", accepted_step=step,
                          reason_codes=["bounded_backtracking_not_global_optimum", "semantic_roles_unreviewed",
                                        "joint_adoption_requires_review"])
            if not any(row["status"] == "candidate_requires_review" for row in match["records"]):
                report["reason_codes"].append("contact_unavailable")
            report["joints"] = [{"joint_id": joint, "position": proposed[joint],
                                  "source": "pose_contact" if proposed[joint] != points[joint] else "pose",
                                  "displacement_px": math.dist(points[joint], proposed[joint])} for joint in JOINTS]
            return report
        report["reason_codes"] = ["joint_constraints_infeasible"]
        return report
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError("joint_optimization_input_invalid") from exc


def validate_joint_optimization(candidate, observations, match, document):
    expected = optimize_joints(candidate, observations, match)
    if type(document) is not dict or expected != document or canonical_sha256(expected) != canonical_sha256(document):
        raise ValueError("joint_optimization_mismatch")
    return deepcopy(expected)
