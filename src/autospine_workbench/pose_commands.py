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
