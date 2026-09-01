"""Fast selected-project authoring seal for persisted Preview v2 mounts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .current_project_chain import CurrentProjectChain
from .current_project_chain_cache import (
    CurrentProjectChainCacheError, current_project_chain_cache_key,
)
from .manifest_artifacts import LayerManifestError, require_sha256
from .p10_preview_v2_cache import P10PreviewV2CacheRecord
from .project_store import ProjectStore, ProjectStoreError


class P10PreviewV2CurrentScopeError(RuntimeError):
    """Raised when a selected project's exact dependency seal is unavailable."""


@dataclass(frozen=True, slots=True)
class P10PreviewV2CurrentScope:
    """One project chain proven by current source bytes and compiler identity."""

    project_id: str
    chain: CurrentProjectChain

    @property
    def project_ids(self) -> tuple[str, ...]:
        return (self.project_id,)

    @property
    def chains(self) -> dict[str, CurrentProjectChain]:
        return {self.project_id: self.chain}


def current_p10_preview_v2_scope(
    store: ProjectStore,
    record: P10PreviewV2CacheRecord,
) -> P10PreviewV2CurrentScope:
    """Rehash selected source rasters without rematerializing its manifest."""

    if type(store) is not ProjectStore \
            or type(record) is not P10PreviewV2CacheRecord:
        raise P10PreviewV2CurrentScopeError(
            "Preview v2 current-scope input is invalid"
        )
    try:
        project_id = record.address.project_id
        p3 = _mapping(record.candidates.document["source"]["p3"])
        expected_resolved = require_sha256(
            p3["resolved_project_sha256"], "Current-scope resolved project",
        )
        expected_manifest = require_sha256(
            p3["layer_manifest_sha256"], "Current-scope Layer Manifest",
        )
        if record.result.project_id != project_id \
                or record.candidates.document["project_id"] != project_id:
            raise P10PreviewV2CurrentScopeError(
                "Preview v2 selected project is cross-wired"
            )
        project = store.get_project(project_id)
        if project.get("id") != project_id:
            raise P10PreviewV2CurrentScopeError(
                "Preview v2 selected project identity changed"
            )
        resolved = _mapping(project.get("resolved"))
        current_resolved = require_sha256(
            resolved.get("sha256"), "Current-scope resolved project",
        )
        assets = _assets(store, project_id, project.get("layers"))
        key = current_project_chain_cache_key(
            project_id, current_resolved, assets,
        )
        if current_resolved != expected_resolved:
            raise P10PreviewV2CurrentScopeError(
                "Preview v2 resolved project is historical"
            )
        return P10PreviewV2CurrentScope(
            project_id,
            CurrentProjectChain(
                project_id, current_resolved, expected_manifest,
                key.input_identity_sha256,
            ),
        )
    except P10PreviewV2CurrentScopeError:
        raise
    except (
        CurrentProjectChainCacheError, KeyError, LayerManifestError,
        OSError, ProjectStoreError, TypeError, ValueError,
    ) as exc:
        raise P10PreviewV2CurrentScopeError(
            "Preview v2 selected project seal could not be rebuilt"
        ) from exc


def _assets(store, project_id, value):
    if not isinstance(value, list) or not value:
        raise P10PreviewV2CurrentScopeError(
            "Preview v2 selected project layers are invalid"
        )
    result = {}
    for row in value:
        if not isinstance(row, Mapping) \
                or not isinstance(row.get("id"), str) \
                or not row["id"] or row["id"] in result:
            raise P10PreviewV2CurrentScopeError(
                "Preview v2 selected project layers are invalid"
            )
        result[row["id"]] = store.resolve_asset(
            project_id, "layer", row["id"],
        )
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P10PreviewV2CurrentScopeError(
            "Preview v2 current-scope value is invalid"
        )
    return value


__all__ = [
    "P10PreviewV2CurrentScope", "P10PreviewV2CurrentScopeError",
    "current_p10_preview_v2_scope",
]
