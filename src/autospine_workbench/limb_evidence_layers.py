"""Effective limb-layer selection, alpha loading, and semantic matching."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .alpha_geometry import AlphaGeometry, AlphaHit, analyze_alpha_png
from .candidate_provenance import sha256_file
from .png_rgba import RgbaPngError


_LIMB_ROLE_TOKENS = ("arm", "hand", "leg", "foot", "pelvis")
_CONTACT_REFERENCE_ROLE_TOKENS = ("torso",)
_JOINT_ROLE_TOKENS = {
    "shoulder": ("arm", "hand"),
    "elbow": ("arm", "hand"),
    "wrist": ("arm", "hand"),
    "hip": ("pelvis", "leg"),
    "knee": ("leg",),
    "ankle": ("leg", "foot"),
}


class LimbCandidateError(ValueError):
    """Raised when alpha/pose evidence cannot be fused without guessing."""


@dataclass(frozen=True, slots=True)
class LimbEvidenceSet:
    effective_layers: tuple[Mapping[str, Any], ...]
    identity_summaries: tuple[dict[str, Any], ...]
    geometries: Mapping[str, AlphaGeometry]
    layers_by_id: Mapping[str, Mapping[str, Any]]
    flags: frozenset[str]

    def alpha_hits(
        self,
        joint_name: str,
        x: float,
        y: float,
        *,
        component_min_area: int,
        component_min_ratio: float,
    ) -> tuple[list[tuple[AlphaHit, str]], bool]:
        """Return matching significant-component hits and an empty-layer signal."""

        hits: list[tuple[AlphaHit, str]] = []
        empty_layers = False
        for layer_id, geometry in self.geometries.items():
            role = str(self.layers_by_id[layer_id].get("canonical_role") or "")
            if not joint_role_matches(joint_name, role):
                continue
            significant = geometry.significant_component_ids(
                min_area=component_min_area,
                min_area_ratio=component_min_ratio,
            )
            if not significant:
                empty_layers = True
                continue
            hit = geometry.nearest_foreground(x, y, component_ids=significant)
            if hit is not None:
                hits.append((hit, layer_id))
        return hits, empty_layers

    def has_geometry_role_token(self, token: str) -> bool:
        return any(
            token in str(self.layers_by_id[layer_id].get("canonical_role") or "")
            for layer_id in self.geometries
        )


def load_limb_evidence(
    project: Mapping[str, Any],
    layer_assets: Mapping[str, Path],
    canvas_size: tuple[int, int],
    config: Mapping[str, Any],
    *,
    include_contact_roles: bool = False,
) -> LimbEvidenceSet:
    """Load alpha geometry and the exact summaries consumed by run identity."""

    if not isinstance(include_contact_roles, bool):
        raise ValueError("include_contact_roles must be boolean")
    layers = effective_layers(project)
    evidence: list[dict[str, Any]] = []
    geometries: dict[str, AlphaGeometry] = {}
    layer_by_id = {str(layer.get("id")): layer for layer in layers}
    for layer in layers:
        layer_id = str(layer.get("id") or "")
        role = str(layer.get("canonical_role") or "")
        selected_role = is_limb_role(role) or (
            include_contact_roles and is_contact_reference_role(role)
        )
        if not selected_role or is_excluded_layer(layer):
            continue
        asset_value = layer_assets.get(layer_id)
        asset = Path(asset_value) if asset_value is not None else None
        if asset is None or not asset.is_file():
            raise LimbCandidateError(f"Limb layer asset is missing: {layer_id}")
        bbox = layer.get("bbox") or {}
        offset = (int(bbox.get("x", 0)), int(bbox.get("y", 0)))
        try:
            geometry = analyze_alpha_png(
                asset,
                canvas_offset_xy=offset,
                threshold=int(config["alpha_threshold"]),
            )
            if (geometry.width, geometry.height) == canvas_size:
                geometry = analyze_alpha_png(
                    asset,
                    canvas_offset_xy=(0, 0),
                    threshold=int(config["alpha_threshold"]),
                )
        except RgbaPngError as exc:
            raise LimbCandidateError(f"Cannot decode limb layer: {layer_id}") from exc
        bbox_size = (int(bbox.get("width", 0)), int(bbox.get("height", 0)))
        if (geometry.width, geometry.height) not in {canvas_size, bbox_size}:
            raise LimbCandidateError(f"Limb layer dimensions do not match bbox: {layer_id}")
        geometries[layer_id] = geometry
        evidence.append(
            {
                "layer_id": layer_id,
                "asset_sha256": sha256_file(asset, "limb layer asset"),
                "canonical_role": role,
                "side": str(layer.get("side") or "unknown"),
                "bbox": dict(bbox),
                "foreground_area": geometry.foreground_area,
                "component_areas": [item.area for item in geometry.components],
            }
        )
    summaries = tuple(sorted(evidence, key=lambda item: item["layer_id"]))
    flags = _geometry_flags(summaries, config)
    return LimbEvidenceSet(
        effective_layers=tuple(layers),
        identity_summaries=summaries,
        geometries=MappingProxyType(geometries),
        layers_by_id=MappingProxyType(layer_by_id),
        flags=frozenset(flags),
    )


def effective_layers(project: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    resolved = project.get("resolved")
    source = resolved if isinstance(resolved, Mapping) else project
    layers = source.get("layers") or []
    return [layer for layer in layers if isinstance(layer, Mapping)]


def is_excluded_layer(layer: Mapping[str, Any]) -> bool:
    return bool(layer.get("empty")) or layer.get("disposition") in {"exclude", "ignore"}


def is_limb_role(role: str) -> bool:
    normalized = _normalized_role(role)
    return any(token in normalized for token in _LIMB_ROLE_TOKENS)


def is_contact_reference_role(role: str) -> bool:
    normalized = _normalized_role(role)
    return any(token in normalized for token in _CONTACT_REFERENCE_ROLE_TOKENS)


def joint_role_matches(joint_name: str, role: str) -> bool:
    normalized = _normalized_role(role)
    return any(token in normalized for token in _JOINT_ROLE_TOKENS[joint_name])


def _normalized_role(role: str) -> str:
    return role.replace("-", "_").split(".")[-1]


def _geometry_flags(
    evidence_layers: tuple[dict[str, Any], ...], config: Mapping[str, Any]
) -> set[str]:
    flags: set[str] = set()
    roles = {_normalized_role(str(item["canonical_role"])) for item in evidence_layers}
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
