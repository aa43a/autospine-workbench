"""Build deterministic alpha geometry evidence documents from analyzed sections."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .alpha_evidence_validation import require_valid_alpha_geometry_evidence
from .candidate_provenance import required_sha256
from .limb_evidence_layers import LimbEvidenceSet
from .pose_observations import PoseObservationSet
from .resolved_project import canonical_sha256


PROVIDER_ID = "pose-alpha-geometry"
PROVIDER_VERSION = "1"
_COORDINATE_SYSTEM = {
    "origin": "top_left",
    "x_axis": "right",
    "y_axis": "down",
    "units": "pixel",
    "side_naming": "character_side",
}


def build_alpha_geometry_evidence(
    project: Mapping[str, Any],
    evidence: LimbEvidenceSet,
    observations: PoseObservationSet,
    sections: Any,
    *,
    config: Mapping[str, Any],
    provider_id: str = PROVIDER_ID,
    provider_version: str = PROVIDER_VERSION,
) -> dict[str, Any]:
    """Materialize and semantically validate one content-addressable artifact."""

    project_id = str(project.get("id") or "")
    canvas = project.get("canvas") or {}
    width, height = int(canvas.get("width", 0)), int(canvas.get("height", 0))
    if (
        project_id != observations.project_id
        or (width, height) != observations.canvas_size
        or width < 1
        or height < 1
    ):
        raise ValueError("Pose observations do not match the geometry project")
    source_project = project.get("source") or {}
    source = {
        "base_project_sha256": _base_project_sha256(project),
        "source_image_sha256": required_sha256(source_project.get("sha256"), "source image"),
        "audit_sha256": required_sha256(source_project.get("audit_sha256"), "audit"),
        "pose_observations_sha256": required_sha256(
            observations.document_sha256, "pose observations"
        ),
    }
    layers = _layer_summaries(evidence)
    input_sha = canonical_sha256(
        {"project_id": project_id, "source": source, "layers": layers}
    )
    config_sha = canonical_sha256(config)
    run_sha = canonical_sha256(
        {
            "input_sha256": input_sha,
            "provider": provider_id,
            "provider_version": provider_version,
            "config_sha256": config_sha,
        }
    )
    analyzed = _sections_mapping(sections)
    qa_flags = analyzed.get("qa_flags", [])
    if not isinstance(qa_flags, (list, tuple)) or any(
        not isinstance(item, str) or not item for item in qa_flags
    ):
        raise ValueError("Geometry section QA flags must be non-empty strings")
    document = {
        "format": "autospine-alpha-geometry-evidence",
        "format_version": 1,
        "project_id": project_id,
        "source": source,
        "analysis": {
            "provider": provider_id,
            "provider_version": provider_version,
            "input_sha256": input_sha,
            "config_sha256": config_sha,
            "run_sha256": run_sha,
        },
        "coordinate_system": dict(_COORDINATE_SYSTEM),
        "layers": layers,
        "paths": deepcopy(analyzed.get("paths", [])),
        "contacts": deepcopy(analyzed.get("contacts", [])),
        "observability": dict(sorted(deepcopy(analyzed.get("observability", {})).items())),
        "qa": {
            "status": "manual_required",
            "flags": sorted(set(qa_flags) | {"GEOMETRY_EVIDENCE_REQUIRES_REVIEW"}),
        },
    }
    require_valid_alpha_geometry_evidence(
        document,
        project_id=project_id,
        joint_ids={item["id"] for item in (project.get("skeleton") or {}).get("joints", [])},
        layer_ids={str(item.get("id")) for item in evidence.effective_layers},
        canvas_width=width,
        canvas_height=height,
    )
    return document


def _base_project_sha256(project: Mapping[str, Any]) -> str:
    """Hash stage inputs while intentionally excluding final review decisions."""

    return canonical_sha256(
        {
            "project_id": project.get("id"),
            "source": project.get("source"),
            "canvas": project.get("canvas"),
            "skeleton": project.get("skeleton"),
        }
    )


def _layer_summaries(evidence: LimbEvidenceSet) -> list[dict[str, Any]]:
    identity = {item["layer_id"]: item for item in evidence.identity_summaries}
    result: list[dict[str, Any]] = []
    for layer_id in sorted(evidence.geometries):
        geometry = evidence.geometries[layer_id]
        layer = evidence.layers_by_id[layer_id]
        summary = identity[layer_id]
        result.append(
            {
                "layer_id": layer_id,
                "raster_sha256": summary["asset_sha256"],
                "canonical_role": str(layer.get("canonical_role") or ""),
                "side": str(layer.get("side") or "unknown"),
                "disposition": str(layer.get("disposition") or "auto"),
                "alpha_threshold": geometry.threshold,
                "foreground_area": geometry.foreground_area,
                "components": [
                    {
                        "component_id": item.component_id,
                        "area": item.area,
                        "bbox_xywh": list(item.bbox_xywh),
                    }
                    for item in sorted(geometry.components, key=lambda value: value.component_id)
                ],
            }
        )
    return result


def _sections_mapping(sections: Any) -> Mapping[str, Any]:
    value = sections.to_dict() if hasattr(sections, "to_dict") else sections
    if not isinstance(value, Mapping):
        raise ValueError("Geometry sections must be a mapping or expose to_dict()")
    return value
