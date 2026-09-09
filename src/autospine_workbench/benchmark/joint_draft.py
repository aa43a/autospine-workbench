"""Manual PSD-canvas joint observations without adoption authority."""
from copy import deepcopy
import math
import unicodedata

from ..resolved_project import canonical_sha256

SCHEMA = "autospine.benchmark-joint-draft/v1"
JOINTS = ("root", "pelvis", "chest", "neck", "head") + tuple(
    f"{joint}.{side}" for joint in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")
    for side in ("left", "right"))


def build_joint_draft(candidate):
    return validate_joint_draft(candidate, {
        "schema": SCHEMA, "candidate_sha256": canonical_sha256(candidate), "authority": "none",
        "records": [{"joint_id": joint, "status": "unmarked", "position": None, "notes": ""}
                    for joint in JOINTS],
    })


def validate_joint_draft(candidate, draft):
    """Caller validates candidate source closure; bounds use its PSD canvas."""
    if type(candidate) is not dict or candidate.get("schema") not in (
            "autospine.benchmark-semantic-candidates/v1", "autospine.project-semantic-candidates/v1") \
            or candidate.get("authority") != "none" or candidate.get("coordinate_system", "psd_canvas") != "psd_canvas":
        raise ValueError("benchmark_joint_candidate_invalid")
    canvas = candidate.get("canvas")
    if type(canvas) is not list or len(canvas) != 2 or any(type(v) is not int or v <= 0 for v in canvas):
        raise ValueError("benchmark_joint_canvas_invalid")
    if type(draft) is not dict or set(draft) != {"schema", "candidate_sha256", "authority", "records"} \
            or draft["schema"] != SCHEMA or draft["authority"] != "none" \
            or draft["candidate_sha256"] != canonical_sha256(candidate):
        raise ValueError("benchmark_joint_draft_mismatch")
    records = draft["records"]
    if type(records) is not list or len(records) != len(JOINTS):
        raise ValueError("benchmark_joint_records_invalid")
    for joint, row in zip(JOINTS, records):
        if type(row) is not dict or set(row) != {"joint_id", "status", "position", "notes"} \
                or row["joint_id"] != joint or row["status"] not in ("unmarked", "observed", "unobservable"):
            raise ValueError("benchmark_joint_records_invalid")
        notes = row["notes"]
        if type(notes) is not str or len(notes) > 1000 or any(unicodedata.category(c).startswith("C") for c in notes):
            raise ValueError("benchmark_joint_notes_invalid")
        if row["status"] == "unobservable" and not notes.strip():
            raise ValueError("benchmark_joint_unobservable_reason_required")
        point = row["position"]
        if row["status"] != "observed":
            if point is not None:
                raise ValueError("benchmark_joint_position_invalid")
        elif type(point) is not list or len(point) != 2 or any(
                type(v) not in (int, float) or not 0 <= v <= limit or not math.isfinite(v)
                for v, limit in zip(point, canvas)):
            raise ValueError("benchmark_joint_position_invalid")
    return deepcopy(draft)
