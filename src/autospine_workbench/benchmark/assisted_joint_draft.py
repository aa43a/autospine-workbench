"""Editable model-assisted suggestions, explicitly excluded from independent GT."""
from copy import deepcopy

from ..resolved_project import canonical_sha256
from .joint_draft import JOINTS, build_joint_draft, validate_joint_draft
from .pose_accuracy import _pose

SCHEMA = "autospine.benchmark-assisted-joint-draft/v1"


def _require(condition):
    if not condition:
        raise ValueError("benchmark_assisted_joint_draft_invalid")


def _sources(candidate, baseline, pose):
    # The CLI replays baseline against its audit; bind and validate its points here.
    initial = build_joint_draft(candidate)
    _require(type(baseline) is dict and baseline.get("schema") == "autospine.benchmark-joint-baseline/v1"
             and baseline.get("authority") == "none" and baseline.get("candidate_sha256") == canonical_sha256(candidate)
             and baseline.get("canvas") == candidate["canvas"] and baseline.get("coordinate_system") == "psd_canvas"
             and baseline.get("algorithm_profile") == "legacy-audit-bbox-v1")
    rows = baseline.get("records")
    _require(type(rows) is list and len(rows) == len(JOINTS))
    for joint, target, source in zip(JOINTS, initial["records"], rows):
        _require(type(source) is dict and source.get("joint_id") == joint)
        target.update(status="observed", position=deepcopy(source.get("position")), notes="边界框自动建议，尚未复核")
    validate_joint_draft(candidate, initial)
    points = _pose(candidate, pose)
    for row in initial["records"]:
        if row["joint_id"] in points:
            row.update(position=deepcopy(points[row["joint_id"]]), notes="姿态模型自动建议，尚未复核")
    return validate_joint_draft(candidate, initial)


def build_assisted_joint_draft(candidate, baseline, pose):
    draft = _sources(candidate, baseline, pose)
    return {"schema": SCHEMA, "authority": "none", "annotation_mode": "model_assisted",
            "independent_annotation": False, "candidate_sha256": canonical_sha256(candidate),
            "source_pose_sha256": pose.document_sha256, "source_baseline_sha256": canonical_sha256(baseline),
            "reviewed_joint_ids": [], "draft": draft}


def validate_assisted_joint_draft(candidate, baseline, pose, document):
    """Allow manual edits only inside draft/reviewed IDs, preserving source identity."""
    expected = build_assisted_joint_draft(candidate, baseline, pose)
    _require(type(document) is dict and set(document) == set(expected))
    for key in expected.keys() - {"draft", "reviewed_joint_ids"}:
        _require(type(document[key]) is type(expected[key]) and document[key] == expected[key])
    reviewed = document["reviewed_joint_ids"]
    _require(type(reviewed) is list and all(type(joint) is str and joint in JOINTS for joint in reviewed)
             and len(set(reviewed)) == len(reviewed))
    validate_joint_draft(candidate, document["draft"])
    return deepcopy(document)
