"""Strict reviewer-authored bilateral split specifications.

The contract records authoring intent only.  It deliberately does not bind a
split artifact or promise that materialized child rasters exist.
"""

from __future__ import annotations

from typing import Any, Mapping

from .contract_types import OVERRIDE_SCHEMA_VERSION_V1, OVERRIDE_SCHEMA_VERSION_V2
from .contract_types import ValidationIssue
from .split_anchors import (
    anatomical_side,
    anchor_identity,
    authored_anchor_fingerprint,
    is_safe_id,
    normalize_split_anchor,
)

_SIDES = ("left", "right")


def infer_humanoid_bone_ids(joint_ids: set[str]) -> set[str]:
    """Return bone ids supported by the workbench humanoid joint template."""

    result: set[str] = set()
    center_specs = (
        ("root-pelvis", "root", "pelvis"),
        ("pelvis-spine", "pelvis", "spine"),
        ("spine-chest", "spine", "chest"),
        ("chest-neck", "chest", "neck"),
        ("neck-head", "neck", "head"),
    )
    for bone_id, start, end in center_specs:
        if {start, end}.issubset(joint_ids):
            result.add(bone_id)
    for side in _SIDES:
        side_specs = (
            (f"chest-shoulder.{side}", "chest", f"shoulder.{side}"),
            (f"upper-arm.{side}", f"shoulder.{side}", f"elbow.{side}"),
            (f"forearm.{side}", f"elbow.{side}", f"wrist.{side}"),
            (f"pelvis-hip.{side}", "pelvis", f"hip.{side}"),
            (f"thigh.{side}", f"hip.{side}", f"knee.{side}"),
            (f"calf.{side}", f"knee.{side}", f"ankle.{side}"),
        )
        for bone_id, start, end in side_specs:
            if {start, end}.issubset(joint_ids):
                result.add(bone_id)
    return result


def normalize_split_spec(
    value: Any,
    *,
    path: str,
    joint_ids: set[str],
    bone_ids: set[str],
    canvas_width: int,
    canvas_height: int,
    issues: list[ValidationIssue],
) -> dict[str, Any] | None:
    """Validate one left/right authoring spec, appending all field issues."""

    before = len(issues)
    spec = _mapping(value, path, issues)
    _unknown_fields(spec, {"parts"}, path, issues)
    parts = _mapping(spec.get("parts"), f"{path}.parts", issues)
    _unknown_fields(parts, set(_SIDES), f"{path}.parts", issues)
    normalized_parts: dict[str, Any] = {}
    for side in _SIDES:
        part_path = f"{path}.parts.{side}"
        if side not in parts:
            issues.append(ValidationIssue(part_path, "is required", "required"))
            continue
        normalized = _normalize_part(
            parts[side],
            side=side,
            path=part_path,
            joint_ids=joint_ids,
            bone_ids=bone_ids,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            issues=issues,
        )
        if normalized is not None:
            normalized_parts[side] = normalized
    if set(normalized_parts) == set(_SIDES):
        _validate_distinct_guides(normalized_parts, path, issues)
    if len(issues) != before:
        return None
    return {"parts": normalized_parts}


def normalize_layer_split_authoring(
    override: Mapping[str, Any],
    normalized: dict[str, Any],
    *,
    path: str,
    schema_version: Any,
    joint_ids: set[str],
    bone_ids: set[str],
    canvas_width: int,
    canvas_height: int,
    issues: list[ValidationIssue],
) -> None:
    """Apply v3-only split rules to one layer override in place."""

    if "split_spec" not in override:
        return
    if schema_version in {OVERRIDE_SCHEMA_VERSION_V1, OVERRIDE_SCHEMA_VERSION_V2}:
        issues.append(
            ValidationIssue(f"{path}.split_spec", "requires override/v3", "version")
        )
    if override.get("side") != "bilateral":
        issues.append(
            ValidationIssue(
                f"{path}.side",
                "must be bilateral when split_spec is present",
                "conflict",
            )
        )
    disposition = override.get("disposition")
    if disposition not in {"split", "split_left_right"}:
        issues.append(
            ValidationIssue(
                f"{path}.disposition",
                "must be split_left_right when split_spec is present",
                "conflict",
            )
        )
    elif disposition == "split":
        normalized["disposition"] = "split_left_right"
    for field in ("pivot_xy", "candidate_bone"):
        if field in override:
            issues.append(
                ValidationIssue(
                    f"{path}.{field}",
                    "is forbidden when split_spec is present",
                    "conflict",
                )
            )
    split_spec = normalize_split_spec(
        override["split_spec"],
        path=f"{path}.split_spec",
        joint_ids=joint_ids,
        bone_ids=bone_ids,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        issues=issues,
    )
    if split_spec is not None:
        normalized["split_spec"] = split_spec


def _normalize_part(
    value: Any,
    *,
    side: str,
    path: str,
    joint_ids: set[str],
    bone_ids: set[str],
    canvas_width: int,
    canvas_height: int,
    issues: list[ValidationIssue],
) -> dict[str, Any] | None:
    before = len(issues)
    part = _mapping(value, path, issues)
    required = {"guide", "pivot", "candidate_bone"}
    _unknown_fields(part, required, path, issues)
    for field in sorted(required - set(part)):
        issues.append(ValidationIssue(f"{path}.{field}", "is required", "required"))

    guide = part.get("guide")
    normalized_guide: list[dict[str, Any]] = []
    if not isinstance(guide, list) or not 2 <= len(guide) <= 8:
        issues.append(
            ValidationIssue(f"{path}.guide", "must contain 2 to 8 anchors", "length")
        )
    else:
        for index, anchor in enumerate(guide):
            normalized = normalize_split_anchor(
                anchor,
                side=side,
                path=f"{path}.guide[{index}]",
                joint_ids=joint_ids,
                canvas_width=canvas_width,
                canvas_height=canvas_height,
                issues=issues,
            )
            if normalized is not None:
                normalized_guide.append(normalized)
        if len(normalized_guide) == len(guide):
            _validate_guide(normalized_guide, f"{path}.guide", issues)

    pivot = normalize_split_anchor(
        part.get("pivot"),
        side=side,
        path=f"{path}.pivot",
        joint_ids=joint_ids,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        issues=issues,
    )
    candidate_bone = part.get("candidate_bone")
    if not is_safe_id(candidate_bone):
        issues.append(
            ValidationIssue(f"{path}.candidate_bone", "must be a safe bone id", "format")
        )
    elif candidate_bone not in bone_ids:
        issues.append(
            ValidationIssue(f"{path}.candidate_bone", "unknown bone id", "unknown_id")
        )
    elif anatomical_side(candidate_bone) != side:
        issues.append(
            ValidationIssue(
                f"{path}.candidate_bone",
                f"must end in .{side}; center and opposite-side bones are invalid",
                "side_mismatch",
            )
        )
    if len(issues) != before:
        return None
    return {
        "guide": normalized_guide,
        "pivot": pivot,
        "candidate_bone": candidate_bone,
    }


def _validate_guide(
    guide: list[dict[str, Any]], path: str, issues: list[ValidationIssue]
) -> None:
    seen: dict[tuple[str, str], int] = {}
    fingerprints = [authored_anchor_fingerprint(anchor) for anchor in guide]
    for index, anchor in enumerate(guide):
        identity = anchor_identity(anchor)
        if identity in seen:
            issues.append(
                ValidationIssue(
                    f"{path}[{index}]",
                    f"duplicates anchor identity from index {seen[identity]}",
                    "duplicate_id",
                )
            )
        else:
            seen[identity] = index
        if index and fingerprints[index - 1] == fingerprints[index]:
            issues.append(
                ValidationIssue(
                    f"{path}[{index}]",
                    "repeats the preceding authored anchor",
                    "degenerate",
                )
            )


def _validate_distinct_guides(
    parts: Mapping[str, Mapping[str, Any]], path: str, issues: list[ValidationIssue]
) -> None:
    left = [authored_anchor_fingerprint(item) for item in parts["left"]["guide"]]
    right = [authored_anchor_fingerprint(item) for item in parts["right"]["guide"]]
    if left == right:
        issues.append(
            ValidationIssue(
                f"{path}.parts.right.guide",
                "must not duplicate the authored left guide",
                "degenerate",
            )
        )
    elif left == list(reversed(right)):
        issues.append(
            ValidationIssue(
                f"{path}.parts.right.guide",
                "must not reverse the authored left guide",
                "degenerate",
            )
        )


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
