"""Cross-document validation for candidate references to geometry evidence."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .resolved_project import canonical_sha256


_COMPONENT_ID = re.compile(r"^(0|[1-9][0-9]*)$")
_GEOMETRY_SECTIONS = {
    "layer_alpha": frozenset({"layers", "paths"}),
    "contact_geometry": frozenset({"contacts"}),
    "kinematic_residual": frozenset({"paths"}),
}


def require_geometry_candidate_binding(
    candidates: Mapping[str, Any], geometry: Mapping[str, Any]
) -> str:
    """Validate every geometry source ref and return the pinned geometry SHA."""

    digest = canonical_sha256(geometry)
    prefix = f"alpha-geometry-evidence:{digest}#"
    indexes = _geometry_indexes(geometry)
    for joint_id, joint in candidates["joints"].items():
        for candidate_index, candidate in enumerate(joint["candidates"]):
            for evidence_index, evidence in enumerate(candidate["evidence"]):
                path = (
                    f"{joint_id}.candidates[{candidate_index}]."
                    f"evidence[{evidence_index}].source_ref"
                )
                _require_reference(evidence, prefix, indexes, path)
    return digest


def _geometry_indexes(
    geometry: Mapping[str, Any],
) -> dict[str, Any]:
    layers = {
        layer["layer_id"]: {item["component_id"] for item in layer["components"]}
        for layer in geometry["layers"]
    }
    return {
        "layers": layers,
        "paths": {item["path_id"] for item in geometry["paths"]},
        "contacts": {item["contact_id"] for item in geometry["contacts"]},
    }


def _require_reference(
    evidence: Mapping[str, Any],
    prefix: str,
    indexes: Mapping[str, Any],
    path: str,
) -> None:
    kind = evidence["kind"]
    source_ref = evidence.get("source_ref")
    allowed_sections = _GEOMETRY_SECTIONS.get(kind)
    if allowed_sections is None:
        if isinstance(source_ref, str) and source_ref.startswith(
            "alpha-geometry-evidence:"
        ):
            raise ValueError(f"{path}: evidence kind cannot reference geometry")
        return
    if not isinstance(source_ref, str) or not source_ref.startswith(prefix):
        raise ValueError(f"{path}: geometry SHA does not match the published content")

    parts = source_ref[len(prefix):].split("/")
    section = parts[0] if parts else ""
    if section not in allowed_sections:
        raise ValueError(f"{path}: geometry section is incompatible with evidence kind")
    if section == "layers":
        _require_layer_fragment(parts, indexes["layers"], path)
    elif len(parts) != 2 or parts[1] not in indexes[section]:
        raise ValueError(f"{path}: geometry {section[:-1]} does not exist")


def _require_layer_fragment(
    parts: list[str], layers: Mapping[str, set[int]], path: str
) -> None:
    if len(parts) not in {2, 4} or parts[1] not in layers:
        raise ValueError(f"{path}: geometry layer does not exist")
    if len(parts) == 2:
        return
    component = parts[3]
    if (
        parts[2] != "components"
        or not _COMPONENT_ID.fullmatch(component)
        or int(component) not in layers[parts[1]]
    ):
        raise ValueError(f"{path}: geometry layer component does not exist")
