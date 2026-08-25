"""Bind split review decisions to immutable previews and current authoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping

from .contract_types import MAX_REASON_LENGTH, ValidationIssue
from .manifest_bundle import LayerManifestBundleError, LayerManifestBundleReader
from .resolved_project import canonical_sha256
from .split_binding_target import (
    SplitBindingArtifactError,
    SplitBindingTargetError,
    preview_matches_current,
)
from .split_preview_reader import SplitPreviewReader, SplitPreviewReaderError


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ACTIONS = frozenset({"accept", "reject"})
_DERIVED = frozenset(
    {
        "operation_config_sha256",
        "review_target_sha256",
        "analysis",
        "binding_status",
    }
)
_CLIENT_FIELDS = frozenset({"action", "split_artifact_sha256", "reason"})


@dataclass(frozen=True, slots=True)
class SplitDecisionBindingIssue:
    path: str
    code: str
    message: str

    def to_validation_issue(self) -> ValidationIssue:
        return ValidationIssue(self.path, self.message, self.code)


class SplitDecisionBindingError(ValueError):
    """Raised when a split decision cannot be safely bound or revalidated."""

    def __init__(
        self, issues: SplitDecisionBindingIssue | list[SplitDecisionBindingIssue]
    ) -> None:
        if isinstance(issues, SplitDecisionBindingIssue):
            issues = [issues]
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{item.path}: {item.message}" for item in issues))

    def as_validation_issues(self) -> list[ValidationIssue]:
        return [item.to_validation_issue() for item in self.issues]


@dataclass(frozen=True, slots=True)
class _Evidence:
    document: Mapping[str, Any]
    manifest: Mapping[str, Any]
    operation_sha256: str
    review_sha256: str
    analysis: dict[str, str]


class SplitDecisionBinder:
    """Resolve split decisions without trusting caller-supplied provenance."""

    def __init__(self, state_root: Path) -> None:
        self._previews = SplitPreviewReader(state_root)
        self._manifests = LayerManifestBundleReader(state_root)

    def bind(
        self,
        project_id: str,
        decisions: Any,
        *,
        resolved: Mapping[str, Any],
        source_paths: Mapping[str, Path],
        stored: bool = False,
    ) -> dict[str, dict[str, Any]]:
        """Bind client choices or revalidate persisted choices deterministically."""

        if not isinstance(project_id, str) or not _SAFE_ID.fullmatch(project_id):
            self._fail("$.project_id", "invalid_id", "project id is invalid")
        if not isinstance(decisions, Mapping):
            self._fail("$.split_decisions", "type", "split decisions must be an object")
        if not isinstance(resolved, Mapping) or not isinstance(source_paths, Mapping):
            self._fail("$", "context", "resolved project and source paths are required")
        preview_cache: dict[str, _Evidence] = {}
        result: dict[str, dict[str, Any]] = {}
        for layer_id in sorted(decisions, key=lambda value: str(value)):
            path = f"$.split_decisions.{layer_id}"
            if not isinstance(layer_id, str) or not _SAFE_ID.fullmatch(layer_id):
                self._fail(path, "invalid_id", "source layer id is invalid")
            raw = decisions[layer_id]
            action, digest, reason = self._validate_decision(raw, path, stored)
            evidence = preview_cache.get(digest)
            if evidence is None:
                evidence = self._load_evidence(project_id, digest, path)
                preview_cache[digest] = evidence
            if evidence.document.get("layer_id") != layer_id:
                self._fail(path, "wrong_layer", "split preview belongs to another layer")
            source_path = source_paths.get(layer_id)
            if source_path is None:
                self._fail(path, "source_missing", "current source raster is missing")
            current = self._binding_is_current(
                evidence, resolved, Path(source_path), path
            )
            expected = self._derived(evidence, "current" if current else "stale")
            if stored:
                self._verify_stored(raw, expected, path)
            elif (
                not current
                or evidence.document.get("resolved_snapshot_sha256")
                != resolved.get("sha256")
            ):
                self._fail(path, "stale_artifact", "split preview no longer matches current inputs")
            output: dict[str, Any] = {
                "action": action,
                "split_artifact_sha256": digest,
                **expected,
            }
            if reason is not None:
                output["reason"] = reason
            result[layer_id] = dict(sorted(output.items()))
        return dict(sorted(result.items()))

    def _validate_decision(
        self, value: Any, path: str, stored: bool
    ) -> tuple[str, str, str | None]:
        if not isinstance(value, Mapping):
            self._fail(path, "type", "decision must be an object")
        allowed = set(_CLIENT_FIELDS | (_DERIVED if stored else frozenset()))
        unknown = set(value) - allowed
        if unknown:
            field = sorted(str(item) for item in unknown)[0]
            code = "derived_field" if field in _DERIVED else "unknown_field"
            self._fail(f"{path}.{field}", code, "decision field is not allowed")
        if not stored:
            spoofed = sorted(set(value) & _DERIVED)
            if spoofed:
                self._fail(
                    f"{path}.{spoofed[0]}",
                    "derived_field",
                    "field must be derived by the binder",
                )
        action = value.get("action")
        if action not in _ACTIONS:
            self._fail(f"{path}.action", "enum", "action must be accept or reject")
        digest = value.get("split_artifact_sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            self._fail(
                f"{path}.split_artifact_sha256",
                "hash",
                "artifact must be a lowercase SHA-256",
            )
        reason = value.get("reason")
        if action == "reject" and reason is None:
            self._fail(f"{path}.reason", "required", "reject requires a reason")
        if reason is not None:
            if not isinstance(reason, str) or not reason.strip():
                self._fail(f"{path}.reason", "required", "reason must not be blank")
            if len(reason) > MAX_REASON_LENGTH:
                self._fail(f"{path}.reason", "length", "reason is too long")
        if stored and value.get("binding_status") not in {"current", "stale"}:
            self._fail(
                f"{path}.binding_status",
                "enum",
                "stored binding status is invalid",
            )
        return str(action), str(digest), reason

    def _load_evidence(self, project_id: str, digest: str, path: str) -> _Evidence:
        artifact_path = f"{path}.split_artifact_sha256"
        try:
            preview = self._previews.load(project_id, digest)
        except SplitPreviewReaderError as exc:
            code = "artifact_missing" if "not found" in str(exc).lower() else "artifact_invalid"
            self._fail(artifact_path, code, str(exc))
        document = preview.document
        manifest_sha = str(document["layer_manifest_sha256"])
        try:
            bundle = self._manifests.load(project_id, manifest_sha)
        except LayerManifestBundleError as exc:
            code = "manifest_missing" if "not found" in str(exc).lower() else "manifest_invalid"
            self._fail(f"{artifact_path}.layer_manifest", code, str(exc))
        operation = document["review_target"]["operation"]
        algorithm = operation["algorithm"]
        analysis = {
            "algorithm_id": algorithm["id"],
            "algorithm_version": algorithm["version"],
            "layer_manifest_sha256": manifest_sha,
            "resolved_snapshot_sha256": document["resolved_snapshot_sha256"],
            "split_spec_sha256": canonical_sha256(document["split_spec"]),
        }
        return _Evidence(
            document=document,
            manifest=bundle.manifest,
            operation_sha256=document["operation_config_sha256"],
            review_sha256=document["review_target_sha256"],
            analysis=dict(sorted(analysis.items())),
        )

    def _binding_is_current(
        self,
        evidence: _Evidence,
        resolved: Mapping[str, Any],
        source_path: Path,
        path: str,
    ) -> bool:
        try:
            return preview_matches_current(
                evidence.document, evidence.manifest, resolved, source_path
            )
        except SplitBindingArtifactError as exc:
            self._fail(path, "artifact_invalid", str(exc))
        except SplitBindingTargetError as exc:
            self._fail(path, "binding_context", str(exc))

    @staticmethod
    def _derived(evidence: _Evidence, status: str) -> dict[str, Any]:
        return {
            "analysis": dict(evidence.analysis),
            "binding_status": status,
            "operation_config_sha256": evidence.operation_sha256,
            "review_target_sha256": evidence.review_sha256,
        }

    def _verify_stored(
        self, value: Mapping[str, Any], expected: Mapping[str, Any], path: str
    ) -> None:
        for field in (
            "operation_config_sha256",
            "review_target_sha256",
            "analysis",
        ):
            if value.get(field) != expected[field]:
                self._fail(
                    f"{path}.{field}",
                    "derived_mismatch",
                    "stored field does not match the split artifact",
                )

    @staticmethod
    def _fail(path: str, code: str, message: str) -> None:
        raise SplitDecisionBindingError(SplitDecisionBindingIssue(path, code, message))
