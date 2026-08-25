"""Primitive value checks shared by alpha evidence semantic sections."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Mapping

from .resolved_project import canonical_sha256


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ROLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")


@dataclass(frozen=True, slots=True)
class AlphaEvidenceValidationIssue:
    path: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "code": self.code, "message": self.message}


class EvidenceFieldChecker:
    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.issues: list[AlphaEvidenceValidationIssue] = []

    def add(self, path: str, code: str, message: str) -> None:
        self.issues.append(AlphaEvidenceValidationIssue(path, code, message))

    def obj(
        self,
        value: Any,
        path: str,
        allowed: set[str],
        required: set[str] | None = None,
    ) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            self.add(path, "type", "must be an object")
            return {}
        for field in value:
            if field not in allowed:
                self.add(f"{path}.{field}", "unknown_field", "unknown field")
        for field in sorted(allowed if required is None else required):
            if field not in value:
                self.add(f"{path}.{field}", "required", "field is required")
        return value

    def array(self, value: Any, path: str) -> list[Any]:
        if not isinstance(value, list):
            self.add(path, "type", "must be an array")
            return []
        return value

    def point(
        self, value: Any, path: str, nullable: bool = False
    ) -> tuple[float, float] | None:
        if nullable and value is None:
            return None
        if not isinstance(value, list) or len(value) != 2 or not all(finite(v) for v in value):
            self.add(path, "coordinate", "must contain two finite numbers")
            return None
        point = (float(value[0]), float(value[1]))
        if not 0 <= point[0] <= self.width or not 0 <= point[1] <= self.height:
            self.add(path, "bounds", "point lies outside the canvas")
        return point

    def points(
        self, value: Any, path: str, count: int | None = None
    ) -> list[tuple[float, float]]:
        items = self.array(value, path)
        if count is not None and len(items) != count:
            self.add(path, "shape", f"must contain {count} points")
        return [
            point
            for index, item in enumerate(items)
            if (point := self.point(item, f"{path}[{index}]")) is not None
        ]

    def number(self, value: Any, path: str, nullable: bool = False) -> float | None:
        if nullable and value is None:
            return None
        if not finite(value) or value < 0:
            self.add(path, "bounds", "must be a finite non-negative number")
            return None
        return float(value)

    def vector(
        self, value: Any, path: str, count: int, maximum: float | None
    ) -> list[float]:
        if not isinstance(value, list) or len(value) != count or not all(finite(v) for v in value):
            self.add(path, "shape", f"must contain {count} finite numbers")
            return []
        result = [float(item) for item in value]
        if any(item < 0 or (maximum is not None and item > maximum) for item in result):
            self.add(path, "bounds", "vector values are outside the supported range")
        return result

    def bbox(self, value: Any, path: str) -> None:
        if (
            not isinstance(value, list)
            or len(value) != 4
            or not all(integer(v) for v in value)
            or value[2] < 1
            or value[3] < 1
            or value[0] < 0
            or value[1] < 0
            or value[0] + value[2] > self.width
            or value[1] + value[3] > self.height
        ):
            self.add(path, "bounds", "bbox must be a positive in-canvas integer rectangle")

    def flags(self, value: Any, path: str) -> None:
        items = self.ids(value, path)
        if items != sorted(items):
            self.add(path, "order", "flags must be sorted")

    def ids(self, value: Any, path: str) -> list[str]:
        items = self.array(value, path)
        if any(not isinstance(item, str) or not self.valid_id(item) for item in items):
            self.add(path, "id", "must contain valid ids")
        if len(items) != len(set(item for item in items if isinstance(item, str))):
            self.add(path, "duplicate", "ids must be unique")
        return [item for item in items if isinstance(item, str)]

    @staticmethod
    def valid_id(value: Any) -> bool:
        return isinstance(value, str) and bool(_ID.fullmatch(value))

    @staticmethod
    def valid_sha(value: Any) -> bool:
        return isinstance(value, str) and bool(_SHA.fullmatch(value))


def validate_anchors(
    value: Any,
    joints: list[Any],
    path: str,
    status: Any,
    check: EvidenceFieldChecker,
) -> None:
    names = ("proximal", "hinge", "distal")
    anchors = check.obj(value, f"{path}.anchors", set(names))
    for index, name in enumerate(names):
        anchor_path = f"{path}.anchors.{name}"
        anchor = check.obj(
            anchors.get(name),
            anchor_path,
            {"joint_id", "input_xy", "projected_xy", "residual_px"},
        )
        if index >= len(joints) or anchor.get("joint_id") != joints[index]:
            check.add(f"{anchor_path}.joint_id", "joint", "anchor does not match joint order")
        check.point(anchor.get("input_xy"), f"{anchor_path}.input_xy")
        check.point(
            anchor.get("projected_xy"),
            f"{anchor_path}.projected_xy",
            nullable=status == "unavailable",
        )
        check.number(
            anchor.get("residual_px"),
            f"{anchor_path}.residual_px",
            nullable=status == "unavailable",
        )


def validate_budgets(value: Any, path: str, check: EvidenceFieldChecker) -> None:
    budgets = check.obj(
        value,
        f"{path}.budgets",
        {"max_raster_pixels", "max_search_nodes", "raster_pixels", "search_nodes"},
    )
    for field in ("max_raster_pixels", "max_search_nodes"):
        if not integer(budgets.get(field)) or budgets[field] < 1:
            check.add(f"{path}.budgets.{field}", "budget", "budget must be positive")
    for field in ("raster_pixels", "search_nodes"):
        if not integer(budgets.get(field)) or budgets[field] < 0:
            check.add(f"{path}.budgets.{field}", "budget", "usage must be non-negative")


def validate_qa(value: Any, check: EvidenceFieldChecker) -> None:
    qa = check.obj(value, "$.qa", {"status", "flags"})
    if qa.get("status") not in {"passed", "manual_required", "rejected"}:
        check.add("$.qa.status", "enum", "unsupported QA status")
    check.flags(qa.get("flags"), "$.qa.flags")


def valid_role(value: Any) -> bool:
    return isinstance(value, str) and bool(_ROLE.fullmatch(value))


def safe_canonical_sha256(value: Any) -> str | None:
    """Return a canonical digest only for strict JSON-compatible values."""

    try:
        return canonical_sha256(value)
    except (TypeError, ValueError, OverflowError):
        return None


def require_sorted_ids(
    items: list[Any], field: str, path: str, check: EvidenceFieldChecker
) -> None:
    values = [item.get(field) for item in items if isinstance(item, Mapping)]
    if values != sorted(values, key=lambda item: str(item)):
        check.add(path, "order", f"items must be sorted by {field}")


def integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
