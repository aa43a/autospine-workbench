"""Orchestrate split binding across override load and prospective saves."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .resolved_project import ResolvedProjectBuilder
from .split_decision_binder import (
    SplitDecisionBinder,
    SplitDecisionBindingError,
    SplitDecisionBindingIssue,
)


_DERIVED = (
    "operation_config_sha256",
    "review_target_sha256",
    "analysis",
    "binding_status",
)
_CLIENT = ("action", "split_artifact_sha256", "reason")


class SplitDecisionPersistence:
    """Keep persisted decisions derived while allowing full-document saves."""

    def __init__(self, state_root: Path) -> None:
        self._binder = SplitDecisionBinder(state_root)
        self._resolved = ResolvedProjectBuilder()

    def revalidate_stored(
        self,
        project_id: str,
        document: Mapping[str, Any],
        *,
        base_project: Mapping[str, Any] | None,
        source_paths: Mapping[str, Path] | None,
    ) -> dict[str, dict[str, Any]]:
        decisions = document.get("split_decisions") or {}
        if not decisions:
            return {}
        project, paths = self._context(project_id, base_project, source_paths)
        resolved = self._resolved.build(project, document)
        return self._binder.bind(
            project_id,
            decisions,
            resolved=resolved,
            source_paths=paths,
            stored=True,
        )

    def bind_save(
        self,
        project_id: str,
        incoming: Mapping[str, Any],
        current: Mapping[str, Any],
        *,
        next_revision: int,
        base_project: Mapping[str, Any] | None,
        source_paths: Mapping[str, Path] | None,
    ) -> dict[str, dict[str, Any]]:
        incoming_decisions = incoming.get("split_decisions") or {}
        if not incoming_decisions:
            return {}
        project, paths = self._context(project_id, base_project, source_paths)
        current_resolved = self._resolved.build(project, current)
        stored_reuse: dict[str, dict[str, Any]] = {}
        client_new: dict[str, dict[str, Any]] = {}
        changed: set[str] = set()
        current_decisions = current.get("split_decisions") or {}
        for layer_id, value in incoming_decisions.items():
            client = _client_fields(value)
            previous = current_decisions.get(layer_id)
            if _client_fields(previous) != client:
                changed.add(layer_id)
            if (
                isinstance(previous, Mapping)
                and previous.get("split_artifact_sha256")
                == client.get("split_artifact_sha256")
            ):
                stored_reuse[layer_id] = {
                    **client,
                    **{field: deepcopy(previous.get(field)) for field in _DERIVED},
                }
            else:
                client_new[layer_id] = client
        provisional: dict[str, dict[str, Any]] = {}
        if stored_reuse:
            provisional.update(
                self._binder.bind(
                    project_id,
                    stored_reuse,
                    resolved=current_resolved,
                    source_paths=paths,
                    stored=True,
                )
            )
        if client_new:
            provisional.update(
                self._binder.bind(
                    project_id,
                    client_new,
                    resolved=current_resolved,
                    source_paths=paths,
                )
            )
        prospective = deepcopy(dict(incoming))
        prospective["revision"] = next_revision
        prospective["split_decisions"] = provisional
        prospective_resolved = self._resolved.build(project, prospective)
        rebound = self._binder.bind(
            project_id,
            provisional,
            resolved=prospective_resolved,
            source_paths=paths,
            stored=True,
        )
        for layer_id in sorted(changed):
            if rebound[layer_id]["binding_status"] == "stale":
                raise SplitDecisionBindingError(
                    SplitDecisionBindingIssue(
                        f"$.split_decisions.{layer_id}",
                        "stale_artifact",
                        "a new or changed decision is stale in the prospective revision",
                    )
                )
        return dict(sorted(rebound.items()))

    @staticmethod
    def _context(
        project_id: str,
        base_project: Mapping[str, Any] | None,
        source_paths: Mapping[str, Path] | None,
    ) -> tuple[Mapping[str, Any], Mapping[str, Path]]:
        if (
            not isinstance(base_project, Mapping)
            or base_project.get("id") != project_id
            or not isinstance(source_paths, Mapping)
        ):
            raise SplitDecisionBindingError(
                SplitDecisionBindingIssue(
                    "$.split_decisions",
                    "binding_context",
                    "split decisions require the base project and strict source paths",
                )
            )
        return base_project, source_paths


def _client_fields(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {field: deepcopy(value[field]) for field in _CLIENT if field in value}
