"""Offline pose-analysis command handlers.

Keep detector input handling and immutable artifact publication outside the
top-level CLI dispatcher so each pose pipeline stage can evolve independently.
"""

from __future__ import annotations

import json
from pathlib import Path

from .alpha_evidence_validation import (
    AlphaEvidenceValidationError,
    require_valid_alpha_geometry_evidence,
)
from .artifact_store import (
    ArtifactStoreError,
    ImmutableJsonArtifactStore,
    PublishedArtifact,
)
from .candidate_provenance import sha256_file
from .candidate_validation import CandidateValidationError, require_valid_candidate_document
from .coco17_adapter import Coco17AdapterError, adapt_coco17_detections
from .coco17_detections import Coco17DetectionError, load_coco17_detections
from .geometry_candidate_binding import require_geometry_candidate_binding
from .joint_candidates import AuditBBoxHeuristicProvider
from .limb_candidates import LimbCandidateError, PoseAlphaLimbProvider
from .pose_geometry_limb_provider import PoseGeometryLimbBundle, PoseGeometryLimbProvider
from .pose_evaluation import PoseEvaluationError, evaluate_pose
from .pose_observations import PoseObservationError, load_pose_observations
from .project_store import ProjectStore, ProjectStoreError


def analyze_joints(
    project_id: str,
    workspace: Path,
    state_root: Path,
    *,
    provider_name: str = "audit-bbox",
    pose_path: Path | None = None,
    alpha_threshold: int = 8,
) -> int:
    """Validate and publish a provenance-ordered joint-analysis artifact chain."""

    try:
        pose_document = None
        store = ProjectStore(workspace, state_root=state_root)
        project = store.get_project(project_id)
        geometry_document = None
        if provider_name == "audit-bbox":
            if pose_path is not None:
                raise ValueError(
                    "--pose-observations is only valid with --provider pose-alpha or pose-geometry"
                )
            provider = AuditBBoxHeuristicProvider()
        elif provider_name in {"pose-alpha", "pose-geometry"}:
            if pose_path is None:
                raise ValueError(
                    f"--provider {provider_name} requires --pose-observations"
                )
            composite = store.resolve_asset(project_id, "composite")
            observations = load_pose_observations(
                pose_path,
                expected_project_id=project_id,
                expected_image_sha256=sha256_file(composite, "project composite"),
                expected_canvas_size=(project["canvas"]["width"], project["canvas"]["height"]),
            )
            pose_document = observations.document
            layer_assets = {
                layer["id"]: store.resolve_asset(project_id, "layer", layer["id"])
                for layer in project["layers"]
            }
            provider_class = (
                PoseGeometryLimbProvider
                if provider_name == "pose-geometry"
                else PoseAlphaLimbProvider
            )
            provider = provider_class(layer_assets, observations, alpha_threshold=alpha_threshold)
        else:
            raise ValueError("Unknown joint candidate provider")
        result = provider.analyze(project)
        if isinstance(result, PoseGeometryLimbBundle):
            geometry_document = result.geometry_document
            document = result.joint_candidate_document
        else:
            document = result
        joint_ids = {item["id"] for item in project["skeleton"]["joints"]}
        layer_ids = {item["id"] for item in project["layers"]}
        validation_context = {
            "joint_ids": joint_ids,
            "layer_ids": layer_ids,
            "canvas_width": project["canvas"]["width"],
            "canvas_height": project["canvas"]["height"],
        }
        geometry_digest = None
        if geometry_document is not None:
            require_valid_alpha_geometry_evidence(
                geometry_document,
                project_id=project_id,
                **validation_context,
            )
        require_valid_candidate_document(
            document,
            **validation_context,
        )
        if geometry_document is not None:
            geometry_digest = require_geometry_candidate_binding(
                document, geometry_document
            )
        artifact_store = ImmutableJsonArtifactStore(state_root)
        pose_published = (
            artifact_store.publish("pose-observations", project_id, pose_document)
            if pose_document is not None
            else None
        )
        if pose_published is not None and pose_published.sha256 != observations.document_sha256:
            raise ArtifactStoreError("Published pose observation identity changed")
        geometry_published = (
            artifact_store.publish(
                "alpha-geometry-evidence", project_id, geometry_document
            )
            if geometry_document is not None
            else None
        )
        if (
            geometry_published is not None
            and geometry_published.sha256 != geometry_digest
        ):
            raise ArtifactStoreError("Published geometry evidence identity changed")
        published = artifact_store.publish("joint-candidates", project_id, document)
    except (
        ProjectStoreError,
        ArtifactStoreError,
        AlphaEvidenceValidationError,
        CandidateValidationError,
        PoseObservationError,
        LimbCandidateError,
        OSError,
        ValueError,
    ) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    response = {
        "ok": True,
        "project_id": project_id,
        "provider": document["analysis"]["provider"],
        "analysis_run_sha256": document["analysis"]["run_sha256"],
        "artifact_sha256": published.sha256,
        "artifact_path": str(published.path),
        "joint_candidate_artifact_sha256": published.sha256,
        "joint_candidate_artifact_path": str(published.path),
    }
    artifacts: dict[str, dict[str, str]] = {}
    if pose_published is not None:
        response["pose_artifact_sha256"] = pose_published.sha256
        response["pose_artifact_path"] = str(pose_published.path)
        artifacts["pose_observations"] = _artifact_identity(pose_published)
    if geometry_published is not None:
        response["geometry_artifact_sha256"] = geometry_published.sha256
        response["geometry_artifact_path"] = str(geometry_published.path)
        artifacts["alpha_geometry_evidence"] = _artifact_identity(geometry_published)
    artifacts["joint_candidates"] = _artifact_identity(published)
    response["artifacts"] = artifacts
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


def _artifact_identity(published: PublishedArtifact) -> dict[str, str]:
    return {"sha256": published.sha256, "path": str(published.path)}


def import_pose(
    project_id: str,
    detections_path: Path,
    workspace: Path,
    state_root: Path,
    *,
    selected_index: int | None,
    selection_method: str | None,
    side_mapping: str,
    view_orientation: str,
    mirror_state: str,
) -> int:
    """Adapt and publish a pinned COCO17 input plus canonical pose v2."""

    try:
        store = ProjectStore(workspace, state_root=state_root)
        project = store.get_project(project_id)
        composite = store.resolve_asset(project_id, "composite")
        detections = load_coco17_detections(
            detections_path,
            expected_project_id=project_id,
            expected_image_sha256=sha256_file(composite, "project composite"),
            expected_canvas_size=(project["canvas"]["width"], project["canvas"]["height"]),
        )
        pose_document = adapt_coco17_detections(
            detections,
            selected_index=selected_index,
            selection_method=selection_method,
            side_mapping=side_mapping,
            view_orientation=view_orientation,
            mirror_state=mirror_state,
        )
        artifact_store = ImmutableJsonArtifactStore(state_root)
        input_artifact = artifact_store.publish(
            "pose-adapter-inputs", project_id, detections.document
        )
        if input_artifact.sha256 != detections.document_sha256:
            raise ArtifactStoreError("Published adapter input identity changed")
        pose_artifact = artifact_store.publish(
            "pose-observations", project_id, pose_document
        )
    except (
        ProjectStoreError,
        ArtifactStoreError,
        Coco17DetectionError,
        Coco17AdapterError,
        OSError,
        ValueError,
    ) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "project_id": project_id,
                "input_artifact_sha256": input_artifact.sha256,
                "input_artifact_path": str(input_artifact.path),
                "pose_artifact_sha256": pose_artifact.sha256,
                "pose_artifact_path": str(pose_artifact.path),
                "coordinate_transform": pose_document["adapter"]["coordinate_transform"],
                "side_mapping": pose_document["adapter"]["side_mapping"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def evaluate_pose_command(
    project_id: str,
    pose_path: Path,
    workspace: Path,
    state_root: Path,
) -> int:
    """Publish a diagnostic report against manual limb-joint overrides."""

    try:
        store = ProjectStore(workspace, state_root=state_root)
        project = store.get_project(project_id)
        composite = store.resolve_asset(project_id, "composite")
        observations = load_pose_observations(
            pose_path,
            expected_project_id=project_id,
            expected_image_sha256=sha256_file(composite, "project composite"),
            expected_canvas_size=(project["canvas"]["width"], project["canvas"]["height"]),
        )
        report = evaluate_pose(project, observations)
        artifact_store = ImmutableJsonArtifactStore(state_root)
        pose_artifact = artifact_store.publish(
            "pose-observations", project_id, observations.document or {}
        )
        if pose_artifact.sha256 != observations.document_sha256:
            raise ArtifactStoreError("Published pose observation identity changed")
        report_artifact = artifact_store.publish("pose-evaluations", project_id, report)
    except (
        ProjectStoreError,
        ArtifactStoreError,
        PoseObservationError,
        PoseEvaluationError,
        OSError,
        ValueError,
    ) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "project_id": project_id,
                "pose_artifact_sha256": pose_artifact.sha256,
                "pose_artifact_path": str(pose_artifact.path),
                "evaluation_artifact_sha256": report_artifact.sha256,
                "evaluation_artifact_path": str(report_artifact.path),
                "metrics": report["metrics"],
                "side_swap_diagnostic": report["side_swap_diagnostic"],
                "qa": report["qa"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0
