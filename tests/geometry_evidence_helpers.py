"""Small valid alpha-geometry documents shared by repository/API tests."""

from __future__ import annotations

from autospine_workbench.resolved_project import canonical_sha256


def geometry_evidence_document(project_id: str) -> dict:
    source = {
        "base_project_sha256": "a" * 64,
        "source_image_sha256": "b" * 64,
        "audit_sha256": "c" * 64,
    }
    layers: list[dict] = []
    analysis = {
        "provider": "pose-alpha-geometry",
        "provider_version": "1",
        "input_sha256": canonical_sha256(
            {"project_id": project_id, "source": source, "layers": layers}
        ),
        "config_sha256": "d" * 64,
        "run_sha256": "",
    }
    analysis["run_sha256"] = canonical_sha256(
        {
            "input_sha256": analysis["input_sha256"],
            "provider": analysis["provider"],
            "provider_version": analysis["provider_version"],
            "config_sha256": analysis["config_sha256"],
        }
    )
    return {
        "format": "autospine-alpha-geometry-evidence",
        "format_version": 1,
        "project_id": project_id,
        "source": source,
        "analysis": analysis,
        "coordinate_system": {
            "origin": "top_left",
            "x_axis": "right",
            "y_axis": "down",
            "units": "pixel",
            "side_naming": "character_side",
        },
        "layers": layers,
        "paths": [],
        "contacts": [],
        "observability": {},
        "qa": {
            "status": "manual_required",
            "flags": ["GEOMETRY_EVIDENCE_REQUIRES_REVIEW"],
        },
    }
