"""Pose-cost matching shared by alpha path and contact analysis."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable, Mapping, Sequence

from .alpha_geometry import AlphaGeometry
from .limb_evidence_layers import LimbEvidenceSet
from .pose_observations import PoseObservationSet


SIDES = ("left", "right")
ANCHOR_NAMES = ("proximal", "hinge", "distal")
CHAIN_JOINTS = {
    "arm": ("shoulder", "elbow", "wrist"),
    "leg": ("hip", "knee", "ankle"),
}
CHAIN_ROLE_TOKENS = {"arm": ("arm", "hand"), "leg": ("leg",)}
DEFAULT_GEOMETRY_CONFIG: dict[str, int | float] = {
    "component_min_area": 16,
    "component_min_ratio": 0.001,
    "max_raster_pixels": 400_000,
    "max_search_nodes": 250_000,
    "component_assignment_margin_ratio": 0.01,
    "path_preferred_rms_ratio": 0.03,
    "path_preferred_max_ratio": 0.05,
    "path_reject_rms_ratio": 0.06,
    "path_reject_max_ratio": 0.08,
    "path_preferred_length_min": 0.75,
    "path_preferred_length_max": 1.35,
    "path_reject_length_min": 0.55,
    "path_reject_length_max": 1.75,
    "path_min_median_clearance": 2.0,
    "contact_max_gap_ratio": 0.01,
    "contact_max_gap_px": 32.0,
    "contact_assignment_margin_ratio": 0.015,
    "pelvis_leg_reject_overlap_ratio": 0.25,
    "pelvis_leg_reject_height_ratio": 0.35,
    "pelvis_leg_warn_overlap_ratio": 0.10,
    "pelvis_leg_warn_height_ratio": 0.20,
}
_REMOVED_CONTACT_CONFIG = frozenset({
    "contact_assigned_max_ratio",
    "contact_anchor_max_ratio",
    "contact_error_radius_ratio",
    "pelvis_leg_anchor_max_ratio",
})


@dataclass(frozen=True, slots=True)
class SideAssignment:
    components: Mapping[str, int]
    costs_px: Mapping[str, Mapping[int, float]]
    fused: bool
    ambiguous: bool
    excess: bool
    margin_ratio: float | None


@dataclass(frozen=True, slots=True)
class ContactSiteAssignment:
    primary: Mapping[str, Any]
    extras: tuple[tuple[Any, str], ...]
    margin_ratio: float | None


def geometry_config(overrides: Mapping[str, Any]) -> dict[str, int | float]:
    """Normalize known numeric settings while ignoring unrelated provider keys."""

    removed = sorted(_REMOVED_CONTACT_CONFIG.intersection(overrides))
    if removed:
        raise ValueError(f"unsupported contact geometry settings: {', '.join(removed)}")
    result = dict(DEFAULT_GEOMETRY_CONFIG)
    for key in result:
        if key in overrides:
            result[key] = overrides[key]
    for key in ("component_min_area", "max_raster_pixels", "max_search_nodes"):
        value = result[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{key} must be a positive integer")
    for key, value in result.items():
        if key in {"component_min_area", "max_raster_pixels", "max_search_nodes"}:
            continue
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"{key} must be a finite non-negative number")
        result[key] = float(value)
    if result["path_preferred_rms_ratio"] > result["path_reject_rms_ratio"]:
        raise ValueError("preferred RMS threshold cannot exceed reject threshold")
    if result["path_preferred_max_ratio"] > result["path_reject_max_ratio"]:
        raise ValueError("preferred max-residual threshold cannot exceed reject threshold")
    return result


def chain_anchors(
    observations: PoseObservationSet, chain: str, side: str
) -> dict[str, tuple[float, float]] | None:
    points: dict[str, tuple[float, float]] = {}
    for anchor_name, joint_name in zip(ANCHOR_NAMES, CHAIN_JOINTS[chain]):
        observation = observations.joints.get(f"{joint_name}.{side}")
        if observation is None:
            return None
        points[anchor_name] = (observation.x, observation.y)
    return points


def path_layers(
    evidence: LimbEvidenceSet, chain: str, side: str
) -> list[tuple[str, Mapping[str, Any], AlphaGeometry]]:
    result: list[tuple[str, Mapping[str, Any], AlphaGeometry]] = []
    for layer_id, geometry in evidence.geometries.items():
        layer = evidence.layers_by_id[layer_id]
        role = _role(str(layer.get("canonical_role") or ""))
        if (
            any(token in role for token in CHAIN_ROLE_TOKENS[chain])
            and layer.get("side") in {side, "bilateral", "unknown"}
        ):
            result.append((layer_id, layer, geometry))
    return sorted(result, key=lambda item: item[0])


def significant_components(
    geometry: AlphaGeometry, config: Mapping[str, int | float]
) -> list[int]:
    return sorted(geometry.significant_component_ids(
        min_area=int(config["component_min_area"]),
        min_area_ratio=float(config["component_min_ratio"]),
    ))


def assign_layer_components(
    geometry: AlphaGeometry,
    anchors_by_side: Mapping[str, Mapping[str, tuple[float, float]]],
    component_ids: Sequence[int],
    canvas_diagonal: float,
    margin_ratio: float,
) -> SideAssignment:
    costs = {
        side: {
            component_id: _component_cost(geometry, component_id, list(anchors.values()))
            for component_id in component_ids
        }
        for side, anchors in anchors_by_side.items()
    }
    if len(costs) < 2 or not component_ids:
        return SideAssignment({}, costs, False, False, len(component_ids) > 2, None)
    if len(component_ids) == 1:
        component_id = component_ids[0]
        return SideAssignment(
            {side: component_id for side in SIDES}, costs, True, False, False, None
        )
    assignment, margin = assign_unique_sites(costs, canvas_diagonal)
    return SideAssignment(
        assignment,
        costs,
        False,
        margin is not None and margin < margin_ratio,
        len(component_ids) > 2,
        margin,
    )


def assign_unique_sites(
    costs: Mapping[str, Mapping[Any, float]], canvas_diagonal: float
) -> tuple[dict[str, Any], float | None]:
    """Assign distinct sites to character sides using costs only, never screen x."""

    if any(side not in costs or not costs[side] for side in SIDES):
        return {}, None
    right_order = sorted(costs["right"], key=lambda site: (costs["right"][site], str(site)))
    candidates: list[tuple[float, str, str, Any, Any]] = []
    for left_site in sorted(costs["left"], key=str):
        alternatives = [site for site in right_order if site != left_site][:2]
        for right_site in alternatives:
            total = costs["left"][left_site] + costs["right"][right_site]
            candidates.append((total, str(left_site), str(right_site), left_site, right_site))
    if not candidates:
        return {}, None
    candidates.sort()
    best = candidates[0]
    margin = None
    if len(candidates) > 1 and canvas_diagonal > 0:
        margin = round((candidates[1][0] - best[0]) / canvas_diagonal, 8)
    return {"left": best[3], "right": best[4]}, margin


def assign_contact_sites(
    costs: Mapping[str, Mapping[Any, float]],
    sites: Sequence[Any],
    canvas_diagonal: float,
    *,
    site_key: Callable[[Any], Any] = str,
) -> ContactSiteAssignment:
    """Assign primary distinct sites, then associate each remaining site once."""

    primary, margin = assign_unique_sites(costs, canvas_diagonal)
    if not primary:
        options = (
            (costs[side][site], side, site_key(site), site)
            for site in sites
            for side in sorted(costs)
            if site in costs[side]
        )
        try:
            _, side, _, site = min(options)
        except ValueError:
            return ContactSiteAssignment({}, (), margin)
        primary = {side: site}
    used = set(primary.values())
    extras: list[tuple[Any, str]] = []
    for site in sites:
        if site in used:
            continue
        available = [side for side in sorted(costs) if site in costs[side]]
        side = min(available, key=lambda value: (costs[value][site], value))
        extras.append((site, side))
    return ContactSiteAssignment(primary, tuple(extras), margin)


def side_observation_status(observations: PoseObservationSet, joint_id: str) -> str:
    item = observations.joints.get(joint_id)
    if item is None or item.visibility == "out_of_frame":
        return "absent"
    if item.visibility == "occluded":
        return "occluded"
    return "visible" if item.visibility == "visible" else "ambiguous"


def _component_cost(
    geometry: AlphaGeometry, component_id: int, anchors: list[tuple[float, float]]
) -> float:
    allowed = frozenset({component_id})
    distances = [
        geometry.nearest_foreground(x, y, component_ids=allowed).distance_px
        for x, y in anchors
    ]
    return round(math.sqrt(sum(value * value for value in distances) / len(distances)), 6)


def _role(value: str) -> str:
    return value.replace("-", "_").split(".")[-1]
