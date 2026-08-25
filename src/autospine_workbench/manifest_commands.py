"""Offline command for publishing a materialized Layer Manifest bundle."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

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


def materialize_manifest_command(
    project_id: str,
    workspace: Path,
    state_root: Path,
) -> int:
    """Materialize reviewed split layers and publish one immutable bundle."""

    try:
        store = ProjectStore(
            workspace,
            state_root=state_root,
            measure_composite_quality=False,
        )
        project = store.get_project(project_id)
        source_assets = {
            layer["id"]: store.resolve_asset(project_id, "layer", layer["id"])
            for layer in project["layers"]
        }
        with tempfile.TemporaryDirectory(prefix="autospine-manifest-") as directory:
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
            bundle, digest = LayerManifestBundleStore(state_root).publish(
                project_id,
                manifest,
                materialized.assets,
            )
    except (
        LayerManifestError,
        LayerSplitMaterializationError,
        ProjectStoreError,
        OSError,
        ValueError,
    ) as exc:
        _print({"ok": False, "error": str(exc)})
        return 2
    _print(
        {
            "ok": True,
            "project_id": project_id,
            "revision": manifest["revision"],
            "manifest_sha256": digest,
            "bundle_path": str(bundle),
        },
        indent=2,
    )
    return 0


def _print(value: object, *, indent: int | None = None) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=indent))
