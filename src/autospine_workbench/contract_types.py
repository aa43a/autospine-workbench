"""Shared version tokens and validation result types for workbench contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
