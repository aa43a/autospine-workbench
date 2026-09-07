"""Measure the unchanged audit/bbox heuristic through an IO-free façade."""
from copy import deepcopy
from pathlib import Path

from ..joint_candidates import AuditBBoxHeuristicProvider
from ..project_store import ProjectStore, _ProjectRecord
from ..resolved_project import canonical_sha256
from .joint_draft import JOINTS, build_joint_draft

SCHEMA = "autospine.benchmark-joint-baseline/v1"


def build_joint_baseline(candidate, audit):
    """Caller verifies semantic source closure; no discovery or state is used.

    The legacy methods use only their arguments and other pure methods. Bypass
    ProjectStore initialization to avoid path resolution and override stores.
    Placeholder paths on the record must never be opened (covered by tests).
    """
    try:
        build_joint_draft(candidate)
        if type(audit) is not dict or candidate.get("audit_snapshot_sha256") != canonical_sha256(audit) \
                or candidate["canvas"] != audit.get("canvas") \
                or candidate.get("source_psd_sha256") != audit.get("sha256"):
            raise ValueError("benchmark_joint_baseline_audit_mismatch")
        canvas = candidate["canvas"]
        facade = object.__new__(ProjectStore)
        record = _ProjectRecord("benchmark", Path("__no_io__"), Path("__no_io__/audit.json"),
                                candidate["audit_snapshot_sha256"], deepcopy(audit))
        layers = facade._layers(record)
        skeleton = facade._skeleton(*canvas, layers)
        project = {"id": "benchmark", "source": {"sha256": audit["sha256"]},
                   "canvas": {"width": canvas[0], "height": canvas[1]}, "skeleton": skeleton}
        analysis = AuditBBoxHeuristicProvider().analyze(project)
        sources = {row["id"]: row["source"] for row in skeleton["joints"]}
        records = []
        for joint in JOINTS:
            point = analysis["joints"][joint]["candidates"][0]
            records.append({"joint_id": joint, "position": deepcopy(point["xy"]),
                            "method": point["method"], "score_kind": point["score_kind"],
                            "heuristic_score": point["heuristic_score"], "source": sources[joint],
                            "reason_codes": ["baseline_requires_review"]})
        return {"schema": SCHEMA, "authority": "none", "candidate_sha256": canonical_sha256(candidate),
                "algorithm_profile": "legacy-audit-bbox-v1", "canvas": deepcopy(canvas),
                "coordinate_system": "psd_canvas",
                "reason_codes": ["baseline_requires_review", "character_sides_unreviewed"],
                "records": records}
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError("benchmark_joint_baseline_input_invalid") from exc


def validate_joint_baseline(candidate, audit, document):
    """Exact replay rejects altered positions, scores, authority or extra fields."""
    expected = build_joint_baseline(candidate, audit)
    if type(document) is not dict or document != expected \
            or canonical_sha256(document) != canonical_sha256(expected):
        raise ValueError("benchmark_joint_baseline_mismatch")
    return deepcopy(expected)
