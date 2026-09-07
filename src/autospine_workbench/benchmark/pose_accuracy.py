"""Compare source-bound methods only against explicitly recorded benchmark references."""
from copy import deepcopy
import math
from statistics import median

from ..asset.joints.optimizer import JOINTS, CONTACT_JOINTS
from ..pose_observations import PoseObservationSet
from ..resolved_project import canonical_sha256
from .joint_draft import JOINTS as ALL_JOINTS, build_joint_draft, validate_joint_draft

METHODS = ("baseline", "pose", "optimized")
SCHEMA = "autospine.benchmark-pose-accuracy/v1"


def _require(condition):
    if not condition:
        raise ValueError("benchmark_pose_accuracy_input_invalid")


def _point(value, canvas):
    _require(type(value) in (list, tuple) and len(value) == 2 and all(
        type(v) in (int, float) and 0 <= v <= limit and math.isfinite(v)
        for v, limit in zip(value, canvas)))
    return list(value)


def _indexed(rows, expected, canvas):
    _require(type(rows) is list and len(rows) == len(expected))
    _require(all(type(row) is dict and row.get("joint_id") == joint for row, joint in zip(rows, expected)))
    return {row["joint_id"]: _point(row.get("position"), canvas) for row in rows}


def _reference(candidate, reference):
    if reference is None:
        return build_joint_draft(candidate)
    _require(type(reference) is dict and reference.get("schema") == "autospine.benchmark-joint-reference/v1"
             and reference.get("authority") == "none" and reference.get("scope") == "benchmark_only"
             and reference.get("independent_annotation") is True
             and reference.get("source_candidate_sha256") == canonical_sha256(candidate))
    draft = {"schema": "autospine.benchmark-joint-draft/v1", "authority": "none",
             "candidate_sha256": canonical_sha256(candidate), "records": reference.get("records")}
    validated = validate_joint_draft(candidate, draft)
    _require(reference.get("source_draft_sha256") == canonical_sha256(draft)
             and any(row["status"] == "observed" for row in draft["records"]))
    return validated


def _pose(candidate, pose):
    _require(isinstance(pose, PoseObservationSet) and type(pose.document) is dict
             and pose.project_id == candidate.get("character_id")
             and pose.image_sha256 == candidate.get("composite_sha256")
             and list(pose.canvas_size) == candidate["canvas"]
             and canonical_sha256(pose.document) == pose.document_sha256)
    source = pose.document.get("source", {})
    _require(pose.document.get("project_id") == pose.project_id
             and source.get("image_sha256") == pose.image_sha256
             and source.get("canvas_size") == candidate["canvas"])
    result = {}
    for joint in JOINTS:
        if joint not in pose.joints:
            _require(joint not in pose.document["joints"])
            continue
        observed = pose.joints[joint]
        point = _point([observed.x, observed.y], candidate["canvas"])
        raw = pose.document["joints"].get(joint)
        _require(type(raw) is dict and _point(raw.get("xy"), candidate["canvas"]) == point
                 and type(observed.detector_score) in (int, float)
                 and 0 <= observed.detector_score <= 1 and math.isfinite(observed.detector_score)
                 and raw.get("detector_score") == observed.detector_score
                 and raw.get("visibility") == observed.visibility)
        result[joint] = point
    return result


def _median(values):
    return median(values) if values else None


def _summary(rows, method):
    samples = [row["methods"][method] for row in rows]
    distances = [item["distance_px"] for item in samples if item["distance_px"] is not None]
    ratios = [item["distance_height_ratio"] for item in samples if item["distance_height_ratio"] is not None]
    return {"compared": len(distances), "median_distance_px": _median(distances),
            "median_distance_height_ratio": _median(ratios)}


def _comparison(rows, first, second):
    common = [(row["methods"][first], row["methods"][second]) for row in rows
              if row["methods"][first]["distance_px"] is not None
              and row["methods"][second]["distance_px"] is not None]
    return {"compared": len(common),
            "first_median_distance_px": _median([a["distance_px"] for a, _ in common]),
            "second_median_distance_px": _median([b["distance_px"] for _, b in common]),
            "median_delta_px": _median([b["distance_px"]-a["distance_px"] for a, b in common]),
            "median_delta_height_ratio": _median([b["distance_height_ratio"]-a["distance_height_ratio"] for a, b in common])}


def build_pose_accuracy(candidate, baseline, pose, optimized, reference, *, character_height):
    """Caller replays baseline/optimization/reference closure and verifies alpha height.

    Differences are paired on the same observed reference joints; coverage loss
    cannot masquerade as an improvement. Negative delta means the second is closer.
    """
    try:
        canvas = candidate.get("canvas") if type(candidate) is dict else None
        _require(type(canvas) is list and len(canvas) == 2 and all(type(v) is int and 0 < v <= 4096 for v in canvas))
        _require(type(character_height) in (int, float) and 1 <= character_height <= canvas[1] and math.isfinite(character_height))
        annotations = _reference(candidate, reference)
        identity = canonical_sha256(candidate)
        _require(type(baseline) is dict and baseline.get("schema") == "autospine.benchmark-joint-baseline/v1"
                 and baseline.get("authority") == "none" and baseline.get("candidate_sha256") == identity)
        baseline_points = _indexed(baseline.get("records"), ALL_JOINTS, canvas)
        pose_points = _pose(candidate, pose)
        _require(type(optimized) is dict and optimized.get("schema") == "autospine.joint-optimization/v1"
                 and optimized.get("authority") == "none" and optimized.get("diagnostic_only") is True
                 and optimized.get("candidate_sha256") == identity and optimized.get("pose_sha256") == pose.document_sha256
                 and optimized.get("status") in ("blocked", "candidate_requires_review"))
        if optimized["status"] == "blocked":
            _require(optimized.get("joints") == [])
            optimized_points = {}
        else:
            optimized_points = _indexed(optimized.get("joints"), JOINTS, canvas)
        points = {"baseline": baseline_points, "pose": pose_points, "optimized": optimized_points}
        references = {row["joint_id"]: row for row in annotations["records"]}
        rows = []
        for joint in JOINTS:
            ref = references[joint]; methods = {}
            for name in METHODS:
                position = points[name].get(joint)
                distance = math.dist(position, ref["position"]) if position is not None and ref["status"] == "observed" else None
                methods[name] = {"position": deepcopy(position), "distance_px": distance,
                                 "distance_height_ratio": distance / character_height if distance is not None else None}
            rows.append({"joint_id": joint, "reference_status": ref["status"],
                         "reference_position": deepcopy(ref["position"]), "methods": methods})
        counts = {status: sum(row["reference_status"] == status for row in rows)
                  for status in ("observed", "unmarked", "unobservable")}
        summary = {"reference_counts": counts}
        for name in METHODS:
            summary[name] = _summary(rows, name)
            available = sum(row["methods"][name]["position"] is not None for row in rows)
            summary[name].update(available=available, coverage=available/len(JOINTS),
                                 reference_coverage=summary[name]["compared"]/counts["observed"] if counts["observed"] else None,
                                 core=_summary([row for row in rows if row["joint_id"] in CONTACT_JOINTS], name))
        summary["comparisons"] = {f"{a}_vs_{b}": _comparison(rows, a, b)
                                  for a, b in (("baseline", "pose"), ("pose", "optimized"))}
        return {"schema": SCHEMA, "authority": "none", "accuracy_evaluated": bool(counts["observed"]),
                "reference_kind": "formal_benchmark_joint_reference" if reference is not None else "none",
                "candidate_sha256": identity, "baseline_sha256": canonical_sha256(baseline),
                "pose_sha256": pose.document_sha256, "optimization_sha256": canonical_sha256(optimized),
                "reference_sha256": canonical_sha256(reference) if reference is not None else None,
                "character_height_px": character_height, "records": rows, "summary": summary}
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        raise ValueError("benchmark_pose_accuracy_input_invalid") from exc


def validate_pose_accuracy(candidate, baseline, pose, optimized, reference, report, *, character_height):
    expected = build_pose_accuracy(candidate, baseline, pose, optimized, reference, character_height=character_height)
    if type(report) is not dict or canonical_sha256(report) != canonical_sha256(expected):
        raise ValueError("benchmark_pose_accuracy_mismatch")
    return deepcopy(expected)
