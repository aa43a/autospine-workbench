"""Strict client and persisted contracts for bilateral split review decisions.

This module validates provenance-shaped data only.  It does not load split
artifacts or decide whether a referenced artifact still matches the project;
that responsibility belongs to the later binder.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from .contract_types import (
    MAX_REASON_LENGTH,
    OVERRIDE_SCHEMA_VERSION_V1,
    OVERRIDE_SCHEMA_VERSION_V2,
    ValidationIssue,
)


_ACTIONS = frozenset({"accept", "reject"})
_ANALYSIS_FIELDS = (
    "layer_manifest_sha256",
    "resolved_snapshot_sha256",
    "split_spec_sha256",
    "algorithm_id",
    "algorithm_version",
)
_DERIVED_FIELDS = frozenset(
    {
        "operation_config_sha256",
        "review_target_sha256",
        "analysis",
        "binding_status",
    }
)
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def normalize_split_decision_root(
    root: Mapping[str, Any],
    *,
    schema_version: Any,
    layer_ids: set[str],
    issues: list[ValidationIssue],
    stored: bool = False,
) -> dict[str, dict[str, Any]]:
    """Normalize the override root field while enforcing its v3 boundary."""

    if (
        schema_version in {OVERRIDE_SCHEMA_VERSION_V1, OVERRIDE_SCHEMA_VERSION_V2}
        and "split_decisions" in root
    ):
        issues.append(
            ValidationIssue("$.split_decisions", "requires override/v3", "version")
        )
    return normalize_split_decisions(
        root.get("split_decisions", {}),
        layer_ids=layer_ids,
        issues=issues,
        stored=stored,
    )


def normalize_split_decisions(
    value: Any,
    *,
    layer_ids: set[str],
    issues: list[ValidationIssue],
    stored: bool = False,
) -> dict[str, dict[str, Any]]:
    """Normalize source-layer split decisions and append every validation issue.

    Client decisions may name only an action, an immutable split artifact, and
    an optional review reason.  Persisted decisions additionally require all
    binder-derived identities needed to revalidate that decision later.
    """

    path = "$.split_decisions"
    if not isinstance(value, Mapping):
        issues.append(ValidationIssue(path, "must be a JSON object", "type"))
        return {}

    sortable: list[tuple[str, Any]] = []
    for key, raw in value.items():
        if not isinstance(key, str):
            issues.append(ValidationIssue(path, "all keys must be strings", "type"))
        else:
            sortable.append((key, raw))

    normalized: dict[str, dict[str, Any]] = {}
    for layer_id, raw in sorted(sortable, key=lambda pair: pair[0]):
        item_path = f"{path}.{layer_id}"
        before = len(issues)
        if not _SAFE_ID.fullmatch(layer_id) or layer_id not in layer_ids:
            issues.append(ValidationIssue(item_path, "unknown source layer id", "unknown_id"))
            continue
        if not isinstance(raw, Mapping):
            issues.append(ValidationIssue(item_path, "must be a JSON object", "type"))
            continue

        allowed = {"action", "split_artifact_sha256", "reason"}
        if stored:
            allowed.update(_DERIVED_FIELDS)
        _reject_unknown_fields(raw, allowed, item_path, issues)

        action = raw.get("action")
        if action not in _ACTIONS:
            issues.append(
                ValidationIssue(
                    f"{item_path}.action",
                    f"must be one of {sorted(_ACTIONS)}",
                    "enum",
                )
            )
        artifact_sha = _required_sha(
            raw.get("split_artifact_sha256"),
            f"{item_path}.split_artifact_sha256",
            issues,
        )
        reason = _normalize_reason(raw, action, item_path, issues)
        operation_sha = _derived_sha(
            raw, "operation_config_sha256", item_path, stored, issues
        )
        review_sha = _derived_sha(
            raw, "review_target_sha256", item_path, stored, issues
        )
        analysis = _normalize_analysis(raw, item_path, stored, issues)
        binding_status = _normalize_binding_status(raw, item_path, stored, issues)

        if len(issues) != before:
            continue
        item: dict[str, Any] = {
            "action": action,
            "split_artifact_sha256": artifact_sha,
        }
        if reason is not None:
            item["reason"] = reason
        if stored:
            item["operation_config_sha256"] = operation_sha
            item["review_target_sha256"] = review_sha
            item["analysis"] = analysis
            item["binding_status"] = binding_status
        normalized[layer_id] = dict(sorted(item.items()))
    return dict(sorted(normalized.items()))


def _reject_unknown_fields(
    value: Mapping[Any, Any], allowed: set[str], path: str, issues: list[ValidationIssue]
) -> None:
    for key in value:
        if not isinstance(key, str):
            issues.append(ValidationIssue(path, "all keys must be strings", "type"))
        elif key not in allowed:
            code = "derived_field" if key in _DERIVED_FIELDS else "unknown_field"
            issues.append(ValidationIssue(f"{path}.{key}", "field is not allowed", code))


def _required_sha(value: Any, path: str, issues: list[ValidationIssue]) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        issues.append(ValidationIssue(path, "must be a lowercase SHA-256", "hash"))
        return ""
    return value


def _derived_sha(
    value: Mapping[str, Any],
    field: str,
    path: str,
    stored: bool,
    issues: list[ValidationIssue],
) -> str | None:
    if not stored:
        return None
    if field not in value:
        issues.append(ValidationIssue(f"{path}.{field}", "is required", "required"))
        return None
    return _required_sha(value.get(field), f"{path}.{field}", issues)


def _normalize_reason(
    value: Mapping[str, Any], action: Any, path: str, issues: list[ValidationIssue]
) -> str | None:
    present = "reason" in value
    if action == "reject" and not present:
        issues.append(ValidationIssue(f"{path}.reason", "is required for reject", "required"))
        return None
    if not present:
        return None
    reason = value.get("reason")
    if not isinstance(reason, str):
        issues.append(ValidationIssue(f"{path}.reason", "must be a string", "type"))
        return None
    if not reason.strip():
        issues.append(ValidationIssue(f"{path}.reason", "must not be blank", "length"))
    elif len(reason) > MAX_REASON_LENGTH:
        issues.append(
            ValidationIssue(
                f"{path}.reason",
                f"must be at most {MAX_REASON_LENGTH} characters",
                "length",
            )
        )
    return reason


def _normalize_analysis(
    value: Mapping[str, Any], path: str, stored: bool, issues: list[ValidationIssue]
) -> dict[str, str] | None:
    if not stored:
        return None
    if "analysis" not in value:
        issues.append(ValidationIssue(f"{path}.analysis", "is required", "required"))
        return None
    analysis = value.get("analysis")
    if not isinstance(analysis, Mapping):
        issues.append(ValidationIssue(f"{path}.analysis", "must be a JSON object", "type"))
        return None
    _reject_unknown_fields(analysis, set(_ANALYSIS_FIELDS), f"{path}.analysis", issues)
    result: dict[str, str] = {}
    for field in _ANALYSIS_FIELDS:
        field_path = f"{path}.analysis.{field}"
        if field not in analysis:
            issues.append(ValidationIssue(field_path, "is required", "required"))
            continue
        item = analysis.get(field)
        if field.endswith("_sha256"):
            result[field] = _required_sha(item, field_path, issues)
        elif field == "algorithm_id":
            if not isinstance(item, str) or not _SAFE_ID.fullmatch(item):
                issues.append(ValidationIssue(field_path, "invalid algorithm id", "id"))
            else:
                result[field] = item
        elif not isinstance(item, str) or not _SAFE_VERSION.fullmatch(item):
            issues.append(ValidationIssue(field_path, "invalid algorithm version", "version"))
        else:
            result[field] = item
    return dict(sorted(result.items()))


def _normalize_binding_status(
    value: Mapping[str, Any], path: str, stored: bool, issues: list[ValidationIssue]
) -> str | None:
    if not stored:
        return None
    status = value.get("binding_status")
    if "binding_status" not in value:
        issues.append(ValidationIssue(f"{path}.binding_status", "is required", "required"))
        return None
    if status not in {"current", "stale"}:
        issues.append(
            ValidationIssue(
                f"{path}.binding_status",
                "must be current or stale",
                "enum",
            )
        )
        return None
    return status
