"""Explicit frontal canonical skeleton candidates without rig or review authority."""
from copy import deepcopy
import math

from ...resolved_project import canonical_sha256

SCHEMA = "autospine.canonical-skeleton-candidate/v1"
LIMBS = tuple(f"{joint}.{side}" for joint in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")
              for side in ("left", "right"))
MIN_LENGTH = 1.0


def _point(value, canvas):
    if type(value) is not list or len(value) != 2 or any(
            type(v) not in (int, float) or not 0 <= v <= limit or not math.isfinite(v)
            for v, limit in zip(value, canvas)):
        raise ValueError("canonical_skeleton_point_invalid")
    return [float(v) for v in value]


def _mid(a, b):
    return [(a[0]+b[0])/2, (a[1]+b[1])/2]


def _extend(start, end, distance):
    length = math.dist(start, end)
    if length < MIN_LENGTH:
        raise ValueError("canonical_skeleton_bone_too_short")
    return [end[i]+(end[i]-start[i])*distance/length for i in (0, 1)]


def _plan(points):
    pelvis = _mid(points["hip.left"], points["hip.right"])
    chest = _mid(points["shoulder.left"], points["shoulder.right"])
    torso = math.dist(pelvis, chest)
    if torso < MIN_LENGTH:
        raise ValueError("canonical_skeleton_torso_too_short")
    if chest[1] >= pelvis[1]:
        raise ValueError("canonical_skeleton_frontal_orientation_unsupported")
    spine = _mid(pelvis, chest)
    neck = _extend(pelvis, chest, torso * .2)
    head = _extend(pelvis, chest, torso * .45)
    head_tip = _extend(pelvis, chest, torso * .6)
    floor = [pelvis[0], max(points["ankle.left"][1], points["ankle.right"][1])]
    core = ["hip.left", "hip.right", "shoulder.left", "shoulder.right"]
    plan = [("root", None, floor, pelvis, "fallback", core + ["ankle.left", "ankle.right"], "ground_proxy"),
            ("pelvis", "root", pelvis, spine, "derived", core, "hip_midpoint"),
            ("spine", "pelvis", spine, chest, "derived", core, "torso_midpoint"),
            ("chest", "spine", chest, neck, "fallback", core, "neck_proportional_fallback"),
            ("neck", "chest", neck, head, "fallback", core, "head_proportional_fallback"),
            ("head", "neck", head, head_tip, "fallback", core, "head_tip_fallback")]
    for side, suffix in (("left", "l"), ("right", "r")):
        shoulder, elbow, wrist, hip, knee, ankle = [f"{j}.{side}" for j in
                                                   ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")]
        hand_tip = _extend(points[elbow], points[wrist], torso*.05)
        foot_tip = _extend(points[knee], points[ankle], torso*.05)
        plan.extend([
            (f"clavicle_{suffix}", "chest", chest, points[shoulder], "derived", core, "shoulder_midpoint"),
            (f"upperarm_{suffix}", f"clavicle_{suffix}", points[shoulder], points[elbow], "optimized", [shoulder, elbow], "optimized_limb"),
            (f"forearm_{suffix}", f"upperarm_{suffix}", points[elbow], points[wrist], "optimized", [elbow, wrist], "optimized_limb"),
            (f"hand_{suffix}", f"forearm_{suffix}", points[wrist], hand_tip, "fallback", [elbow, wrist], "hand_tip_extension"),
            (f"thigh_{suffix}", "pelvis", points[hip], points[knee], "optimized", [hip, knee], "optimized_limb"),
            (f"calf_{suffix}", f"thigh_{suffix}", points[knee], points[ankle], "optimized", [knee, ankle], "optimized_limb"),
            (f"foot_{suffix}", f"calf_{suffix}", points[ankle], foot_tip, "fallback", [knee, ankle], "foot_tip_extension"),
        ])
    return plan


def _compile(points, canvas):
    bones, frames = [], {}
    for identifier, parent, head, tail, kind, sources, reason in _plan(points):
        try:
            head, tail = _point(head, canvas), _point(tail, canvas)
        except ValueError as exc:
            raise ValueError("canonical_skeleton_derived_point_outside_canvas") from exc
        length = math.dist(head, tail)
        if length < MIN_LENGTH:
            raise ValueError("canonical_skeleton_bone_too_short")
        angle = math.degrees(math.atan2(tail[1]-head[1], tail[0]-head[0]))
        parent_head, parent_angle = frames[parent] if parent is not None else ([0., 0.], 0.)
        radians = math.radians(-parent_angle)
        dx, dy = head[0]-parent_head[0], head[1]-parent_head[1]
        local = {"x": dx*math.cos(radians)-dy*math.sin(radians),
                 "y": dx*math.sin(radians)+dy*math.cos(radians), "rotation_degrees": angle-parent_angle}
        bones.append({"id": identifier, "parent_id": parent, "head_xy": head, "tail_xy": tail,
                      "world_rotation_degrees": angle, "length": length, "setup_local": local,
                      "provenance": {"kind": kind, "source_joint_ids": sources, "reason_codes": [reason]}})
        frames[identifier] = (head, angle)
    return bones


def build_canonical_skeleton(candidate, optimization):
    """Caller verifies optimization closure; all central and terminal guesses stay explicit."""
    canvas = candidate.get("canvas") if type(candidate) is dict else None
    if type(candidate) is not dict or candidate.get("authority") != "none" \
            or candidate.get("schema") != "autospine.benchmark-semantic-candidates/v1" \
            or type(canvas) is not list or len(canvas) != 2 \
            or any(type(v) is not int or not 0 < v <= 65536 for v in canvas):
        raise ValueError("canonical_skeleton_candidate_invalid")
    if type(optimization) is not dict or optimization.get("candidate_sha256") != canonical_sha256(candidate) \
            or optimization.get("authority") != "none" or optimization.get("diagnostic_only") is not True \
            or optimization.get("schema") != "autospine.joint-optimization/v1" \
            or optimization.get("status") not in ("blocked", "candidate_requires_review"):
        raise ValueError("canonical_skeleton_optimization_invalid")
    result = {"schema": SCHEMA, "authority": "none", "diagnostic_only": True,
              "status": "blocked", "candidate_sha256": canonical_sha256(candidate),
              "source_optimization_sha256": canonical_sha256(optimization), "profile": "canonical-frontal-v1",
              "coordinate_system": "psd_canvas", "canvas": deepcopy(canvas), "bones": [], "reason_codes": []}
    if optimization.get("status") == "blocked":
        result["reason_codes"] = ["joint_optimization_blocked"]
        return result
    records = optimization.get("joints")
    if type(records) is not list or len(records) != len(LIMBS) \
            or any(type(row) is not dict or row.get("joint_id") != joint for row, joint in zip(records, LIMBS)):
        raise ValueError("canonical_skeleton_optimization_invalid")
    points = {row["joint_id"]: _point(row.get("position"), canvas) for row in records}
    try:
        result["bones"] = _compile(points, canvas)
    except ValueError as exc:
        result["reason_codes"] = [str(exc)]
        return result
    result["status"] = "candidate_requires_review"
    result["reason_codes"] = ["central_points_derived", "terminal_points_fallback", "skeleton_review_required"]
    return result


def validate_canonical_skeleton(candidate, optimization, document):
    expected = build_canonical_skeleton(candidate, optimization)
    if type(document) is not dict or canonical_sha256(document) != canonical_sha256(expected):
        raise ValueError("canonical_skeleton_mismatch")
    return deepcopy(expected)
