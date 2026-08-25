"""Pose-led limb candidates with alpha components as an auditable soft constraint."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

from .candidate_provenance import candidate_run_identity, required_sha256
from .limb_candidate_items import fallback_joint, pose_candidate, pose_score
from .limb_evidence_layers import (
    LimbCandidateError,
    LimbEvidenceSet,
    load_limb_evidence,
)
from .pose_observations import PoseObservationSet, PoseJointObservation


_LIMB_JOINTS = frozenset(
    f"{joint}.{side}"
    for joint in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")
    for side in ("left", "right")
)


class PoseAlphaLimbProvider:
    provider_id = "pose-alpha-limb-fusion"
    # Version 2 pins the stage-scoped input identity.  Version 1 included the
    # final resolved snapshot and therefore formed a decision/analysis loop.
    provider_version = "2"

    def __init__(
        self,
        layer_assets: Mapping[str, Path],
        observations: PoseObservationSet,
        *,
        alpha_threshold: int = 8,
        max_snap_ratio: float = 0.04,
        alpha_pull: float = 0.35,
        visible_threshold: float = 0.5,
    ) -> None:
        if not isinstance(alpha_threshold, int) or not 1 <= alpha_threshold <= 255:
            raise ValueError("alpha_threshold must lie in [1, 255]")
        for label, value in (
            ("max_snap_ratio", max_snap_ratio),
            ("alpha_pull", alpha_pull),
            ("visible_threshold", visible_threshold),
        ):
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{label} must lie in [0, 1]")
        self.layer_assets = {str(key): Path(value) for key, value in layer_assets.items()}
        self.observations = observations
        self.config = {
            "alpha_threshold": alpha_threshold,
            "max_snap_ratio": float(max_snap_ratio),
            "alpha_pull": float(alpha_pull),
            "visible_threshold": float(visible_threshold),
            "component_min_area": 16,
            "component_min_ratio": 0.001,
        }

    def analyze(self, project: Mapping[str, Any]) -> dict[str, Any]:
        project_id = str(project.get("id") or "")
        canvas = project.get("canvas") or {}
        width, height = int(canvas.get("width", 0)), int(canvas.get("height", 0))
        if (
            project_id != self.observations.project_id
            or (width, height) != self.observations.canvas_size
            or width < 1
            or height < 1
        ):
            raise LimbCandidateError("Pose observations do not match the project")
        source = project.get("source") or {}
        source_sha = required_sha256(source.get("sha256"), "source image")
        audit_sha = required_sha256(source.get("audit_sha256"), "audit")
        evidence = load_limb_evidence(
            project,
            self.layer_assets,
            (width, height),
            self.config,
        )
        run = candidate_run_identity(
            project,
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            config=self.config,
            evidence_identity={
                "pose_observations_sha256": self.observations.document_sha256,
                "layers": list(evidence.identity_summaries),
            },
        )
        joints: dict[str, Any] = {}
        document_flags = {"FUSION_PROVIDER_REQUIRES_REVIEW", "HEURISTIC_SCORE_NOT_CALIBRATED"}
        document_flags.update(evidence.flags)
        skeleton_joints = (project.get("skeleton") or {}).get("joints", [])
        for joint in skeleton_joints:
            if not isinstance(joint, Mapping) or not isinstance(joint.get("id"), str):
                continue
            joint_id = joint["id"]
            if joint_id not in _LIMB_JOINTS:
                joints[joint_id] = fallback_joint(joint, run["run_sha256"], requires_pose=False)
                continue
            observation = self.observations.joints.get(joint_id)
            if observation is None:
                document_flags.add("MISSING_POSE_OBSERVATION")
                joints[joint_id] = fallback_joint(joint, run["run_sha256"], requires_pose=True)
                continue
            item, flags = self._fuse_joint(
                joint_id,
                observation,
                evidence,
                run["run_sha256"],
                math.hypot(width, height),
            )
            joints[joint_id] = item
            document_flags.update(flags)
        if self.observations.detected_count > 1:
            document_flags.add("MULTIPLE_SUBJECTS_SELECTED_UPSTREAM")
        return {
            "format": "autospine-joint-candidates",
            "format_version": 1,
            "project_id": project_id,
            "source": {
                "base_project_sha256": run["input_sha256"],
                "source_image_sha256": source_sha,
                "audit_sha256": audit_sha,
            },
            "analysis": {
                "provider": self.provider_id,
                "provider_version": self.provider_version,
                "config_sha256": run["config_sha256"],
                "run_sha256": run["run_sha256"],
            },
            "coordinate_system": {
                "origin": "top_left",
                "x_axis": "right",
                "y_axis": "down",
                "units": "pixel",
                "side_naming": "character_side",
            },
            "joints": joints,
            "qa": {"status": "manual_required", "flags": sorted(document_flags)},
        }

    def _fuse_joint(
        self,
        joint_id: str,
        observation: PoseJointObservation,
        evidence: LimbEvidenceSet,
        run_sha: str,
        canvas_diagonal: float,
    ) -> tuple[dict[str, Any], set[str]]:
        joint_name, side = joint_id.split(".", 1)
        layer_by_id = evidence.layers_by_id
        flags = {"SIDE_CONVENTION_AMBIGUOUS"}
        score = pose_score(observation)
        pose_flags = {"DETECTOR_SCORE_NOT_CALIBRATED"}
        if observation.visibility != "visible":
            pose_flags.add("POSE_NOT_FULLY_VISIBLE")
        raw_candidate = pose_candidate(
            joint_id,
            observation,
            score,
            run_sha,
            self.observations.document_sha256,
            pose_flags,
        )
        hits, empty_layers = evidence.alpha_hits(
            joint_name, observation.x, observation.y,
            component_min_area=int(self.config["component_min_area"]),
            component_min_ratio=float(self.config["component_min_ratio"]),
        )
        if empty_layers:
            flags.add("EMPTY_LIMB_LAYER")
        if not hits:
            flags.add("NO_RELEVANT_ALPHA_LAYER")
            raw_candidate["qa_flags"] = sorted(set(raw_candidate["qa_flags"]) | flags)
            return {"observability": "ambiguous", "candidates": [raw_candidate]}, flags

        hit, layer_id = min(hits, key=lambda item: (item[0].distance_px, item[1]))
        selected_layer = layer_by_id[layer_id]
        selected_role = str(selected_layer.get("canonical_role") or "")
        pelvis_only = (
            joint_name == "hip"
            and "pelvis" in selected_role
            and not evidence.has_geometry_role_token("leg")
        )
        if pelvis_only:
            flags.add("OCCLUDED_JOINT")
        layer_side = str(selected_layer.get("side") or "unknown")
        if layer_side in {"left", "right"} and layer_side != side:
            flags.add("OPPOSITE_SIDE_LAYER_SELECTED")
        max_snap = max(4.0, canvas_diagonal * float(self.config["max_snap_ratio"]))
        if hit.distance_px > max_snap:
            flags.add("ALPHA_SNAP_OUTLIER")
            raw_candidate["qa_flags"] = sorted(set(raw_candidate["qa_flags"]) | flags)
            observability = (
                "occluded"
                if pelvis_only or observation.visibility == "occluded"
                else "ambiguous"
            )
            return {"observability": observability, "candidates": [raw_candidate]}, flags

        support = max(0.0, 1.0 - hit.distance_px / max_snap)
        pull = float(self.config["alpha_pull"]) * support
        fused_xy = [
            observation.x + (hit.xy[0] - observation.x) * pull,
            observation.y + (hit.xy[1] - observation.y) * pull,
        ]
        fused_score = max(0.0, min(1.0, score * (0.6 + 0.4 * support)))
        fused_flags = set(flags) | {"SOFT_ALPHA_CONSTRAINT"}
        candidate = {
            "candidate_id": f"{joint_id}.fusion.{run_sha[:12]}",
            "xy": [round(fused_xy[0], 6), round(fused_xy[1], 6)],
            "method": "fusion",
            "score_kind": "heuristic",
            "heuristic_score": round(fused_score, 6),
            "source_layer_ids": [layer_id],
            "evidence": [
                {
                    "kind": "pose_heatmap",
                    "source_ref": f"pose-observations:{self.observations.document_sha256}",
                    "note": (
                        f"Detector-native score={observation.detector_score:.6f}; "
                        "used only as an uncalibrated ranking signal."
                    ),
                },
                {
                    "kind": "layer_alpha",
                    "source_ref": f"{layer_id}:component:{hit.component_id}",
                    "note": (
                        f"Soft alpha support distance={hit.distance_px:.3f}px; "
                        f"component_area={hit.component_area}; ratio={hit.component_area_ratio:.6f}."
                    ),
                },
            ],
            "qa_flags": sorted(fused_flags),
        }
        raw_candidate["qa_flags"] = sorted(set(raw_candidate["qa_flags"]) | flags)
        if pelvis_only:
            candidate["qa_flags"] = sorted(fused_flags)
        visible = (
            not pelvis_only
            and observation.visibility == "visible"
            and fused_score >= self.config["visible_threshold"]
        )
        return {
            "observability": "visible" if visible else ("occluded" if pelvis_only else "ambiguous"),
            "candidates": [candidate, raw_candidate],
        }, fused_flags
