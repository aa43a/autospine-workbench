"""Contract-shaped pose-conditioned alpha path evidence."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from .alpha_paths import AlphaPathResult, trace_alpha_clearance_path
from .limb_evidence_layers import LimbEvidenceSet
from .limb_geometry_matching import (
    ANCHOR_NAMES,
    CHAIN_JOINTS,
    SIDES,
    assign_layer_components,
    chain_anchors,
    geometry_config,
    path_layers,
    side_observation_status,
    significant_components,
)
from .pose_observations import PoseObservationSet


@dataclass(frozen=True, slots=True)
class PathSections:
    paths: list[dict[str, Any]]
    joint_states: dict[str, dict[str, Any]]
    qa_flags: set[str]


@dataclass(slots=True)
class _Candidate:
    payload: dict[str, Any]
    rank: tuple[Any, ...]
    preferred_quality: bool


def analyze_limb_paths(
    evidence: LimbEvidenceSet,
    observations: PoseObservationSet,
    canvas_size: tuple[int, int],
    config: Mapping[str, Any],
) -> PathSections:
    settings = geometry_config(config)
    diagonal = math.hypot(*canvas_size)
    candidates: dict[tuple[str, str], list[_Candidate]] = {}
    group_flags: dict[tuple[str, str], set[str]] = {}
    qa_flags: set[str] = set()
    for chain in sorted(CHAIN_JOINTS):
        anchors_by_side = {
            side: anchors
            for side in SIDES
            if (anchors := chain_anchors(observations, chain, side)) is not None
        }
        assignments = _layer_assignments(
            evidence, chain, anchors_by_side, diagonal, settings
        )
        for side in SIDES:
            group = (chain, side)
            candidates[group], group_flags[group] = _analyze_side(
                evidence,
                observations,
                chain,
                side,
                anchors_by_side.get(side),
                assignments,
                diagonal,
                settings,
            )
            qa_flags.update(group_flags[group])
    paths: list[dict[str, Any]] = []
    joint_states: dict[str, dict[str, Any]] = {}
    for chain, side in sorted(candidates):
        group_candidates = candidates[(chain, side)]
        limb_id = f"{chain}.{side}"
        group_candidates.sort(
            key=lambda item: (item.payload["layer_id"], item.payload["component_id"])
        )
        for index, candidate in enumerate(group_candidates):
            candidate.payload["path_id"] = f"{limb_id}.path.{index:03d}"
        valid = [item for item in group_candidates if item.payload["status"] == "valid"]
        preferred = min(valid, key=lambda item: item.rank) if valid else None
        if preferred is not None:
            preferred.payload["flags"] = sorted(set(preferred.payload["flags"]) | {"PATH_PREFERRED"})
        if len(group_candidates) > 1:
            group_flags[(chain, side)].add("MULTIPLE_ALPHA_PATH_CANDIDATES")
        refs = sorted(item.payload["path_id"] for item in group_candidates)
        selected_flags = set(preferred.payload["flags"]) if preferred else set()
        for joint_name in CHAIN_JOINTS[chain]:
            joint_id = f"{joint_name}.{side}"
            flags = set(group_flags[(chain, side)])
            status = side_observation_status(observations, joint_id)
            if preferred is None and status != "absent":
                status = "ambiguous"
            if "BILATERAL_FUSED_COMPONENT" in selected_flags:
                status = "merged"
                flags.add("BILATERAL_FUSED_COMPONENT")
            elif not preferred or not preferred.preferred_quality:
                if status == "visible":
                    status = "ambiguous"
            joint_states[joint_id] = {
                "status": status,
                "path_ids": refs,
                "flags": sorted(flags),
            }
        paths.extend(item.payload for item in group_candidates)
    for flags in group_flags.values():
        qa_flags.update(flags)
    return PathSections(
        sorted(paths, key=lambda item: item["path_id"]),
        dict(sorted(joint_states.items())),
        qa_flags,
    )


def _layer_assignments(
    evidence: LimbEvidenceSet,
    chain: str,
    anchors_by_side: Mapping[str, Mapping[str, tuple[float, float]]],
    diagonal: float,
    config: Mapping[str, int | float],
) -> dict[str, Any]:
    assignments: dict[str, Any] = {}
    seen: set[str] = set()
    for side in SIDES:
        for layer_id, layer, geometry in path_layers(evidence, chain, side):
            if layer_id in seen or layer.get("side") not in {"bilateral", "unknown"}:
                continue
            seen.add(layer_id)
            component_ids = significant_components(geometry, config)
            assignments[layer_id] = assign_layer_components(
                geometry,
                anchors_by_side,
                component_ids,
                diagonal,
                float(config["component_assignment_margin_ratio"]),
            )
    return assignments


def _analyze_side(
    evidence: LimbEvidenceSet,
    observations: PoseObservationSet,
    chain: str,
    side: str,
    anchors: Mapping[str, tuple[float, float]] | None,
    assignments: Mapping[str, Any],
    diagonal: float,
    config: Mapping[str, int | float],
) -> tuple[list[_Candidate], set[str]]:
    flags: set[str] = set()
    if anchors is None:
        flags.add("CHAIN_POSE_INCOMPLETE")
        return [], flags
    layers = path_layers(evidence, chain, side)
    if not layers:
        flags.add("NO_RELEVANT_ALPHA_LAYER")
        if chain == "leg":
            flags.add("NO_LEG_SEMANTIC_LAYER")
        return [], flags
    result: list[_Candidate] = []
    joint_ids = [f"{joint}.{side}" for joint in CHAIN_JOINTS[chain]]
    for layer_id, layer, geometry in layers:
        component_ids = significant_components(geometry, config)
        assignment = assignments.get(layer_id)
        layer_flags: set[str] = set()
        if assignment is not None:
            assigned = assignment.components.get(side)
            component_ids = [assigned] if assigned is not None else component_ids
            if assignment.fused:
                layer_flags.add("BILATERAL_FUSED_COMPONENT")
            if assignment.ambiguous:
                layer_flags.add("BILATERAL_COMPONENT_ASSIGNMENT_AMBIGUOUS")
            if assignment.excess:
                layer_flags.add("EXCESS_LIMB_COMPONENTS")
        if layer.get("side") == "unknown":
            layer_flags.add("UNKNOWN_SIDE_LAYER")
        for component_id in component_ids:
            alpha_result = trace_alpha_clearance_path(
                geometry.canvas_runs(component_id),
                anchors,
                max_raster_pixels=int(config["max_raster_pixels"]),
                max_search_nodes=int(config["max_search_nodes"]),
            )
            candidate = _path_candidate(
                f"{chain}.{side}", joint_ids, layer_id, component_id,
                anchors, alpha_result, diagonal, config, layer_flags,
                side_priority=_side_priority(layer.get("side"), side),
            )
            result.append(candidate)
            flags.update(set(candidate.payload["flags"]) - {"CHAMFER_CLEARANCE_APPROXIMATION"})
    return result, flags


def _path_candidate(
    limb_id: str,
    joint_ids: list[str],
    layer_id: str,
    component_id: int,
    inputs: Mapping[str, tuple[float, float]],
    result: AlphaPathResult,
    diagonal: float,
    config: Mapping[str, int | float],
    initial_flags: set[str],
    *,
    side_priority: int,
) -> _Candidate:
    flags = set(result.flags) | set(initial_flags)
    anchors = _anchor_payload(joint_ids, inputs, result)
    status = "valid" if result.length_px is not None else "unavailable"
    preferred_quality = False
    rms_ratio = max_ratio = float("inf")
    detour = float("inf")
    if status == "valid":
        residuals = [item.residual_px for item in result.projected_anchors.values()]
        rms_ratio = math.sqrt(sum(value * value for value in residuals) / 3) / diagonal
        max_ratio = max(residuals) / diagonal
        pose_length = math.dist(inputs["proximal"], inputs["hinge"]) + math.dist(inputs["hinge"], inputs["distal"])
        detour = result.length_px / pose_length if pose_length > 0 else float("inf")
        rejected = (
            rms_ratio > config["path_reject_rms_ratio"]
            or max_ratio > config["path_reject_max_ratio"]
            or not config["path_reject_length_min"] <= detour <= config["path_reject_length_max"]
        )
        if rejected:
            flags.add("ALPHA_PATH_QUALITY_REJECTED")
            status = "unavailable"
        else:
            if rms_ratio > config["path_preferred_rms_ratio"] or max_ratio > config["path_preferred_max_ratio"]:
                flags.add("HIGH_ALPHA_PATH_RESIDUAL")
            if not config["path_preferred_length_min"] <= detour <= config["path_preferred_length_max"]:
                flags.add("ALPHA_PATH_DETOUR_OUTLIER")
            if result.median_clearance_px < config["path_min_median_clearance"]:
                flags.add("LOW_PATH_CLEARANCE")
            preferred_quality = not flags.intersection({
                "HIGH_ALPHA_PATH_RESIDUAL", "ALPHA_PATH_DETOUR_OUTLIER", "LOW_PATH_CLEARANCE",
                "BILATERAL_COMPONENT_ASSIGNMENT_AMBIGUOUS", "UNKNOWN_SIDE_LAYER",
            })
    payload = {
        "path_id": "pending",
        "limb_id": limb_id,
        "status": status,
        "joint_ids": joint_ids,
        "layer_id": layer_id,
        "component_id": component_id,
        "anchors": anchors,
        "polyline_xy": [list(point) for point in result.polyline_xy] if status == "valid" else [],
        "length_px": result.length_px if status == "valid" else None,
        "min_clearance_px": result.min_clearance_px if status == "valid" else None,
        "median_clearance_px": result.median_clearance_px if status == "valid" else None,
        "hinge_candidate_xy": list(result.hinge_candidate_xy) if status == "valid" else None,
        "error_radius_px": result.error_radius_px if status == "valid" else None,
        "budgets": {
            "max_raster_pixels": int(config["max_raster_pixels"]),
            "max_search_nodes": int(config["max_search_nodes"]),
            "raster_pixels": result.raster_pixels,
            "search_nodes": result.search_nodes,
        },
        "flags": sorted(flags),
    }
    rank = (side_priority, rms_ratio, abs(detour - 1), -float(result.median_clearance_px or 0), layer_id, component_id)
    return _Candidate(payload, rank, preferred_quality)


def _anchor_payload(joint_ids, inputs, result: AlphaPathResult) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for name, joint_id in zip(ANCHOR_NAMES, joint_ids):
        projected = result.projected_anchors.get(name)
        payload[name] = {
            "joint_id": joint_id,
            "input_xy": list(inputs[name]),
            "projected_xy": list(projected.xy) if projected else None,
            "residual_px": projected.residual_px if projected else None,
        }
    return payload


def _side_priority(layer_side: Any, side: str) -> int:
    return 0 if layer_side == side else (1 if layer_side == "bilateral" else 2)
