"""Strict normalization for candidate-backed joint review decisions."""

from __future__ import annotations

import math
import re
from typing import Any, Mapping

from .contracts import MAX_REASON_LENGTH, ValidationIssue


_ACTIONS = frozenset({"accept", "adjust", "reject", "unobservable"})
_CANDIDATE_ACTIONS = frozenset({"accept", "adjust", "reject"})
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ANALYSIS_FIELDS = (
    "provider",
    "provider_version",
    "input_sha256",
    "config_sha256",
    "run_sha256",
)


def normalize_joint_decisions(
    value: Any,
    *,
    joint_ids: set[str],
    canvas_width: int,
    canvas_height: int,
    issues: list[ValidationIssue],
    stored: bool = False,
) -> dict[str, dict[str, Any]]:
    """Normalize client or persisted candidate decisions without raising.

    Client documents (``stored=False``) cannot provide binder-derived
    ``analysis`` metadata or an accepted candidate's ``final_xy``. Persisted
    documents require both, allowing their provenance to be revalidated when
    loaded. All errors are appended to ``issues`` so the surrounding override
    validator can return one coherent response.
    """

    path = "$.joint_decisions"
    if not isinstance(value, Mapping):
        issues.append(ValidationIssue(path, "must be a JSON object", "type"))
        return {}

    normalized: dict[str, dict[str, Any]] = {}
    sortable: list[tuple[str, Any]] = []
    for key, raw in value.items():
        if not isinstance(key, str):
            issues.append(ValidationIssue(path, "all keys must be strings", "type"))
            continue
        sortable.append((key, raw))

    for joint_id, raw in sorted(sortable, key=lambda pair: pair[0]):
        item_path = f"{path}.{joint_id}"
        before = len(issues)
        if not _SAFE_ID.fullmatch(joint_id) or joint_id not in joint_ids:
            issues.append(ValidationIssue(item_path, "unknown joint id", "unknown_id"))
            continue
        if not isinstance(raw, Mapping):
            issues.append(ValidationIssue(item_path, "must be a JSON object", "type"))
            continue

        allowed = {
            "action",
            "candidate_artifact_sha256",
            "candidate_id",
            "final_xy",
            "reason",
        }
        if stored:
            allowed.add("analysis")
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
            raw.get("candidate_artifact_sha256"),
            f"{item_path}.candidate_artifact_sha256",
            issues,
        )
        candidate_id = _normalize_candidate_id(raw, action, item_path, issues)
        final_xy = _normalize_final_xy(
            raw,
            action,
            item_path,
            canvas_width,
            canvas_height,
            stored,
            issues,
        )
        reason = _normalize_reason(raw, action, item_path, issues)
        analysis = _normalize_analysis(raw, item_path, stored, issues)

        if len(issues) != before:
            continue
        item: dict[str, Any] = {
            "action": action,
            "candidate_artifact_sha256": artifact_sha,
        }
        if candidate_id is not None:
            item["candidate_id"] = candidate_id
        if final_xy is not None:
            item["final_xy"] = final_xy
        if reason is not None:
            item["reason"] = reason
        if analysis is not None:
            item["analysis"] = analysis
        normalized[joint_id] = dict(sorted(item.items()))
    return dict(sorted(normalized.items()))


def _reject_unknown_fields(
    value: Mapping[Any, Any], allowed: set[str], path: str, issues: list[ValidationIssue]
) -> None:
    for key in value:
        if not isinstance(key, str):
            issues.append(ValidationIssue(path, "all keys must be strings", "type"))
        elif key not in allowed:
            code = "derived_field" if key == "analysis" else "unknown_field"
            issues.append(ValidationIssue(f"{path}.{key}", "field is not allowed", code))


def _required_sha(value: Any, path: str, issues: list[ValidationIssue]) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        issues.append(ValidationIssue(path, "must be a lowercase SHA-256", "hash"))
        return ""
    return value


def _normalize_candidate_id(
    value: Mapping[str, Any], action: Any, path: str, issues: list[ValidationIssue]
) -> str | None:
    present = "candidate_id" in value
    candidate_id = value.get("candidate_id")
    if action in _CANDIDATE_ACTIONS:
        if not present:
            issues.append(ValidationIssue(f"{path}.candidate_id", "is required", "required"))
            return None
        if not isinstance(candidate_id, str) or not _SAFE_ID.fullmatch(candidate_id):
            issues.append(ValidationIssue(f"{path}.candidate_id", "invalid candidate id", "id"))
            return None
        return candidate_id
    if action == "unobservable" and present:
        issues.append(
            ValidationIssue(f"{path}.candidate_id", "is forbidden for unobservable", "forbidden")
        )
    return None


def _normalize_final_xy(
    value: Mapping[str, Any],
    action: Any,
    path: str,
    width: int,
    height: int,
    stored: bool,
    issues: list[ValidationIssue],
) -> list[float] | None:
    present = "final_xy" in value
    required = action == "adjust" or (stored and action == "accept")
    forbidden = action in {"reject", "unobservable"} or (not stored and action == "accept")
    if required and not present:
        issues.append(ValidationIssue(f"{path}.final_xy", "is required", "required"))
        return None
    if forbidden and present:
        label = "binder-derived for accept" if action == "accept" else f"forbidden for {action}"
        issues.append(ValidationIssue(f"{path}.final_xy", label, "derived_field" if action == "accept" else "forbidden"))
        return None
    if not present:
        return None
    point = value.get("final_xy")
    if not isinstance(point, list) or len(point) != 2 or not all(_finite(v) for v in point):
        issues.append(ValidationIssue(f"{path}.final_xy", "must be two finite numbers", "shape"))
        return None
    x, y = float(point[0]), float(point[1])
    if not 0 <= x <= width or not 0 <= y <= height:
        issues.append(ValidationIssue(f"{path}.final_xy", "must lie inside the canvas", "bounds"))
        return None
    return [x, y]


def _normalize_reason(
    value: Mapping[str, Any], action: Any, path: str, issues: list[ValidationIssue]
) -> str | None:
    present = "reason" in value
    reason = value.get("reason")
    if action in {"adjust", "reject", "unobservable"} and not present:
        issues.append(ValidationIssue(f"{path}.reason", "is required", "required"))
        return None
    if not present:
        return None
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
        item = analysis.get(field)
        if field in {"input_sha256", "config_sha256", "run_sha256"}:
            result[field] = _required_sha(item, field_path, issues)
        elif field == "provider":
            if not isinstance(item, str) or not _SAFE_ID.fullmatch(item):
                issues.append(ValidationIssue(field_path, "invalid provider id", "id"))
            else:
                result[field] = item
        elif not isinstance(item, str) or not item or len(item) > 64:
            issues.append(ValidationIssue(field_path, "must contain 1 to 64 characters", "length"))
        else:
            result[field] = item
    return dict(sorted(result.items()))


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
