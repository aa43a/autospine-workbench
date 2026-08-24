"""Small candidate item builders shared by limb provider branches."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .pose_observations import PoseJointObservation


def pose_score(observation: PoseJointObservation) -> float:
    factor = {"visible": 1.0, "occluded": 0.65, "unknown": 0.5, "out_of_frame": 0.2}
    return max(0.0, min(1.0, observation.detector_score * factor[observation.visibility]))


def pose_candidate(
    joint_id: str,
    observation: PoseJointObservation,
    score: float,
    run_sha: str,
    pose_document_sha: str,
    flags: set[str],
) -> dict[str, Any]:
    return {
        "candidate_id": f"{joint_id}.pose.{run_sha[:12]}",
        "xy": [observation.x, observation.y],
        "method": "pose",
        "score_kind": "heuristic",
        "heuristic_score": round(score, 6),
        "source_layer_ids": [],
        "evidence": [
            {
                "kind": "pose_heatmap",
                "source_ref": f"pose-observations:{pose_document_sha}",
                "note": (
                    f"Detector-native score={observation.detector_score:.6f}, "
                    f"visibility={observation.visibility}; not a calibrated probability."
                ),
            }
        ],
        "qa_flags": sorted(flags),
    }


def fallback_joint(
    joint: Mapping[str, Any], run_sha: str, *, requires_pose: bool
) -> dict[str, Any]:
    joint_id = str(joint["id"])
    flags = ["MISSING_POSE_OBSERVATION"] if requires_pose else []
    return {
        "observability": "ambiguous" if requires_pose else "visible",
        "candidates": [
            {
                "candidate_id": f"{joint_id}.bbox.{run_sha[:12]}",
                "xy": [float(joint.get("x", 0)), float(joint.get("y", 0))],
                "method": "audit_bbox_heuristic",
                "score_kind": "heuristic",
                "heuristic_score": _clamp_score(joint.get("confidence")),
                "source_layer_ids": [],
                "evidence": [
                    {
                        "kind": "audit_source",
                        "source_ref": str(joint.get("source") or "unknown"),
                        "note": "Fallback audit/bbox setup-pose heuristic.",
                    }
                ],
                "qa_flags": flags,
            }
        ],
    }


def _clamp_score(value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return 0.0
    return min(1.0, max(0.0, float(value)))
