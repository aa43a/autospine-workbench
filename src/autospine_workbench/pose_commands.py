"""Offline pose-analysis command handlers.

Keep detector input handling and immutable artifact publication outside the
top-level CLI dispatcher so each pose pipeline stage can evolve independently.
"""

from __future__ import annotations

import json
from pathlib import Path

from .artifact_store import ArtifactStoreError, ImmutableJsonArtifactStore
from .candidate_provenance import sha256_file
from .candidate_validation import CandidateValidationError, require_valid_candidate_document
from .coco17_adapter import Coco17AdapterError, adapt_coco17_detections
from .coco17_detections import Coco17DetectionError, load_coco17_detections
from .joint_candidates import AuditBBoxHeuristicProvider
from .limb_candidates import LimbCandidateError, PoseAlphaLimbProvider
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
    """Publish one validated, content-addressed joint-candidate document."""

    try:
        pose_document = None
        store = ProjectStore(workspace, state_root=state_root)
        project = store.get_project(project_id)
        if provider_name == "audit-bbox":
            if pose_path is not None:
                raise ValueError("--pose-observations is only valid with --provider pose-alpha")
            provider = AuditBBoxHeuristicProvider()
        elif provider_name == "pose-alpha":
            if pose_path is None:
                raise ValueError("--provider pose-alpha requires --pose-observations")
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
            provider = PoseAlphaLimbProvider(
                layer_assets,
                observations,
                alpha_threshold=alpha_threshold,
            )
        else:
            raise ValueError("Unknown joint candidate provider")
        document = provider.analyze(project)
        require_valid_candidate_document(
            document,
            joint_ids={item["id"] for item in project["skeleton"]["joints"]},
            layer_ids={item["id"] for item in project["layers"]},
            canvas_width=project["canvas"]["width"],
            canvas_height=project["canvas"]["height"],
        )
        artifact_store = ImmutableJsonArtifactStore(state_root)
        pose_published = (
            artifact_store.publish("pose-observations", project_id, pose_document)
            if pose_document is not None
            else None
        )
        published = artifact_store.publish("joint-candidates", project_id, document)
    except (
        ProjectStoreError,
        ArtifactStoreError,
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
    }
    if pose_published is not None:
        response["pose_artifact_sha256"] = pose_published.sha256
        response["pose_artifact_path"] = str(pose_published.path)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


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
