"""Strict read boundary for content-addressed analysis artifacts."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping

from .alpha_evidence_validation import (
    AlphaEvidenceValidationError,
    require_valid_alpha_geometry_evidence,
)
from .candidate_validation import CandidateValidationError, require_valid_candidate_document
from .resolved_project import canonical_sha256


_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
_MAX_LIST_ITEMS = 256
_MAX_LIST_BYTES = 64 * 1024 * 1024


class AnalysisRepositoryError(RuntimeError):
    pass


class AnalysisArtifactNotFound(AnalysisRepositoryError):
    pass


class AnalysisArtifactRepository:
    def __init__(self, state_root: Path) -> None:
        self.root = Path(state_root) / "analysis"

    def list_joint_candidates(
        self,
        project_id: str,
        *,
        joint_ids: set[str],
        layer_ids: set[str],
        canvas_width: int,
        canvas_height: int,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for path in self._artifact_paths(project_id, "joint-candidates"):
            digest = path.stem
            document = self.read_joint_candidates(
                project_id,
                digest,
                joint_ids=joint_ids,
                layer_ids=layer_ids,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
            )
            items.append(_candidate_summary(document, digest))
        return {
            "schema_version": "autospine-workbench.analysis-index/v1",
            "project_id": project_id,
            "kind": "joint-candidates",
            "count": len(items),
            "items": items,
        }

    def read_joint_candidates(
        self,
        project_id: str,
        digest: str,
        *,
        joint_ids: set[str],
        layer_ids: set[str],
        canvas_width: int,
        canvas_height: int,
    ) -> dict[str, Any]:
        document = self.read_json(project_id, "joint-candidates", digest)
        try:
            require_valid_candidate_document(
                document,
                joint_ids=joint_ids,
                layer_ids=layer_ids,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
            )
        except CandidateValidationError as exc:
            raise AnalysisRepositoryError(f"Candidate artifact is invalid: {exc}") from exc
        return document

    def list_alpha_geometry_evidence(
        self,
        project_id: str,
        *,
        joint_ids: set[str],
        layer_ids: set[str],
        canvas_width: int,
        canvas_height: int,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for path in self._artifact_paths(project_id, "alpha-geometry-evidence"):
            digest = path.stem
            document = self.read_alpha_geometry_evidence(
                project_id,
                digest,
                joint_ids=joint_ids,
                layer_ids=layer_ids,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
            )
            items.append(_geometry_summary(document, digest))
        return {
            "schema_version": "autospine-workbench.analysis-index/v1",
            "project_id": project_id,
            "kind": "alpha-geometry-evidence",
            "count": len(items),
            "items": items,
        }

    def read_alpha_geometry_evidence(
        self,
        project_id: str,
        digest: str,
        *,
        joint_ids: set[str],
        layer_ids: set[str],
        canvas_width: int,
        canvas_height: int,
    ) -> dict[str, Any]:
        document = self.read_json(project_id, "alpha-geometry-evidence", digest)
        try:
            require_valid_alpha_geometry_evidence(
                document,
                project_id=project_id,
                joint_ids=joint_ids,
                layer_ids=layer_ids,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
            )
        except AlphaEvidenceValidationError as exc:
            raise AnalysisRepositoryError(f"Alpha geometry artifact is invalid: {exc}") from exc
        return document

    def read_json(self, project_id: str, kind: str, digest: str) -> dict[str, Any]:
        directory = self._directory(project_id, kind, require=True)
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise AnalysisArtifactNotFound("Analysis artifact was not found")
        assert directory is not None
        lexical = directory / f"{digest}.json"
        try:
            resolved = lexical.resolve(strict=True)
            resolved.relative_to(directory)
        except (OSError, ValueError) as exc:
            raise AnalysisArtifactNotFound("Analysis artifact was not found") from exc
        if lexical.is_symlink() or not resolved.is_file():
            raise AnalysisArtifactNotFound("Analysis artifact was not found")
        try:
            if resolved.stat().st_size > _MAX_ARTIFACT_BYTES:
                raise AnalysisRepositoryError("Analysis artifact exceeds 4 MiB")
            with resolved.open("r", encoding="utf-8") as stream:
                document = json.load(
                    stream,
                    object_pairs_hook=_unique_object,
                    parse_constant=_reject_constant,
                )
        except AnalysisRepositoryError:
            raise
        except (_DuplicateKey, _NonFiniteJson, OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AnalysisRepositoryError("Analysis artifact is not strict JSON") from exc
        if not isinstance(document, dict) or canonical_sha256(document) != digest:
            raise AnalysisRepositoryError("Analysis artifact does not match its content address")
        if document.get("project_id") != project_id:
            raise AnalysisRepositoryError("Analysis artifact belongs to another project")
        return document

    def _artifact_paths(self, project_id: str, kind: str) -> list[Path]:
        directory = self._directory(project_id, kind, require=False)
        if directory is None:
            return []
        try:
            paths = sorted(directory.glob("*.json"), key=lambda item: item.name)
            listed_bytes = sum(path.lstat().st_size for path in paths)
        except OSError as exc:
            raise AnalysisRepositoryError("Could not enumerate analysis artifacts") from exc
        if len(paths) > _MAX_LIST_ITEMS:
            raise AnalysisRepositoryError("Analysis artifact list exceeds the safety limit")
        if listed_bytes > _MAX_LIST_BYTES:
            raise AnalysisRepositoryError("Analysis artifact index exceeds 64 MiB")
        if any(not _SHA256.fullmatch(path.stem) or path.is_symlink() for path in paths):
            raise AnalysisRepositoryError("Analysis artifact index contains an unsafe entry")
        return paths

    def _directory(self, project_id: str, kind: str, *, require: bool) -> Path | None:
        if not _SAFE_TOKEN.fullmatch(project_id) or not _SAFE_TOKEN.fullmatch(kind):
            raise AnalysisArtifactNotFound("Analysis artifact was not found")
        lexical = self.root / project_id / kind
        try:
            root = self.root.resolve(strict=require)
            directory = lexical.resolve(strict=require)
            directory.relative_to(root)
        except FileNotFoundError:
            if require:
                raise AnalysisArtifactNotFound("Analysis artifact was not found")
            return None
        except (OSError, ValueError) as exc:
            raise AnalysisRepositoryError("Analysis artifact directory is unsafe") from exc
        if not directory.is_dir():
            if require:
                raise AnalysisArtifactNotFound("Analysis artifact was not found")
            return None
        return directory


def _candidate_summary(document: Mapping[str, Any], digest: str) -> dict[str, Any]:
    analysis = document["analysis"]
    methods: dict[str, int] = {}
    candidate_count = 0
    for evidence in document["joints"].values():
        for candidate in evidence["candidates"]:
            method = str(candidate["method"])
            methods[method] = methods.get(method, 0) + 1
            candidate_count += 1
    return {
        "artifact_sha256": digest,
        "provider": analysis["provider"],
        "provider_version": analysis["provider_version"],
        "input_sha256": document["source"]["base_project_sha256"],
        "config_sha256": analysis["config_sha256"],
        "run_sha256": analysis["run_sha256"],
        "qa_status": document["qa"]["status"],
        "qa_flags": list(document["qa"]["flags"]),
        "joint_count": len(document["joints"]),
        "candidate_count": candidate_count,
        "method_counts": dict(sorted(methods.items())),
    }


def _geometry_summary(document: Mapping[str, Any], digest: str) -> dict[str, Any]:
    analysis = document["analysis"]
    relations: dict[str, int] = {}
    observability: dict[str, int] = {}
    for contact in document["contacts"]:
        relation = str(contact["relation"])
        relations[relation] = relations.get(relation, 0) + 1
    for item in document["observability"].values():
        status = str(item["status"])
        observability[status] = observability.get(status, 0) + 1
    return {
        "artifact_sha256": digest,
        "provider": analysis["provider"],
        "provider_version": analysis["provider_version"],
        "input_sha256": analysis["input_sha256"],
        "config_sha256": analysis["config_sha256"],
        "run_sha256": analysis["run_sha256"],
        "qa_status": document["qa"]["status"],
        "qa_flags": list(document["qa"]["flags"]),
        "layer_count": len(document["layers"]),
        "path_count": len(document["paths"]),
        "contact_count": len(document["contacts"]),
        "relation_counts": dict(sorted(relations.items())),
        "observability_counts": dict(sorted(observability.items())),
    }


class _DuplicateKey(ValueError):
    pass


class _NonFiniteJson(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise _NonFiniteJson(value)
