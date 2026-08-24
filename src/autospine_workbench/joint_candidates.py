"""Joint candidate provider contracts and the legacy heuristic baseline."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from .resolved_project import canonical_sha256


class JointCandidateProvider(Protocol):
    provider_id: str
    provider_version: str

    def analyze(self, project: Mapping[str, Any]) -> dict[str, Any]: ...


class AuditBBoxHeuristicProvider:
    """Expose the existing single-point heuristic as explicit review evidence.

    This provider is intentionally a baseline, not a calibrated pose model. Later
    pose, alpha-medial-axis, and contact providers can emit additional candidates
    without changing the review or persistence contract.
    """

    provider_id = "audit-bbox-heuristic"
    provider_version = "1"

    def __init__(self, *, visible_threshold: float = 0.5) -> None:
        if not 0 <= visible_threshold <= 1:
            raise ValueError("visible_threshold must lie in [0, 1]")
        self.config = {"visible_threshold": float(visible_threshold)}

    def analyze(self, project: Mapping[str, Any]) -> dict[str, Any]:
        input_payload = {
            "project_id": project.get("id"),
            "source": project.get("source"),
            "canvas": project.get("canvas"),
            "skeleton_generation": (project.get("skeleton") or {}).get("generation"),
            "joints": (project.get("skeleton") or {}).get("joints"),
        }
        input_sha = canonical_sha256(input_payload)
        config_sha = canonical_sha256(self.config)
        run_sha = canonical_sha256(
            {
                "input_sha256": input_sha,
                "provider": self.provider_id,
                "provider_version": self.provider_version,
                "config_sha256": config_sha,
            }
        )
        joints: dict[str, Any] = {}
        low_score = False
        for joint in (project.get("skeleton") or {}).get("joints", []):
            if not isinstance(joint, Mapping) or not isinstance(joint.get("id"), str):
                continue
            joint_id = joint["id"]
            score = _score(joint.get("confidence"))
            ambiguous = score < self.config["visible_threshold"]
            low_score = low_score or ambiguous
            source = str(joint.get("source") or "unknown")
            qa_flags = ["LOW_HEURISTIC_SCORE"] if ambiguous else []
            joints[joint_id] = {
                "observability": "ambiguous" if ambiguous else "visible",
                "candidates": [
                    {
                        "candidate_id": f"{joint_id}.bbox.{run_sha[:12]}",
                        "xy": [float(joint["x"]), float(joint["y"])],
                        "method": "audit_bbox_heuristic",
                        "score_kind": "heuristic",
                        "heuristic_score": score,
                        "source_layer_ids": [],
                        "evidence": [
                            {
                                "kind": "audit_source",
                                "source_ref": source,
                                "note": "Existing audit/bbox setup-pose heuristic.",
                            }
                        ],
                        "qa_flags": qa_flags,
                    }
                ],
            }
        source_sha = str((project.get("source") or {}).get("sha256") or "")
        if len(source_sha) != 64:
            source_sha = "0" * 64
        return {
            "format": "autospine-joint-candidates",
            "format_version": 1,
            "project_id": project.get("id"),
            "source": {
                "base_project_sha256": input_sha,
                "source_image_sha256": source_sha,
            },
            "analysis": {
                "provider": self.provider_id,
                "provider_version": self.provider_version,
                "config_sha256": config_sha,
                "run_sha256": run_sha,
            },
            "coordinate_system": {
                "origin": "top_left",
                "x_axis": "right",
                "y_axis": "down",
                "units": "pixel",
                "side_naming": "character_side",
            },
            "joints": joints,
            "qa": {
                "status": "manual_required",
                "flags": [
                    "BASELINE_PROVIDER_REQUIRES_REVIEW",
                    *(["LOW_HEURISTIC_SCORE"] if low_score else []),
                ],
            },
        }


def _score(value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return 0.0
    return min(1.0, max(0.0, float(value)))
