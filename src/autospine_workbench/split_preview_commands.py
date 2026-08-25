"""Offline publication command for reviewed bilateral split previews."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .artifact_store import ArtifactStoreError, ImmutableJsonArtifactStore
from .layer_manifest import (
    LayerManifestBuilder,
    LayerManifestBundleStore,
    LayerManifestError,
)
from .layer_split_materializer import (
    LayerSplitMaterializationError,
    materialize_bilateral_splits,
)
from .project_store import ProjectStore, ProjectStoreError
from .resolved_project import canonical_sha256
from .split_preview import SplitPreviewError, build_split_preview
from .split_preview_reader import SplitPreviewReader, SplitPreviewReaderError


class SplitPreviewPublicationError(ValueError):
    """Raised when the current project has no canonical authored split set."""


def add_split_preview_subcommand(
    subparsers: Any,
    *,
    default_workspace: Path,
    default_state_root: Path,
) -> None:
    parser = subparsers.add_parser(
        "publish-split-previews",
        help="Publish immutable previews for every authored bilateral split",
    )
    parser.add_argument("project_id", help="Audit project identifier")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=default_workspace,
        help="Workspace containing tmp/psd_audit/results",
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=default_state_root,
        help="Root for immutable manifest and preview artifacts",
    )


def publish_split_previews_command(
    project_id: str,
    workspace: Path,
    state_root: Path,
) -> int:
    """Validate all preview inputs before publishing any success response."""

    try:
        store = ProjectStore(
            workspace,
            state_root=state_root,
            measure_composite_quality=False,
        )
        project = store.get_project(project_id)
        layer_ids = _authored_split_layer_ids(project)
        source_assets = {
            layer["id"]: store.resolve_asset(project_id, "layer", layer["id"])
            for layer in _source_layers(project)
        }
        with tempfile.TemporaryDirectory(prefix="autospine-split-preview-") as directory:
            materialized = materialize_bilateral_splits(
                project,
                source_assets,
                Path(directory),
            )
            manifest = LayerManifestBuilder().build(
                project,
                materialized.assets,
                materialized_layers=materialized.layers,
            )
            manifest_sha = canonical_sha256(manifest)
            previews = [
                (
                    layer_id,
                    build_split_preview(
                        project,
                        materialized,
                        manifest,
                        layer_manifest_sha256=manifest_sha,
                        parent_layer_id=layer_id,
                    ),
                )
                for layer_id in layer_ids
            ]
            bundle, published_manifest_sha = LayerManifestBundleStore(
                state_root
            ).publish(project_id, manifest, materialized.assets)
            if published_manifest_sha != manifest_sha:
                raise SplitPreviewPublicationError(
                    "Published Layer Manifest identity changed unexpectedly"
                )
            artifact_store = ImmutableJsonArtifactStore(state_root)
            published = []
            for layer_id, document in previews:
                artifact = artifact_store.publish(
                    "split-previews", project_id, document
                )
                SplitPreviewReader(state_root).load(project_id, artifact.sha256)
                published.append(
                    {
                        "layer_id": layer_id,
                        "split_artifact_sha256": artifact.sha256,
                    }
                )
    except (
        ArtifactStoreError,
        KeyError,
        LayerManifestError,
        LayerSplitMaterializationError,
        OSError,
        ProjectStoreError,
        SplitPreviewError,
        SplitPreviewReaderError,
        TypeError,
        ValueError,
    ) as exc:
        _print({"ok": False, "error": str(exc)})
        return 2
    _print(
        {
            "ok": True,
            "project_id": project_id,
            "revision": manifest["revision"],
            "manifest_sha256": published_manifest_sha,
            "bundle_path": str(bundle),
            "previews": published,
        },
        indent=2,
    )
    return 0


def _authored_split_layer_ids(project: Mapping[str, Any]) -> list[str]:
    resolved = project.get("resolved")
    if not isinstance(resolved, Mapping):
        raise SplitPreviewPublicationError("Project has no resolved snapshot")
    result: list[str] = []
    seen: set[str] = set()
    for layer in _layers(resolved.get("layers"), "resolved"):
        layer_id = layer.get("id")
        if not isinstance(layer_id, str) or not layer_id or layer_id in seen:
            raise SplitPreviewPublicationError("Resolved layer ids are invalid")
        seen.add(layer_id)
        disposition = layer.get("disposition")
        has_spec = "split_spec" in layer
        if disposition in {"split", "split_left_right"} or has_spec:
            if disposition != "split_left_right" or not isinstance(
                layer.get("split_spec"), Mapping
            ):
                raise SplitPreviewPublicationError(
                    f"Layer {layer_id} is not a canonical authored split"
                )
            result.append(layer_id)
    if not result:
        raise SplitPreviewPublicationError(
            "Project has no authored split_left_right layer with split_spec"
        )
    return sorted(result)


def _source_layers(project: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return _layers(project.get("layers"), "source")


def _layers(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(
        not isinstance(layer, Mapping) for layer in value
    ):
        raise SplitPreviewPublicationError(f"Project {label} layers are invalid")
    return value


def _print(value: object, *, indent: int | None = None) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=indent))
