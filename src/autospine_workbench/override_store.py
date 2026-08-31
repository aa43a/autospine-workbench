"""Append-only persistence for reviewed project overrides.

The history directory is the source of truth. ``latest.json`` is an atomically
replaceable read cache, while the legacy ``<project>.json`` document remains a
read-only migration source.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any, Mapping

from .candidate_decisions import CandidateDecisionBinder, CandidateDecisionError
from .contracts import (
    ContractValidationError,
    empty_overrides,
    normalize_override_request,
)
from .override_commit import refresh_latest_after_commit
from .override_document_reader import OverrideDocumentReader
from .override_files import OverrideFileError, OverrideFiles, history_filename
from .region_rebind_revision_provenance import (
    RegionRebindRevisionProvenanceError,
    normalize_region_rebind_revision_provenance,
)
from .split_decision_binder import SplitDecisionBindingError
from .split_decision_persistence import SplitDecisionPersistence


_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class OverrideStoreError(RuntimeError):
    """Base error for override persistence."""


class OverrideStateError(OverrideStoreError):
    """Raised when persisted override state is inconsistent or invalid."""


class OverrideRevisionConflict(OverrideStoreError):
    """Raised when a compare-and-swap request targets a stale revision."""

    def __init__(self, requested_revision: int, current_revision: int):
        self.requested_revision = requested_revision
        self.current_revision = current_revision
        super().__init__(
            f"Revision conflict: requested {requested_revision}, current {current_revision}"
        )


class OverrideHistoryStore:
    """Read legacy overrides and publish immutable revision snapshots."""

    def __init__(self, state_root: Path):
        self._root = Path(state_root) / "overrides"
        self._files = OverrideFiles(self._root)
        self._decision_binder = CandidateDecisionBinder(state_root)
        self._split_decisions = SplitDecisionPersistence(state_root)
        self._documents = OverrideDocumentReader(
            self._files,
            self._decision_binder,
            self._split_decisions,
            OverrideStateError,
        )
        self._lock = threading.RLock()

    def load(
        self,
        project_id: str,
        *,
        joint_ids: set[str],
        bone_ids: set[str] | None = None,
        layer_ids: set[str],
        canvas_width: int,
        canvas_height: int,
        base_project: Mapping[str, Any] | None = None,
        source_paths: Mapping[str, Path] | None = None,
    ) -> dict[str, Any]:
        """Return the highest valid persisted revision for a project."""

        self._validate_project_id(project_id)
        documents: dict[int, dict[str, Any]] = {}
        try:
            paths = self._files.document_paths(project_id)
        except OverrideFileError as exc:
            raise OverrideStateError(str(exc)) from exc
        for path, expected_revision in paths:
            document = self._documents.read(
                path,
                project_id=project_id,
                joint_ids=joint_ids,
                bone_ids=bone_ids,
                layer_ids=layer_ids,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
                base_project=base_project,
                source_paths=source_paths,
            )
            revision = document["revision"]
            if expected_revision is not None and revision != expected_revision:
                raise OverrideStateError(
                    f"History filename revision does not match its document: {path.name}"
                )
            previous = documents.get(revision)
            if previous is not None and previous != document:
                raise OverrideStateError(
                    f"Conflicting override documents exist for revision {revision}"
                )
            documents[revision] = document
        if not documents:
            return empty_overrides(project_id)
        return documents[max(documents)]

    def save(
        self,
        project_id: str,
        payload: Any,
        *,
        revision_provenance: Mapping[str, Any] | None = None,
        joint_ids: set[str],
        bone_ids: set[str] | None = None,
        layer_ids: set[str],
        canvas_width: int,
        canvas_height: int,
        base_project: Mapping[str, Any] | None = None,
        source_paths: Mapping[str, Path] | None = None,
    ) -> dict[str, Any]:
        """Compare revisions, append one snapshot, then atomically update latest."""

        with self._lock:
            current = self.load(
                project_id,
                joint_ids=joint_ids,
                bone_ids=bone_ids,
                layer_ids=layer_ids,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
                base_project=base_project,
                source_paths=source_paths,
            )
            try:
                requested_revision, normalized = normalize_override_request(
                    payload,
                    project_id=project_id,
                    current_revision=current["revision"],
                    joint_ids=joint_ids,
                    bone_ids=bone_ids,
                    layer_ids=layer_ids,
                    canvas_width=canvas_width,
                    canvas_height=canvas_height,
                )
            except ContractValidationError:
                raise
            if requested_revision != current["revision"]:
                raise OverrideRevisionConflict(requested_revision, current["revision"])

            try:
                normalized["joint_decisions"] = self._decision_binder.bind(
                    project_id,
                    normalized["joint_decisions"],
                    joint_ids=joint_ids,
                    layer_ids=layer_ids,
                    canvas_width=canvas_width,
                    canvas_height=canvas_height,
                )
            except CandidateDecisionError as exc:
                raise ContractValidationError(exc.as_validation_issues()) from exc

            try:
                normalized["split_decisions"] = self._split_decisions.bind_save(
                    project_id,
                    normalized,
                    current,
                    next_revision=current["revision"] + 1,
                    base_project=base_project,
                    source_paths=source_paths,
                )
            except SplitDecisionBindingError as exc:
                raise ContractValidationError(exc.as_validation_issues()) from exc

            normalized["revision"] = current["revision"] + 1
            if revision_provenance is not None:
                try:
                    normalized["revision_provenance"] = (
                        normalize_region_rebind_revision_provenance(
                            revision_provenance,
                            project_id=project_id,
                            revision=normalized["revision"],
                        )
                    )
                except RegionRebindRevisionProvenanceError as exc:
                    raise OverrideStoreError(
                        "Trusted revision provenance is invalid"
                    ) from exc
            project_dir = self._project_dir(project_id)
            history_dir = project_dir / "history"
            history_dir.mkdir(parents=True, exist_ok=True)

            if current["revision"] > 0:
                self._ensure_snapshot(
                    history_dir,
                    current,
                    project_id=project_id,
                    joint_ids=joint_ids,
                    bone_ids=bone_ids,
                    layer_ids=layer_ids,
                    canvas_width=canvas_width,
                    canvas_height=canvas_height,
                    base_project=base_project,
                    source_paths=source_paths,
                )
            try:
                self._files.publish(history_dir, normalized)
            except FileExistsError as exc:
                observed = self.load(
                    project_id,
                    joint_ids=joint_ids,
                    bone_ids=bone_ids,
                    layer_ids=layer_ids,
                    canvas_width=canvas_width,
                    canvas_height=canvas_height,
                    base_project=base_project,
                    source_paths=source_paths,
                )
                raise OverrideRevisionConflict(
                    requested_revision, observed["revision"]
                ) from exc
            except OverrideFileError as exc:
                raise OverrideStoreError(str(exc)) from exc
            return refresh_latest_after_commit(
                self._files,
                history_path=(
                    history_dir / history_filename(int(normalized["revision"]))
                ),
                latest_path=project_dir / "latest.json",
                document=normalized,
            )

    def _ensure_snapshot(
        self,
        history_dir: Path,
        document: Mapping[str, Any],
        *,
        project_id: str,
        joint_ids: set[str],
        bone_ids: set[str] | None,
        layer_ids: set[str],
        canvas_width: int,
        canvas_height: int,
        base_project: Mapping[str, Any] | None,
        source_paths: Mapping[str, Path] | None,
    ) -> None:
        destination = history_dir / history_filename(int(document["revision"]))
        if not destination.exists():
            try:
                self._files.publish(history_dir, document)
                return
            except FileExistsError:
                pass
            except OverrideFileError as exc:
                raise OverrideStoreError(str(exc)) from exc
        existing = self._documents.read(
            destination,
            project_id=project_id,
            joint_ids=joint_ids,
            bone_ids=bone_ids,
            layer_ids=layer_ids,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            base_project=base_project,
            source_paths=source_paths,
        )
        if existing != document:
            raise OverrideStateError(
                f"History revision {document['revision']} is already occupied"
            )

    def _project_dir(self, project_id: str) -> Path:
        self._validate_project_id(project_id)
        return self._root / project_id

    @staticmethod
    def _validate_project_id(project_id: str) -> None:
        if not _PROJECT_ID_RE.fullmatch(project_id):
            raise OverrideStateError("Invalid project id for override storage")
