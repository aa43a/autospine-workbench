"""Pose-led limb candidates with alpha components as an auditable soft constraint."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

from .alpha_geometry import AlphaGeometry, AlphaHit, analyze_alpha_png
from .candidate_provenance import candidate_run_identity, required_sha256, sha256_file
from .limb_candidate_items import fallback_joint, pose_candidate, pose_score
from .png_rgba import RgbaPngError
from .pose_observations import PoseObservationSet, PoseJointObservation


_LIMB_JOINTS = frozenset(
    f"{joint}.{side}"
    for joint in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")
    for side in ("left", "right")
)
_ROLE_TOKENS = {
    "shoulder": ("arm", "hand"),
    "elbow": ("arm", "hand"),
    "wrist": ("arm", "hand"),
    "hip": ("pelvis", "leg"),
    "knee": ("leg",),
    "ankle": ("leg", "foot"),
}


class LimbCandidateError(ValueError):
    """Raised when alpha/pose evidence cannot be fused without guessing."""


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
        layers = _effective_layers(project)
        evidence_layers, geometries = self._load_evidence_layers(layers, (width, height))
        run = candidate_run_identity(
            project,
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            config=self.config,
            evidence_identity={
                "pose_observations_sha256": self.observations.document_sha256,
                "layers": evidence_layers,
            },
        )
        joints: dict[str, Any] = {}
        document_flags = {"FUSION_PROVIDER_REQUIRES_REVIEW", "HEURISTIC_SCORE_NOT_CALIBRATED"}
        document_flags.update(_geometry_flags(evidence_layers, self.config))
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
                layers,
                geometries,
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

    def _load_evidence_layers(
        self,
        layers: list[Mapping[str, Any]],
        canvas_size: tuple[int, int],
    ) -> tuple[list[dict[str, Any]], dict[str, AlphaGeometry]]:
        evidence: list[dict[str, Any]] = []
        geometries: dict[str, AlphaGeometry] = {}
        for layer in layers:
            layer_id = str(layer.get("id") or "")
            role = str(layer.get("canonical_role") or "")
            if not _is_limb_role(role) or _is_excluded(layer):
                continue
            asset = self.layer_assets.get(layer_id)
            if asset is None or not asset.is_file():
                raise LimbCandidateError(f"Limb layer asset is missing: {layer_id}")
            bbox = layer.get("bbox") or {}
            offset = (int(bbox.get("x", 0)), int(bbox.get("y", 0)))
            try:
                geometry = analyze_alpha_png(
                    asset,
                    canvas_offset_xy=offset,
                    threshold=int(self.config["alpha_threshold"]),
                )
                if (geometry.width, geometry.height) == canvas_size:
                    geometry = analyze_alpha_png(
                        asset,
                        canvas_offset_xy=(0, 0),
                        threshold=int(self.config["alpha_threshold"]),
                    )
            except RgbaPngError as exc:
                raise LimbCandidateError(f"Cannot decode limb layer: {layer_id}") from exc
            bbox_size = (int(bbox.get("width", 0)), int(bbox.get("height", 0)))
            if (geometry.width, geometry.height) not in {canvas_size, bbox_size}:
                raise LimbCandidateError(f"Limb layer dimensions do not match bbox: {layer_id}")
            digest = sha256_file(asset, "limb layer asset")
            geometries[layer_id] = geometry
            evidence.append(
                {
                    "layer_id": layer_id,
                    "asset_sha256": digest,
                    "canonical_role": role,
                    "side": str(layer.get("side") or "unknown"),
                    "bbox": dict(bbox),
                    "foreground_area": geometry.foreground_area,
                    "component_areas": [item.area for item in geometry.components],
                }
            )
        return sorted(evidence, key=lambda item: item["layer_id"]), geometries

    def _fuse_joint(
        self,
        joint_id: str,
        observation: PoseJointObservation,
        layers: list[Mapping[str, Any]],
        geometries: Mapping[str, AlphaGeometry],
        run_sha: str,
        canvas_diagonal: float,
    ) -> tuple[dict[str, Any], set[str]]:
        joint_name, side = joint_id.split(".", 1)
        layer_by_id = {str(layer.get("id")): layer for layer in layers}
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
        hits, empty_layers = self._alpha_hits(
            joint_name,
            observation,
            layer_by_id,
            geometries,
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
        pelvis_only = joint_name == "hip" and "pelvis" in selected_role and not any(
            "leg" in str(layer_by_id[item].get("canonical_role") or "") for item in geometries
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

    def _alpha_hits(
        self,
        joint_name: str,
        observation: PoseJointObservation,
        layer_by_id: Mapping[str, Mapping[str, Any]],
        geometries: Mapping[str, AlphaGeometry],
    ) -> tuple[list[tuple[AlphaHit, str]], bool]:
        hits: list[tuple[AlphaHit, str]] = []
        empty_layers = False
        for layer_id, geometry in geometries.items():
            role = str(layer_by_id[layer_id].get("canonical_role") or "")
            if not _role_matches(joint_name, role):
                continue
            significant = geometry.significant_component_ids(
                min_area=int(self.config["component_min_area"]),
                min_area_ratio=float(self.config["component_min_ratio"]),
            )
            if not significant:
                empty_layers = True
                continue
            hit = geometry.nearest_foreground(
                observation.x,
                observation.y,
                component_ids=significant,
            )
            if hit is not None:
                hits.append((hit, layer_id))
        return hits, empty_layers


def _effective_layers(project: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    resolved = project.get("resolved")
    source = resolved if isinstance(resolved, Mapping) else project
    layers = source.get("layers") or []
    return [layer for layer in layers if isinstance(layer, Mapping)]


def _is_excluded(layer: Mapping[str, Any]) -> bool:
    return bool(layer.get("empty")) or layer.get("disposition") in {"exclude", "ignore"}


def _is_limb_role(role: str) -> bool:
    return any(token in role.replace("-", "_").split(".")[-1] for token in ("arm", "hand", "leg", "foot", "pelvis"))


def _role_matches(joint_name: str, role: str) -> bool:
    normalized = role.replace("-", "_").split(".")[-1]
    return any(token in normalized for token in _ROLE_TOKENS[joint_name])


def _geometry_flags(
    evidence_layers: list[dict[str, Any]], config: Mapping[str, Any]
) -> set[str]:
    flags: set[str] = set()
    roles = {str(item["canonical_role"]).replace("-", "_").split(".")[-1] for item in evidence_layers}
    if not any("leg" in role for role in roles):
        flags.add("NO_LEG_SEMANTIC_LAYER")
    for item in evidence_layers:
        if item["side"] != "bilateral":
            continue
        threshold = max(
            int(config["component_min_area"]),
            math.ceil(item["foreground_area"] * float(config["component_min_ratio"])),
        )
        significant = sum(area >= threshold for area in item["component_areas"])
        if significant == 1:
            flags.add("BILATERAL_FUSED_COMPONENT")
        elif significant > 2:
            flags.add("EXCESS_LIMB_COMPONENTS")
    return flags
