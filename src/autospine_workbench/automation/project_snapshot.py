"""Read-only, lifetime-bounded observation of the current authoring chain."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from typing import Callable, Iterator

from ..current_project_chain_cache import current_project_chain_cache_key
from ..layer_manifest import LayerManifestBuilder, LayerManifestError
from ..layer_split_materializer import (
    LayerSplitMaterializationError, materialize_bilateral_splits,
)
from ..manifest_artifacts import png_ihdr
from ..project_store import ProjectStore, ProjectNotFoundError, AssetNotFoundError
from ..region_rig import RegionRigCompilation, RegionRigError, compile_region_rig
from ..resolved_project import canonical_sha256
from ..project_asset_resolution import layers as layer_assets


class SnapshotError(ValueError):
    """Public errors contain stable codes, never local source paths."""

    def __init__(self, reason_code: str):
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class ProjectSnapshot:
    project_id: str
    resolved: dict
    manifest: dict
    assets: dict[str, Path]
    materialized_assets: dict[str, Path]
    image_sizes: dict[str, tuple[int, int]]
    source_addresses: dict[str, str]
    region_compilation: RegionRigCompilation | None
    compile_reason_code: str | None
    assert_current: Callable[[], None]


def _read(store, project_id):
    try:
        project = deepcopy(store.get_project(project_id))
        if project.get("id") != project_id:
            raise SnapshotError("project_snapshot_invalid")
        resolved = project["resolved"]
        canonical_sha256(project)
        assets = layer_assets(store,project_id,[layer['id'] for layer in resolved['layers']])
        key = current_project_chain_cache_key(project_id, resolved["sha256"], assets)
        return project, assets, key
    except SnapshotError:
        raise
    except ProjectNotFoundError as exc:
        raise SnapshotError("project_not_found") from exc
    except (AssetNotFoundError, OSError) as exc:
        raise SnapshotError("project_asset_unavailable") from exc
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise SnapshotError("project_snapshot_invalid") from exc


@contextmanager
def observe_project(store: ProjectStore, project_id: str) -> Iterator[ProjectSnapshot]:
    """Build exact P2 inputs in temporary storage; publish no artifacts.

    Paths are valid inside the context. Check source drift before yielding and
    on normal context exit, including edits to the current authoring revision.
    """
    if not isinstance(project_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", project_id,
    ):
        raise SnapshotError("project_snapshot_invalid")
    project, original_assets, initial_key = _read(store, project_id)

    def assert_current():
        _, _, current_key = _read(store, project_id)
        if current_key != initial_key:
            raise SnapshotError("project_changed_during_snapshot")

    with TemporaryDirectory(prefix="autospine-pipeline-observation-") as temporary:
        try:
            materialized = materialize_bilateral_splits(
                project, original_assets, Path(temporary),
            )
        except (LayerSplitMaterializationError, OSError, ValueError) as exc:
            raise SnapshotError("layer_split_unsupported") from exc
        try:
            manifest = LayerManifestBuilder().build(
                project, materialized.assets, materialized_layers=materialized.layers,
            )
            manifest_sha = canonical_sha256(manifest)
            image_sizes = {
                row["layer_id"]: png_ihdr(materialized.assets[row["layer_id"]])[:2]
                for row in manifest["layers"]
            }
            assets = {
                row["raster"]["artifact_path"]: materialized.assets[row["layer_id"]]
                for row in manifest["layers"]
            }
        except (LayerManifestError, KeyError, OSError, TypeError, ValueError) as exc:
            raise SnapshotError("layer_manifest_invalid") from exc
        compilation, reason = None, None
        try:
            compilation = compile_region_rig(
                manifest, project["resolved"], layer_manifest_sha256=manifest_sha,
                image_sizes=image_sizes, allow_manual_required=True,
            )
        except RegionRigError:
            reason = "region_geometry_unsupported"
        assert_current()
        yield ProjectSnapshot(
            project_id, project["resolved"], manifest, assets, materialized.assets,
            image_sizes,
            {"resolved_project_sha256": initial_key.resolved_project_sha256,
             "layer_manifest_sha256": manifest_sha,
             "input_identity_sha256": initial_key.input_identity_sha256},
            compilation, reason, assert_current,
        )
        assert_current()
