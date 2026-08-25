"""Joint candidates derived from a pinned pose/alpha geometry artifact."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .alpha_evidence_document import build_alpha_geometry_evidence
from .candidate_provenance import candidate_run_identity
from .candidate_validation import require_valid_candidate_document
from .limb_candidates import PoseAlphaLimbProvider
from .limb_evidence_layers import load_limb_evidence
from .limb_geometry_matching import geometry_config
from .limb_geometry_sections import GeometrySections, analyze_geometry_sections
from .pose_observations import PoseObservationSet
from .resolved_project import canonical_sha256


_POLICY_VERSION = "1"
_METHOD_TOKEN = {
    "audit_bbox_heuristic": "bbox",
    "pose": "pose",
    "fusion": "fusion",
    "medial_axis": "medial",
    "contact": "contact",
}


@dataclass(frozen=True, slots=True)
class PoseGeometryLimbBundle:
    geometry_document: dict[str, Any]
    joint_candidate_document: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return deepcopy({
            "geometry_document": self.geometry_document,
            "joint_candidate_document": self.joint_candidate_document,
        })


class PoseGeometryLimbProvider:
    """Build geometry first, then bind review candidates to its artifact hash."""

    provider_id = "pose-alpha-geometry-limb"
    provider_version = "1"
    geometry_provider_id = "pose-alpha-geometry"
    geometry_provider_version = "1"

    def __init__(
        self,
        layer_assets: Mapping[str, Path],
        observations: PoseObservationSet,
        *,
        alpha_threshold: int = 8,
        max_snap_ratio: float = 0.04,
        alpha_pull: float = 0.35,
        visible_threshold: float = 0.5,
        geometry_overrides: Mapping[str, Any] | None = None,
    ) -> None:
        self.layer_assets = {str(key): Path(value) for key, value in layer_assets.items()}
        self.observations = observations
        self._fusion = PoseAlphaLimbProvider(
            self.layer_assets,
            observations,
            alpha_threshold=alpha_threshold,
            max_snap_ratio=max_snap_ratio,
            alpha_pull=alpha_pull,
            visible_threshold=visible_threshold,
        )
        normalized = geometry_config(dict(geometry_overrides or {}))
        self.geometry_config = {"alpha_threshold": alpha_threshold, **normalized}
        self.candidate_config = {
            "fusion": dict(self._fusion.config),
            "fusion_provider": {
                "id": self._fusion.provider_id,
                "version": self._fusion.provider_version,
            },
            "geometry_candidate_policy_version": _POLICY_VERSION,
            "geometry_provider": {
                "id": self.geometry_provider_id,
                "version": self.geometry_provider_version,
            },
        }

    def analyze(self, project: Mapping[str, Any]) -> PoseGeometryLimbBundle:
        base_candidates = self._fusion.analyze(project)
        canvas_value = project.get("canvas") or {}
        canvas = (int(canvas_value.get("width", 0)), int(canvas_value.get("height", 0)))
        evidence = load_limb_evidence(
            project,
            self.layer_assets,
            canvas,
            self.geometry_config,
            include_contact_roles=True,
        )
        sections = analyze_geometry_sections(
            evidence, self.observations, canvas, self.geometry_config
        )
        geometry_document = build_alpha_geometry_evidence(
            project,
            evidence,
            self.observations,
            sections,
            config=self.geometry_config,
            provider_id=self.geometry_provider_id,
            provider_version=self.geometry_provider_version,
        )
        geometry_sha = canonical_sha256(geometry_document)
        run = candidate_run_identity(
            project,
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            config=self.candidate_config,
            evidence_identity={"alpha_geometry_evidence_sha256": geometry_sha},
        )
        candidate_document = self._candidate_document(
            project, base_candidates, sections, geometry_sha, run
        )
        require_valid_candidate_document(
            candidate_document,
            joint_ids={item["id"] for item in (project.get("skeleton") or {}).get("joints", [])},
            layer_ids={str(item.get("id")) for item in project.get("layers", [])},
            canvas_width=canvas[0],
            canvas_height=canvas[1],
        )
        return PoseGeometryLimbBundle(geometry_document, candidate_document)

    def _candidate_document(
        self,
        project: Mapping[str, Any],
        base: Mapping[str, Any],
        sections: GeometrySections,
        geometry_sha: str,
        run: Mapping[str, str],
    ) -> dict[str, Any]:
        derived = _geometry_candidates(sections, geometry_sha)
        joints: dict[str, Any] = {}
        for joint_id, raw in sorted(base["joints"].items()):
            item = deepcopy(raw)
            state = sections.observability.get(joint_id)
            if state is not None:
                item["observability"] = state["status"]
            for candidate in item["candidates"]:
                _bind_base_candidate(candidate, geometry_sha)
            item["candidates"].extend(derived.get(joint_id, ()))
            for index, candidate in enumerate(item["candidates"]):
                token = _METHOD_TOKEN[candidate["method"]]
                candidate["candidate_id"] = (
                    f"{joint_id}.{token}.{index:03d}.{run['run_sha256'][:12]}"
                )
            joints[joint_id] = item
        flags = (
            set(base["qa"]["flags"])
            | set(sections.qa_flags)
            | {
                "GEOMETRY_CANDIDATE_PROVIDER_REQUIRES_REVIEW",
                "HEURISTIC_SCORE_NOT_CALIBRATED",
            }
        )
        source = deepcopy(base["source"])
        source["base_project_sha256"] = run["input_sha256"]
        return {
            "format": "autospine-joint-candidates",
            "format_version": 1,
            "project_id": project.get("id"),
            "source": source,
            "analysis": {
                "provider": self.provider_id,
                "provider_version": self.provider_version,
                "config_sha256": run["config_sha256"],
                "run_sha256": run["run_sha256"],
            },
            "coordinate_system": deepcopy(base["coordinate_system"]),
            "joints": joints,
            "qa": {"status": "manual_required", "flags": sorted(flags)},
        }


def _geometry_candidates(
    sections: GeometrySections, geometry_sha: str
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for path in sections.paths:
        if path["status"] != "valid":
            continue
        joint_id = path["joint_ids"][1]
        residuals = [item["residual_px"] for item in path["anchors"].values()]
        ref = _geometry_ref(geometry_sha, "paths", path["path_id"])
        flags = sorted(set(path["flags"]) | {"HEURISTIC_SCORE_NOT_CALIBRATED"})
        result.setdefault(joint_id, []).append({
            "xy": list(path["hinge_candidate_xy"]),
            "method": "medial_axis",
            "score_kind": "heuristic",
            "heuristic_score": _score(0.74, flags),
            "error_radius_px": path["error_radius_px"],
            "source_layer_ids": [path["layer_id"]],
            "evidence": [
                {"kind": "layer_alpha", "source_ref": ref,
                 "note": "Pose-conditioned alpha-clearance hinge; not an exact Blum skeleton."},
                {"kind": "kinematic_residual", "source_ref": ref,
                 "note": f"Maximum projected-anchor residual={max(residuals):.3f}px."},
            ],
            "qa_flags": flags,
        })
    for contact in sections.contacts:
        joint_id = contact["joint_id"]
        ref = _geometry_ref(geometry_sha, "contacts", contact["contact_id"])
        flags = sorted(set(contact["flags"]) | {"HEURISTIC_SCORE_NOT_CALIBRATED"})
        result.setdefault(joint_id, []).append({
            "xy": list(contact["representative_xy"]),
            "method": "contact",
            "score_kind": "heuristic",
            "heuristic_score": _score(0.68 if contact["mode"] == "overlap" else 0.55, flags),
            "error_radius_px": contact["error_radius_px"],
            "source_layer_ids": list(contact["layer_ids"]),
            "evidence": [{"kind": "contact_geometry", "source_ref": ref,
                          "note": "Alpha contact representative ranked by pose cost; not a probability."}],
            "qa_flags": flags,
        })
    return result


def _bind_base_candidate(candidate: dict[str, Any], geometry_sha: str) -> None:
    candidate["qa_flags"] = sorted(
        set(candidate["qa_flags"]) | {"HEURISTIC_SCORE_NOT_CALIBRATED"}
    )
    for evidence in candidate["evidence"]:
        if evidence["kind"] == "layer_alpha" and candidate["source_layer_ids"]:
            old_ref = str(evidence.get("source_ref") or "")
            component = old_ref.rsplit(":component:", 1)
            layer_ref = candidate["source_layer_ids"][0]
            if len(component) == 2 and component[1].isdigit():
                layer_ref = f"{layer_ref}/components/{component[1]}"
            evidence["source_ref"] = _geometry_ref(
                geometry_sha, "layers", layer_ref
            )


def _geometry_ref(sha256: str, section: str, item_id: str) -> str:
    return f"alpha-geometry-evidence:{sha256}#{section}/{item_id}"


def _score(base: float, flags: list[str]) -> float:
    penalties = {
        "HIGH_ALPHA_PATH_RESIDUAL", "ALPHA_PATH_DETOUR_OUTLIER",
        "LOW_PATH_CLEARANCE", "CONTACT_SIDE_ASSIGNMENT_AMBIGUOUS",
        "PELVIS_LEG_CONTACT_AMBIGUOUS", "EXTRA_CONTACT_LOBE_AMBIGUOUS",
    }
    return round(max(0.05, base - 0.08 * len(penalties.intersection(flags))), 6)
