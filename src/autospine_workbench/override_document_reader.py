"""Strict reader for stored override revisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .candidate_decisions import CandidateDecisionBinder, CandidateDecisionError
from .contracts import (
    ContractValidationError,
    OVERRIDE_SCHEMA_VERSION,
    normalize_override_request,
)
from .override_files import OverrideFileError, OverrideFiles
from .region_rebind_revision_provenance import (
    RegionRebindRevisionProvenanceError,
    normalize_region_rebind_revision_provenance,
)
from .split_decision_binder import SplitDecisionBindingError
from .split_decision_persistence import SplitDecisionPersistence


class OverrideDocumentReader:
    """Validate one legacy, latest, or immutable history document."""

    def __init__(
        self,
        files: OverrideFiles,
        decisions: CandidateDecisionBinder,
        split_decisions: SplitDecisionPersistence,
        state_error: type[RuntimeError],
    ) -> None:
        self._files = files
        self._decisions = decisions
        self._split_decisions = split_decisions
        self._state_error = state_error

    def read(
        self,
        path: Path,
        *,
        project_id: str,
        joint_ids: set[str],
        bone_ids: set[str] | None,
        layer_ids: set[str],
        canvas_width: int,
        canvas_height: int,
        base_project: Mapping[str, Any] | None,
        source_paths: Mapping[str, Path] | None,
    ) -> dict[str, Any]:
        try:
            raw = self._files.read(path)
        except OverrideFileError as exc:
            raise self._state_error(str(exc)) from exc
        revision = raw.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise self._state_error("Override revision is invalid")
        stored_project_id = raw.get("project_id")
        if stored_project_id is not None and stored_project_id != project_id:
            raise self._state_error("Override document belongs to another project")
        request = {
            "schema_version": raw.get("schema_version", OVERRIDE_SCHEMA_VERSION),
            "base_revision": revision,
            "joint_overrides": raw.get("joint_overrides", {}),
            "joint_decisions": raw.get("joint_decisions", {}),
            "layer_overrides": raw.get("layer_overrides", {}),
            "notes": raw.get("notes", ""),
        }
        if "split_decisions" in raw:
            request["split_decisions"] = raw["split_decisions"]
        try:
            _, normalized = normalize_override_request(
                request,
                project_id=project_id,
                current_revision=revision,
                joint_ids=joint_ids,
                bone_ids=bone_ids,
                layer_ids=layer_ids,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
                stored=True,
            )
        except ContractValidationError as exc:
            raise self._state_error(f"Stored overrides are invalid: {exc}") from exc
        try:
            normalized["joint_decisions"] = self._decisions.bind(
                project_id,
                normalized["joint_decisions"],
                joint_ids=joint_ids,
                layer_ids=layer_ids,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
                stored=True,
            )
        except CandidateDecisionError as exc:
            raise self._state_error(
                f"Stored candidate decisions are invalid: {exc}"
            ) from exc
        normalized["revision"] = revision
        if "revision_provenance" in raw:
            try:
                normalized["revision_provenance"] = (
                    normalize_region_rebind_revision_provenance(
                        raw["revision_provenance"],
                        project_id=project_id,
                        revision=revision,
                    )
                )
            except RegionRebindRevisionProvenanceError as exc:
                raise self._state_error(
                    "Stored revision provenance is invalid"
                ) from exc
        try:
            normalized["split_decisions"] = self._split_decisions.revalidate_stored(
                project_id,
                normalized,
                base_project=base_project,
                source_paths=source_paths,
            )
        except SplitDecisionBindingError as exc:
            raise self._state_error(
                f"Stored split decisions are invalid: {exc}"
            ) from exc
        return normalized
