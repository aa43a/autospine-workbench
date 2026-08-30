"""Rebuild current authoring identities without publishing artifacts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
import re
import tempfile
from typing import Any

from .current_project_chain_cache import (
    CurrentProjectChainCacheError,
    current_project_chain_cache_key,
    get_cached_current_project_manifest,
)
from .layer_manifest import LayerManifestBuilder, LayerManifestError
from .layer_split_materializer import (
    LayerSplitMaterializationError,
    materialize_bilateral_splits,
)
from .project_store import ProjectStore, ProjectStoreError
from .resolved_project import canonical_sha256


_SHA = re.compile(r"^[0-9a-f]{64}$")


class CurrentProjectChainError(RuntimeError):
    """Base class for current authoring-chain safety failures."""


class CurrentProjectChainUnavailableError(CurrentProjectChainError):
    """Raised when a current Resolved/Manifest identity cannot be rebuilt."""


class CurrentProjectChainChangedError(CurrentProjectChainError):
    """Raised only when two complete current-chain snapshots differ."""


@dataclass(frozen=True, slots=True)
class CurrentProjectChain:
    """Exact current authoring identities used to classify immutable builds."""

    project_id: str
    resolved_project_sha256: str
    layer_manifest_sha256: str
    input_identity_sha256: str | None = None


def rebuild_current_project_chains(
    store: ProjectStore,
    project_ids: Iterable[str],
) -> dict[str, CurrentProjectChain]:
    """Rebuild exact current identities in temporary storage only."""

    result: dict[str, CurrentProjectChain] = {}
    try:
        for project_id in project_ids:
            if project_id in result:
                raise CurrentProjectChainUnavailableError(
                    "Current project chain ids are duplicated"
                )
            project = store.get_project(project_id)
            if project.get("id") != project_id:
                raise CurrentProjectChainUnavailableError(
                    "Current project identity changed during rebuild"
                )
            resolved = _mapping(project.get("resolved"), "Resolved project")
            resolved_sha = _digest(
                resolved.get("sha256"), "Resolved project SHA-256"
            )
            assets = {
                layer["id"]: store.resolve_asset(
                    project_id, "layer", layer["id"],
                )
                for layer in _layers(project)
            }
            cache_key = current_project_chain_cache_key(
                project_id, resolved_sha, assets,
            )

            def compile_manifest() -> str:
                with tempfile.TemporaryDirectory(
                    prefix="autospine-current-manifest-"
                ) as temporary:
                    materialized = materialize_bilateral_splits(
                        project, assets, Path(temporary),
                    )
                    manifest = LayerManifestBuilder().build(
                        project,
                        materialized.assets,
                        materialized_layers=materialized.layers,
                    )
                manifest_sha = canonical_sha256(manifest)
                if current_project_chain_cache_key(
                    project_id, resolved_sha, assets,
                ) != cache_key:
                    raise CurrentProjectChainCacheError(
                        "Current project chain inputs changed during rebuild"
                    )
                return manifest_sha

            manifest_sha = get_cached_current_project_manifest(
                cache_key, compile_manifest,
            )
            result[project_id] = CurrentProjectChain(
                project_id,
                resolved_sha,
                manifest_sha,
                cache_key.input_identity_sha256,
            )
        return result
    except CurrentProjectChainUnavailableError:
        raise
    except CurrentProjectChainError as exc:
        raise CurrentProjectChainUnavailableError(
            "Current project chain could not be rebuilt"
        ) from exc
    except (
        AttributeError, KeyError, LayerManifestError,
        LayerSplitMaterializationError,
        CurrentProjectChainCacheError, OSError, ProjectStoreError,
        TypeError, ValueError,
    ) as exc:
        raise CurrentProjectChainUnavailableError(
            "Current project chain could not be rebuilt"
        ) from exc


def chain_is_current(
    project_id: str,
    resolved_project_sha256: str,
    layer_manifest_sha256: str,
    current: Mapping[str, CurrentProjectChain] | None,
) -> bool:
    """Accept only an exact row in an explicit current-chain inventory."""

    if current is None:
        return False
    head = current.get(project_id)
    return type(head) is CurrentProjectChain and (
        head.project_id == project_id
        and head.resolved_project_sha256 == resolved_project_sha256
        and head.layer_manifest_sha256 == layer_manifest_sha256
    )


def require_unchanged_current_project_chains(
    before: Mapping[str, CurrentProjectChain],
    after: Mapping[str, CurrentProjectChain],
) -> None:
    """Reject an inventory assembled across authoring-state drift."""

    if dict(before) != dict(after):
        raise CurrentProjectChainChangedError(
            "Current project chain changed during package discovery"
        )


def _layers(project: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = project.get("layers")
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) or not isinstance(row.get("id"), str)
        for row in value
    ):
        raise CurrentProjectChainUnavailableError(
            "Current project layers are invalid"
        )
    return value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CurrentProjectChainUnavailableError(f"{label} is invalid")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise CurrentProjectChainUnavailableError(f"{label} is invalid")
    return value
