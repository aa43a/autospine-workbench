"""Versioned workbench contracts and strict override validation.

The public API intentionally uses plain dictionaries so it remains usable from
the Python standard library and serializes without custom encoders.  Every
top-level contract carries both a stable ``schema_version`` string and a small
``contract`` descriptor for human-facing clients.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping


PROJECT_SCHEMA_VERSION = "autospine-workbench.project/v1"
LAYER_SCHEMA_VERSION = "autospine-workbench.layer/v1"
SKELETON_SCHEMA_VERSION = "autospine-workbench.skeleton/v1"
OVERRIDE_SCHEMA_VERSION_V1 = "autospine-workbench.override/v1"
OVERRIDE_SCHEMA_VERSION = "autospine-workbench.override/v2"
PROJECT_LIST_SCHEMA_VERSION = "autospine-workbench.project-list/v1"
VALIDATION_SCHEMA_VERSION = "autospine-workbench.validation/v1"

MAX_NOTES_LENGTH = 10_000
MAX_REASON_LENGTH = 1_000
MAX_ROLE_LENGTH = 96

SIDE_VALUES = frozenset({"left", "right", "center", "bilateral", "unknown"})

# ``disposition`` is a review decision, not a renderer mode.  Aliases retained
# here cover the vocabulary used by the early workbench prototypes.
DISPOSITION_VALUES = frozenset(
    {
        "auto",
        "keep",
        "exclude",
        "ignore",
        "split",
        "split_left_right",
        "merge",
        "review",
    }
)

_SAFE_ROLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


def contract_descriptor(kind: str, version: int = 1) -> dict[str, Any]:
    return {"name": f"autospine-workbench.{kind}", "version": version}


@dataclass(frozen=True)
class ValidationIssue:
    """A machine-readable field validation error."""

    path: str
    message: str
    code: str = "invalid"

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message, "code": self.code}


class ContractValidationError(ValueError):
    """Raised when an API document fails contract validation."""

    def __init__(self, issues: list[ValidationIssue] | ValidationIssue):
        if isinstance(issues, ValidationIssue):
            issues = [issues]
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{item.path}: {item.message}" for item in self.issues))

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": "validation_error",
            "message": "Request body does not satisfy the override contract.",
            "issues": [item.as_dict() for item in self.issues],
        }


def empty_overrides(project_id: str) -> dict[str, Any]:
    """Return the canonical revision-zero override document."""

    return {
        "schema_version": OVERRIDE_SCHEMA_VERSION,
        "contract": contract_descriptor("override", 2),
        "project_id": project_id,
        "revision": 0,
        "joint_overrides": {},
        "joint_decisions": {},
        "layer_overrides": {},
        "notes": "",
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _expect_mapping(value: Any, path: str, issues: list[ValidationIssue]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        issues.append(ValidationIssue(path, "must be a JSON object", "type"))
        return {}
    return value


def _unknown_fields(
    value: Mapping[str, Any], allowed: set[str], path: str, issues: list[ValidationIssue]
) -> None:
    for key in value:
        if not isinstance(key, str):
            issues.append(ValidationIssue(path, "all keys must be strings", "type"))
        elif key not in allowed:
            issues.append(ValidationIssue(f"{path}.{key}", "unknown field", "unknown_field"))


def _validate_notes(value: Any, path: str, issues: list[ValidationIssue], limit: int) -> str:
    if not isinstance(value, str):
        issues.append(ValidationIssue(path, "must be a string", "type"))
        return ""
    if len(value) > limit:
        issues.append(ValidationIssue(path, f"must be at most {limit} characters", "length"))
        return value[:limit]
    return value


def _normalize_pivot(
    value: Any,
    path: str,
    canvas_width: int,
    canvas_height: int,
    issues: list[ValidationIssue],
) -> list[float] | None:
    if isinstance(value, Mapping):
        _unknown_fields(value, {"x", "y"}, path, issues)
        value = [value.get("x"), value.get("y")]
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        issues.append(ValidationIssue(path, "must be [x, y]", "shape"))
        return None
    x, y = value
    if not _is_number(x) or not _is_number(y):
        issues.append(ValidationIssue(path, "coordinates must be finite numbers", "type"))
        return None
    if not (0 <= float(x) <= canvas_width) or not (0 <= float(y) <= canvas_height):
        issues.append(ValidationIssue(path, "coordinates must lie inside the canvas", "bounds"))
        return None
    return [float(x), float(y)]


def normalize_override_request(
    payload: Any,
    *,
    project_id: str,
    current_revision: int,
    joint_ids: set[str],
    layer_ids: set[str],
    canvas_width: int,
    canvas_height: int,
    stored: bool = False,
) -> tuple[int, dict[str, Any]]:
    """Validate and normalize a PUT override request.

    The canonical request is ``{base_revision, joint_overrides,
    layer_overrides, notes}``.  Early UI aliases ``revision``, ``joints``,
    ``layers`` and ``workflow.notes`` are accepted and normalized.  The
    returned document does not increment the revision; the store does that
    only after the compare-and-swap check succeeds.
    """

    issues: list[ValidationIssue] = []
    root = _expect_mapping(payload, "$", issues)
    allowed_root = {
        "schema_version",
        "base_revision",
        "revision",
        "joint_overrides",
        "joint_decisions",
        "layer_overrides",
        "notes",
        "joints",
        "layers",
        "workflow",
    }
    _unknown_fields(root, allowed_root, "$", issues)

    schema_version = root.get("schema_version")
    supported_versions = {OVERRIDE_SCHEMA_VERSION_V1, OVERRIDE_SCHEMA_VERSION}
    if schema_version is not None and schema_version not in supported_versions:
        issues.append(
            ValidationIssue(
                "$.schema_version",
                f"must be one of {sorted(supported_versions)!r}",
                "version",
            )
        )

    if "base_revision" in root and "revision" in root:
        if root.get("base_revision") != root.get("revision"):
            issues.append(
                ValidationIssue(
                    "$.revision",
                    "must match base_revision when both are supplied",
                    "conflict",
                )
            )
    base_revision = root.get("base_revision", root.get("revision"))
    if not isinstance(base_revision, int) or isinstance(base_revision, bool) or base_revision < 0:
        issues.append(
            ValidationIssue("$.base_revision", "must be a non-negative integer", "type")
        )
        base_revision = -1

    if "joint_overrides" in root and "joints" in root:
        issues.append(
            ValidationIssue("$.joints", "cannot be used with joint_overrides", "ambiguous")
        )
    if "layer_overrides" in root and "layers" in root:
        issues.append(
            ValidationIssue("$.layers", "cannot be used with layer_overrides", "ambiguous")
        )

    raw_joint_overrides = root.get("joint_overrides", root.get("joints", {}))
    joint_overrides = _expect_mapping(raw_joint_overrides, "$.joint_overrides", issues)
    normalized_joints: dict[str, Any] = {}
    joint_fields = {"x", "y", "confidence", "reason"}
    for joint_id, raw_override in joint_overrides.items():
        path = f"$.joint_overrides.{joint_id}"
        if joint_id not in joint_ids:
            issues.append(ValidationIssue(path, "unknown joint id", "unknown_id"))
            continue
        override = _expect_mapping(raw_override, path, issues)
        _unknown_fields(override, joint_fields, path, issues)
        if "x" not in override or "y" not in override:
            issues.append(ValidationIssue(path, "x and y are required", "required"))
            continue
        x, y = override.get("x"), override.get("y")
        if not _is_number(x) or not _is_number(y):
            issues.append(ValidationIssue(path, "x and y must be finite numbers", "type"))
            continue
        if not (0 <= float(x) <= canvas_width) or not (0 <= float(y) <= canvas_height):
            issues.append(ValidationIssue(path, "x and y must lie inside the canvas", "bounds"))
            continue
        item: dict[str, Any] = {"x": float(x), "y": float(y)}
        if "confidence" in override:
            confidence = override["confidence"]
            if not _is_number(confidence) or not (0 <= float(confidence) <= 1):
                issues.append(
                    ValidationIssue(f"{path}.confidence", "must be between 0 and 1", "bounds")
                )
            else:
                item["confidence"] = float(confidence)
        if "reason" in override:
            item["reason"] = _validate_notes(
                override["reason"], f"{path}.reason", issues, MAX_REASON_LENGTH
            )
        normalized_joints[joint_id] = item

    from .decision_contracts import normalize_joint_decisions

    raw_joint_decisions = root.get("joint_decisions", {})
    if schema_version == OVERRIDE_SCHEMA_VERSION_V1 and raw_joint_decisions:
        issues.append(
            ValidationIssue(
                "$.joint_decisions",
                "override/v1 cannot contain candidate-backed decisions",
                "version",
            )
        )
    normalized_decisions = normalize_joint_decisions(
        raw_joint_decisions,
        joint_ids=joint_ids,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        issues=issues,
        stored=stored,
    )
    for joint_id in sorted(set(normalized_joints) & set(normalized_decisions)):
        issues.append(
            ValidationIssue(
                f"$.joint_decisions.{joint_id}",
                "cannot coexist with a manual joint override for the same joint",
                "conflict",
            )
        )

    raw_layer_overrides = root.get("layer_overrides", root.get("layers", {}))
    layer_overrides = _expect_mapping(raw_layer_overrides, "$.layer_overrides", issues)
    normalized_layers: dict[str, Any] = {}
    layer_fields = {"canonical_role", "side", "disposition", "visible", "pivot_xy", "notes"}
    for layer_id, raw_override in layer_overrides.items():
        path = f"$.layer_overrides.{layer_id}"
        if layer_id not in layer_ids:
            issues.append(ValidationIssue(path, "unknown layer id", "unknown_id"))
            continue
        override = _expect_mapping(raw_override, path, issues)
        _unknown_fields(override, layer_fields, path, issues)
        item: dict[str, Any] = {}
        if "canonical_role" in override:
            role = override["canonical_role"]
            if role is None:
                item["canonical_role"] = None
            elif (
                not isinstance(role, str)
                or len(role) > MAX_ROLE_LENGTH
                or not _SAFE_ROLE_RE.fullmatch(role)
            ):
                issues.append(
                    ValidationIssue(
                        f"{path}.canonical_role",
                        "must be null or a short semantic role token",
                        "format",
                    )
                )
            else:
                item["canonical_role"] = role
        if "side" in override:
            side = override["side"]
            if side not in SIDE_VALUES:
                issues.append(
                    ValidationIssue(
                        f"{path}.side",
                        f"must be one of {sorted(SIDE_VALUES)}",
                        "enum",
                    )
                )
            else:
                item["side"] = side
        if "disposition" in override:
            disposition = override["disposition"]
            if disposition not in DISPOSITION_VALUES:
                issues.append(
                    ValidationIssue(
                        f"{path}.disposition",
                        f"must be one of {sorted(DISPOSITION_VALUES)}",
                        "enum",
                    )
                )
            else:
                item["disposition"] = disposition
        if "visible" in override:
            if not isinstance(override["visible"], bool):
                issues.append(ValidationIssue(f"{path}.visible", "must be boolean", "type"))
            else:
                item["visible"] = override["visible"]
        if "pivot_xy" in override:
            pivot = _normalize_pivot(
                override["pivot_xy"],
                f"{path}.pivot_xy",
                canvas_width,
                canvas_height,
                issues,
            )
            if pivot is not None:
                item["pivot_xy"] = pivot
        if "notes" in override:
            item["notes"] = _validate_notes(
                override["notes"], f"{path}.notes", issues, MAX_REASON_LENGTH
            )
        normalized_layers[layer_id] = item

    notes_value = root.get("notes", "")
    if "workflow" in root:
        workflow = root["workflow"]
        if isinstance(workflow, str):
            if "notes" not in root:
                notes_value = workflow
        else:
            workflow_map = _expect_mapping(workflow, "$.workflow", issues)
            _unknown_fields(workflow_map, {"notes"}, "$.workflow", issues)
            if "notes" in workflow_map and "notes" not in root:
                notes_value = workflow_map["notes"]
    notes = _validate_notes(notes_value, "$.notes", issues, MAX_NOTES_LENGTH)

    if issues:
        raise ContractValidationError(issues)

    normalized = {
        "schema_version": OVERRIDE_SCHEMA_VERSION,
        "contract": contract_descriptor("override", 2),
        "project_id": project_id,
        "revision": current_revision,
        "joint_overrides": normalized_joints,
        "joint_decisions": normalized_decisions,
        "layer_overrides": normalized_layers,
        "notes": notes,
    }
    return int(base_revision), normalized
