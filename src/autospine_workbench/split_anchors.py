"""Validation primitives for reviewer-authored split anchors.

Anchors are provenance, not materialized coordinates.  Joint anchors retain a
stable joint id; manual proxies retain both a stable proxy id and the reviewer
explanation for using a visible landmark in place of hidden anatomy.
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping

from .contract_types import MAX_LABEL_LENGTH, MAX_REASON_LENGTH, ValidationIssue


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SIDES = ("left", "right")


def is_safe_id(value: Any) -> bool:
    """Return whether *value* is a stable contract identifier."""

    return isinstance(value, str) and _SAFE_ID.fullmatch(value) is not None


def anatomical_side(value: str) -> str | None:
    """Return a recognized anatomical suffix, if the id has one."""

    return next((side for side in _SIDES if value.endswith(f".{side}")), None)


def anchor_identity(anchor: Mapping[str, Any]) -> tuple[str, str]:
    """Return the stable identity used to reject duplicate guide anchors."""

    if anchor["kind"] == "joint":
        return "joint", str(anchor["joint_id"])
    return "manual_proxy", str(anchor["proxy_id"])


def authored_anchor_fingerprint(anchor: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return statically comparable authored location/provenance.

    Manual proxy coordinates are intentional authored landmarks.  Comparing
    their coordinates catches a repeated point even if it was accidentally
    assigned two proxy ids.  Joint coordinates are resolved later, so their
    stable joint ids are the only honest static comparison.
    """

    if anchor["kind"] == "joint":
        return "joint", str(anchor["joint_id"])
    xy = anchor["xy"]
    return "manual_proxy_xy", float(xy[0]), float(xy[1])


def normalize_split_anchor(
    value: Any,
    *,
    side: str,
    path: str,
    joint_ids: set[str],
    canvas_width: int,
    canvas_height: int,
    issues: list[ValidationIssue],
) -> dict[str, Any] | None:
    """Validate and canonicalize one joint or manual-proxy anchor."""

    before = len(issues)
    anchor = _mapping(value, path, issues)
    kind = anchor.get("kind")
    if kind == "joint":
        _unknown_fields(anchor, {"kind", "joint_id"}, path, issues)
        joint_id = anchor.get("joint_id")
        _validate_joint_reference(
            joint_id,
            path=f"{path}.joint_id",
            side=side,
            joint_ids=joint_ids,
            issues=issues,
        )
        return None if len(issues) != before else {"kind": "joint", "joint_id": joint_id}

    if kind == "manual_proxy":
        required = {"kind", "proxy_id", "xy", "label", "reason"}
        _unknown_fields(anchor, required | {"proxy_for_joint_id"}, path, issues)
        for field in sorted(required - set(anchor)):
            issues.append(ValidationIssue(f"{path}.{field}", "is required", "required"))

        proxy_id = anchor.get("proxy_id")
        if not is_safe_id(proxy_id):
            issues.append(
                ValidationIssue(f"{path}.proxy_id", "must be a safe stable id", "format")
            )
        elif anatomical_side(proxy_id) != side:
            issues.append(
                ValidationIssue(
                    f"{path}.proxy_id",
                    f"must end in .{side} for this split part",
                    "side_mismatch",
                )
            )

        xy = _point(anchor.get("xy"), f"{path}.xy", canvas_width, canvas_height, issues)
        label = _nonblank_text(
            anchor.get("label"), f"{path}.label", MAX_LABEL_LENGTH, issues
        )
        reason = _nonblank_text(
            anchor.get("reason"), f"{path}.reason", MAX_REASON_LENGTH, issues
        )
        proxy_for = anchor.get("proxy_for_joint_id")
        if "proxy_for_joint_id" in anchor:
            _validate_joint_reference(
                proxy_for,
                path=f"{path}.proxy_for_joint_id",
                side=side,
                joint_ids=joint_ids,
                issues=issues,
            )
        if len(issues) != before:
            return None
        normalized = {
            "kind": "manual_proxy",
            "proxy_id": proxy_id,
            "xy": xy,
            "label": label,
            "reason": reason,
        }
        if "proxy_for_joint_id" in anchor:
            normalized["proxy_for_joint_id"] = proxy_for
        return normalized

    _unknown_fields(anchor, {"kind"}, path, issues)
    issues.append(ValidationIssue(f"{path}.kind", "must be joint or manual_proxy", "enum"))
    return None


def _validate_joint_reference(
    value: Any,
    *,
    path: str,
    side: str,
    joint_ids: set[str],
    issues: list[ValidationIssue],
) -> None:
    if not is_safe_id(value):
        issues.append(ValidationIssue(path, "invalid joint id", "format"))
    elif value not in joint_ids:
        issues.append(ValidationIssue(path, "unknown joint id", "unknown_id"))
    elif anatomical_side(value) not in {None, side}:
        issues.append(
            ValidationIssue(
                path,
                f"must not reference the opposite anatomical side ({side})",
                "side_mismatch",
            )
        )


def _point(
    value: Any,
    path: str,
    width: int,
    height: int,
    issues: list[ValidationIssue],
) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 2 or not all(_finite(v) for v in value):
        issues.append(ValidationIssue(path, "must be two finite numbers", "shape"))
        return None
    point = [float(value[0]), float(value[1])]
    if not 0 <= point[0] <= width or not 0 <= point[1] <= height:
        issues.append(ValidationIssue(path, "must lie inside the canvas", "bounds"))
        return None
    return point


def _nonblank_text(
    value: Any, path: str, limit: int, issues: list[ValidationIssue]
) -> str:
    if not isinstance(value, str):
        issues.append(ValidationIssue(path, "must be a string", "type"))
        return ""
    if not value.strip():
        issues.append(ValidationIssue(path, "must not be blank", "length"))
    elif len(value) > limit:
        issues.append(ValidationIssue(path, f"must be at most {limit} characters", "length"))
    return value


def _mapping(value: Any, path: str, issues: list[ValidationIssue]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        issues.append(ValidationIssue(path, "must be a JSON object", "type"))
        return {}
    return value


def _unknown_fields(
    value: Mapping[Any, Any], allowed: set[str], path: str, issues: list[ValidationIssue]
) -> None:
    for field in value:
        if not isinstance(field, str):
            issues.append(ValidationIssue(path, "all keys must be strings", "type"))
        elif field not in allowed:
            issues.append(ValidationIssue(f"{path}.{field}", "unknown field", "unknown_field"))


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )
