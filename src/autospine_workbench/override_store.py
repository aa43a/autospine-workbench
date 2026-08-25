"""Append-only persistence for reviewed project overrides.

The history directory is the source of truth. ``latest.json`` is an atomically
replaceable read cache, while the legacy ``<project>.json`` document remains a
read-only migration source.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping

from .candidate_decisions import CandidateDecisionBinder, CandidateDecisionError
from .contracts import (
    ContractValidationError,
    OVERRIDE_SCHEMA_VERSION,
    empty_overrides,
    normalize_override_request,
)


_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_HISTORY_NAME_RE = re.compile(r"^r([0-9]{6,})\.json$")
_MAX_OVERRIDE_BYTES = 2 * 1024 * 1024


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
        self._decision_binder = CandidateDecisionBinder(state_root)
        self._lock = threading.RLock()

    def load(
        self,
        project_id: str,
        *,
        joint_ids: set[str],
        layer_ids: set[str],
        canvas_width: int,
        canvas_height: int,
    ) -> dict[str, Any]:
        """Return the highest valid persisted revision for a project."""

        self._validate_project_id(project_id)
        documents: dict[int, dict[str, Any]] = {}
        for path, expected_revision in self._document_paths(project_id):
            document = self._read_document(
                path,
                project_id=project_id,
                joint_ids=joint_ids,
                layer_ids=layer_ids,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
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
        joint_ids: set[str],
        layer_ids: set[str],
        canvas_width: int,
        canvas_height: int,
    ) -> dict[str, Any]:
        """Compare revisions, append one snapshot, then atomically update latest."""

        with self._lock:
            current = self.load(
                project_id,
                joint_ids=joint_ids,
                layer_ids=layer_ids,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
            )
            try:
                requested_revision, normalized = normalize_override_request(
                    payload,
                    project_id=project_id,
                    current_revision=current["revision"],
                    joint_ids=joint_ids,
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

            normalized["revision"] = current["revision"] + 1
            project_dir = self._project_dir(project_id)
            history_dir = project_dir / "history"
            history_dir.mkdir(parents=True, exist_ok=True)

            if current["revision"] > 0:
                self._ensure_snapshot(
                    history_dir,
                    current,
                    project_id=project_id,
                    joint_ids=joint_ids,
                    layer_ids=layer_ids,
                    canvas_width=canvas_width,
                    canvas_height=canvas_height,
                )
            try:
                self._publish_snapshot(history_dir, normalized)
            except FileExistsError as exc:
                observed = self.load(
                    project_id,
                    joint_ids=joint_ids,
                    layer_ids=layer_ids,
                    canvas_width=canvas_width,
                    canvas_height=canvas_height,
                )
                raise OverrideRevisionConflict(
                    requested_revision, observed["revision"]
                ) from exc
            self._write_latest(project_dir / "latest.json", normalized)
            return normalized

    def _document_paths(self, project_id: str) -> list[tuple[Path, int | None]]:
        project_dir = self._project_dir(project_id)
        paths: list[tuple[Path, int | None]] = []
        legacy_path = self._root / f"{project_id}.json"
        latest_path = project_dir / "latest.json"
        if legacy_path.is_file():
            paths.append((legacy_path, None))
        if latest_path.is_file():
            paths.append((latest_path, None))

        history_dir = project_dir / "history"
        if history_dir.is_dir():
            try:
                entries = sorted(history_dir.iterdir(), key=lambda item: item.name)
            except OSError as exc:
                raise OverrideStateError("Could not enumerate override history") from exc
            for path in entries:
                match = _HISTORY_NAME_RE.fullmatch(path.name)
                if match and path.is_file():
                    paths.append((path, int(match.group(1))))
        return paths

    def _read_document(
        self,
        path: Path,
        *,
        project_id: str,
        joint_ids: set[str],
        layer_ids: set[str],
        canvas_width: int,
        canvas_height: int,
    ) -> dict[str, Any]:
        try:
            if path.stat().st_size > _MAX_OVERRIDE_BYTES:
                raise OverrideStateError(f"Override document is too large: {path.name}")
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle, object_pairs_hook=_unique_object)
        except OverrideStateError:
            raise
        except _DuplicateJsonKey as exc:
            raise OverrideStateError(
                f"Override document contains duplicate field {exc}: {path.name}"
            ) from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise OverrideStateError(f"Cannot read override document: {path.name}") from exc
        if not isinstance(raw, Mapping):
            raise OverrideStateError("Override document must be a JSON object")
        revision = raw.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise OverrideStateError("Override revision is invalid")
        stored_project_id = raw.get("project_id")
        if stored_project_id is not None and stored_project_id != project_id:
            raise OverrideStateError("Override document belongs to another project")
        request = {
            "schema_version": raw.get("schema_version", OVERRIDE_SCHEMA_VERSION),
            "base_revision": revision,
            "joint_overrides": raw.get("joint_overrides", {}),
            "joint_decisions": raw.get("joint_decisions", {}),
            "layer_overrides": raw.get("layer_overrides", {}),
            "notes": raw.get("notes", ""),
        }
        try:
            _, normalized = normalize_override_request(
                request,
                project_id=project_id,
                current_revision=revision,
                joint_ids=joint_ids,
                layer_ids=layer_ids,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
                stored=True,
            )
        except ContractValidationError as exc:
            raise OverrideStateError(f"Stored overrides are invalid: {exc}") from exc
        try:
            normalized["joint_decisions"] = self._decision_binder.bind(
                project_id,
                normalized["joint_decisions"],
                joint_ids=joint_ids,
                layer_ids=layer_ids,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
                stored=True,
            )
        except CandidateDecisionError as exc:
            raise OverrideStateError(f"Stored candidate decisions are invalid: {exc}") from exc
        normalized["revision"] = revision
        return normalized

    def _ensure_snapshot(
        self,
        history_dir: Path,
        document: Mapping[str, Any],
        *,
        project_id: str,
        joint_ids: set[str],
        layer_ids: set[str],
        canvas_width: int,
        canvas_height: int,
    ) -> None:
        destination = history_dir / self._history_name(int(document["revision"]))
        if not destination.exists():
            try:
                self._publish_snapshot(history_dir, document)
                return
            except FileExistsError:
                pass
        existing = self._read_document(
            destination,
            project_id=project_id,
            joint_ids=joint_ids,
            layer_ids=layer_ids,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        )
        if existing != document:
            raise OverrideStateError(
                f"History revision {document['revision']} is already occupied"
            )

    def _publish_snapshot(self, history_dir: Path, document: Mapping[str, Any]) -> None:
        destination = history_dir / self._history_name(int(document["revision"]))
        encoded = self._encode(document)
        temp_path: Path | None = None
        try:
            fd, raw_temp_path = tempfile.mkstemp(
                prefix=f".{destination.stem}.", suffix=".tmp", dir=history_dir
            )
            temp_path = Path(raw_temp_path)
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temp_path, destination)
        except FileExistsError:
            raise
        except OSError as exc:
            raise OverrideStoreError("Could not append override history") from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _write_latest(self, destination: Path, document: Mapping[str, Any]) -> None:
        encoded = self._encode(document)
        temp_path: Path | None = None
        try:
            fd, raw_temp_path = tempfile.mkstemp(
                prefix=".latest.", suffix=".tmp", dir=destination.parent
            )
            temp_path = Path(raw_temp_path)
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, destination)
            temp_path = None
        except OSError as exc:
            raise OverrideStoreError("Could not atomically save overrides") from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _encode(document: Mapping[str, Any]) -> bytes:
        return (
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")

    def _project_dir(self, project_id: str) -> Path:
        self._validate_project_id(project_id)
        return self._root / project_id

    @staticmethod
    def _history_name(revision: int) -> str:
        return f"r{revision:06d}.json"

    @staticmethod
    def _validate_project_id(project_id: str) -> None:
        if not _PROJECT_ID_RE.fullmatch(project_id):
            raise OverrideStateError("Invalid project id for override storage")


class _DuplicateJsonKey(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result
