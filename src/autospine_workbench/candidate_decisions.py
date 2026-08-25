"""Bind human joint decisions to immutable candidate evidence."""

from __future__ import annotations
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

from .candidate_validation import CandidateValidationError, require_valid_candidate_document
from .contracts import ValidationIssue
from .resolved_project import canonical_sha256
_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
_SAFE_PROJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ACTIONS = frozenset({"accept", "adjust", "reject", "unobservable"})
_BASE_FIELDS = frozenset({"action", "candidate_artifact_sha256", "candidate_id", "final_xy", "reason", "analysis"})
@dataclass(frozen=True, slots=True)
class CandidateDecisionIssue:
    path: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "code": self.code, "message": self.message}
    def to_validation_issue(self) -> ValidationIssue:
        return ValidationIssue(path=self.path, message=self.message, code=self.code)

class CandidateDecisionError(ValueError):
    def __init__(self, issues: CandidateDecisionIssue | list[CandidateDecisionIssue]):
        if isinstance(issues, CandidateDecisionIssue):
            issues = [issues]
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{item.path}: {item.message}" for item in issues))

    def as_validation_issues(self) -> list[ValidationIssue]:
        return [item.to_validation_issue() for item in self.issues]

@dataclass(frozen=True, slots=True)
class _Artifact:
    document: Mapping[str, Any]
    analysis: dict[str, str]
    candidate_owners: Mapping[str, str]
class CandidateDecisionBinder:
    """Resolve decision references without trusting caller-supplied evidence."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def bind(
        self,
        project_id: str,
        decisions: Any,
        *,
        joint_ids: set[str],
        layer_ids: set[str],
        canvas_width: int,
        canvas_height: int,
        stored: bool = False,
    ) -> dict[str, dict[str, Any]]:
        if not isinstance(project_id, str) or not _SAFE_PROJECT.fullmatch(project_id):
            self._fail("$.project_id", "invalid_id", "project id is not a safe path token")
        if not isinstance(decisions, Mapping):
            self._fail("$.joint_decisions", "type", "joint decisions must be an object")
        cache: dict[str, _Artifact] = {}
        result: dict[str, dict[str, Any]] = {}
        for joint_id in sorted(decisions, key=lambda item: str(item)):
            path = f"$.joint_decisions.{joint_id}"
            if not isinstance(joint_id, str) or joint_id not in joint_ids:
                self._fail(path, "unknown_joint", "joint is not in the project")
            decision = decisions[joint_id]
            if not isinstance(decision, Mapping):
                self._fail(path, "type", "decision must be an object")
            unknown = set(decision) - _BASE_FIELDS
            if unknown:
                field = sorted(str(item) for item in unknown)[0]
                self._fail(f"{path}.{field}", "unknown_field", "unknown decision field")
            action = decision.get("action")
            if action not in _ACTIONS:
                self._fail(f"{path}.action", "enum", "unsupported decision action")
            digest = decision.get("candidate_artifact_sha256")
            if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
                self._fail(f"{path}.candidate_artifact_sha256", "hash", "artifact must be a lowercase SHA-256")
            artifact = cache.get(digest)
            if artifact is None:
                artifact = self._read_artifact(
                    project_id, digest,
                    path=f"{path}.candidate_artifact_sha256",
                    joint_ids=joint_ids, layer_ids=layer_ids,
                    canvas_width=canvas_width, canvas_height=canvas_height,
                )
                cache[digest] = artifact
            result[joint_id] = self._bind_one(
                joint_id, decision, artifact, digest, path=path, stored=stored,
                canvas_size=(canvas_width, canvas_height)
            )
        return result

    def _bind_one(
        self,
        joint_id: str,
        decision: Mapping[str, Any],
        artifact: _Artifact,
        digest: str,
        *,
        path: str,
        stored: bool,
        canvas_size: tuple[int, int],
    ) -> dict[str, Any]:
        action = str(decision["action"])
        candidate_id = decision.get("candidate_id")
        candidate: Mapping[str, Any] | None = None
        if action == "unobservable":
            if candidate_id is not None:
                self._fail(f"{path}.candidate_id", "forbidden", "unobservable has no candidate")
        else:
            if not isinstance(candidate_id, str) or not candidate_id:
                self._fail(f"{path}.candidate_id", "required", "candidate id is required")
            owner = artifact.candidate_owners.get(candidate_id)
            if owner is None:
                self._fail(f"{path}.candidate_id", "candidate_not_found", "candidate is not in the artifact")
            if owner != joint_id:
                self._fail(f"{path}.candidate_id", "wrong_joint", f"candidate belongs to {owner}")
            candidate = self._candidate(artifact.document, joint_id, candidate_id)
        reason = decision.get("reason")
        if action in {"adjust", "reject", "unobservable"} or reason is not None:
            if not isinstance(reason, str) or not reason.strip():
                self._fail(f"{path}.reason", "required", "a non-empty reason is required")
            if len(reason) > 1000:
                self._fail(f"{path}.reason", "length", "reason must be at most 1000 characters")
        if not stored and "analysis" in decision:
            self._fail(f"{path}.analysis", "forbidden", "analysis is derived from the artifact")
        if stored and decision.get("analysis") != artifact.analysis:
            self._fail(f"{path}.analysis", "provenance_mismatch", "stored analysis does not match the artifact")
        output: dict[str, Any] = {"action": action, "candidate_artifact_sha256": digest}
        if candidate_id is not None:
            output["candidate_id"] = candidate_id
        if action == "accept":
            assert candidate is not None
            derived_xy = _point(candidate["xy"])
            if not stored and "final_xy" in decision:
                self._fail(f"{path}.final_xy", "derived_field", "accepted coordinates are artifact-derived")
            if stored and not _same_point(decision.get("final_xy"), derived_xy):
                self._fail(f"{path}.final_xy", "derived_mismatch", "stored coordinates do not match the candidate")
            output["final_xy"] = derived_xy
            if reason is not None:
                output["reason"] = reason
        elif action == "adjust":
            output["final_xy"] = self._manual_point(
                decision.get("final_xy"), path, canvas_size
            )
            output["reason"] = reason
        elif action in {"reject", "unobservable"}:
            if "final_xy" in decision:
                self._fail(f"{path}.final_xy", "forbidden", f"{action} has no final coordinates")
            output["reason"] = reason
        output["analysis"] = dict(artifact.analysis)
        return output

    def _read_artifact(
        self,
        project_id: str,
        digest: str,
        *,
        path: str,
        joint_ids: set[str],
        layer_ids: set[str],
        canvas_width: int,
        canvas_height: int,
    ) -> _Artifact:
        lexical = self.state_root / "analysis" / project_id / "joint-candidates" / f"{digest}.json"
        try:
            analysis_root = (self.state_root / "analysis").resolve(strict=True)
            resolved = lexical.resolve(strict=True)
            resolved.relative_to(analysis_root)
        except FileNotFoundError:
            self._fail(path, "artifact_missing", "candidate artifact does not exist")
        except (OSError, ValueError):
            self._fail(path, "unsafe_path", "candidate artifact path is unsafe")
        if lexical.is_symlink() or not resolved.is_file():
            self._fail(path, "unsafe_path", "candidate artifact must be a regular file")
        try:
            if resolved.stat().st_size > _MAX_ARTIFACT_BYTES:
                self._fail(path, "artifact_too_large", "candidate artifact exceeds 2 MiB")
            raw = resolved.read_bytes()
        except OSError:
            self._fail(path, "artifact_unreadable", "candidate artifact cannot be read")
        if len(raw) > _MAX_ARTIFACT_BYTES:
            self._fail(path, "artifact_too_large", "candidate artifact exceeds 2 MiB")
        document = self._decode_document(raw, path)
        try:
            observed = canonical_sha256(document)
        except (TypeError, ValueError):
            self._fail(path, "artifact_json", "candidate artifact is not canonical JSON data")
        if observed != digest:
            self._fail(path, "content_address_mismatch", "candidate artifact content does not match its SHA-256")
        if document.get("project_id") != project_id:
            self._fail(path, "wrong_project", "candidate artifact belongs to another project")
        try:
            require_valid_candidate_document(
                document,
                joint_ids=joint_ids,
                layer_ids=layer_ids,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
            )
        except CandidateValidationError as exc:
            detail = exc.issues[0] if exc.issues else None
            message = "candidate artifact failed semantic validation"
            if detail is not None:
                message = f"{message}: {detail.path}: {detail.message}"
            self._fail(path, "invalid_artifact", message)
        analysis = self._derive_analysis(document, path)
        owners = {
            candidate["candidate_id"]: joint_id
            for joint_id, item in document["joints"].items()
            for candidate in item["candidates"]
        }
        return _Artifact(document=document, analysis=analysis, candidate_owners=owners)

    def _derive_analysis(self, document: Mapping[str, Any], path: str) -> dict[str, str]:
        source, analysis = document.get("source"), document.get("analysis")
        values = {
            "provider": analysis.get("provider") if isinstance(analysis, Mapping) else None,
            "provider_version": analysis.get("provider_version") if isinstance(analysis, Mapping) else None,
            "input_sha256": source.get("base_project_sha256") if isinstance(source, Mapping) else None,
            "config_sha256": analysis.get("config_sha256") if isinstance(analysis, Mapping) else None,
            "run_sha256": analysis.get("run_sha256") if isinstance(analysis, Mapping) else None,
        }
        if not isinstance(values["provider"], str) or not _SAFE_PROJECT.fullmatch(values["provider"]):
            self._fail(path, "invalid_artifact", "artifact provider id is invalid")
        version = values["provider_version"]
        if not isinstance(version, str) or not version or len(version) > 64:
            self._fail(path, "invalid_artifact", "artifact provider version is invalid")
        for field in ("input_sha256", "config_sha256", "run_sha256"):
            if not isinstance(values[field], str) or not _SHA256.fullmatch(values[field]):
                self._fail(path, "invalid_artifact", f"artifact {field} is not a SHA-256")
        return values  # type: ignore[return-value]

    @staticmethod
    def _candidate(document: Mapping[str, Any], joint_id: str, candidate_id: str) -> Mapping[str, Any]:
        return next(item for item in document["joints"][joint_id]["candidates"] if item["candidate_id"] == candidate_id)

    def _manual_point(self, value: Any, path: str, canvas_size: tuple[int, int]) -> list[float]:
        if not _valid_point(value):
            self._fail(f"{path}.final_xy", "coordinate", "final_xy must contain two finite numbers")
        point = _point(value)
        if not 0 <= point[0] <= canvas_size[0] or not 0 <= point[1] <= canvas_size[1]:
            self._fail(f"{path}.final_xy", "bounds", "final_xy lies outside the canvas")
        return point

    @staticmethod
    def _decode_document(raw: bytes, path: str) -> Mapping[str, Any]:
        try:
            text = raw.decode("utf-8")
            document = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        except UnicodeDecodeError as exc:
            raise CandidateDecisionError(CandidateDecisionIssue(path, "artifact_encoding", "artifact is not UTF-8")) from exc
        except _DuplicateKey as exc:
            raise CandidateDecisionError(CandidateDecisionIssue(path, "duplicate_key", f"artifact repeats JSON key: {exc}")) from exc
        except (json.JSONDecodeError, _NonFiniteJson) as exc:
            raise CandidateDecisionError(CandidateDecisionIssue(path, "artifact_json", "artifact is not strict JSON")) from exc
        if not isinstance(document, Mapping):
            raise CandidateDecisionError(CandidateDecisionIssue(path, "artifact_json", "artifact root must be an object"))
        return document

    @staticmethod
    def _fail(path: str, code: str, message: str) -> None:
        raise CandidateDecisionError(CandidateDecisionIssue(path, code, message))

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

def _valid_point(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item) for item in value)
    )

def _point(value: Any) -> list[float]:
    return [0.0 if float(item) == 0 else float(item) for item in value]

def _same_point(value: Any, expected: list[float]) -> bool:
    return _valid_point(value) and _point(value) == expected
