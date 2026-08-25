"""Resolve reviewer-authored split anchors against one pinned setup snapshot.

The authored ``split_spec`` keeps stable joint/proxy references.  This module
turns those references into immutable coordinates for preview generation while
retaining their provenance.  It never treats the resolution as an accepted
split decision.
"""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any, Mapping

from .contract_types import ValidationIssue
from .resolved_project import canonical_sha256
from .split_specs import normalize_split_spec


_USABLE_JOINT_STATES = frozenset({"candidate_accepted", "manual_adjusted"})
_SIDES = ("left", "right")


class SplitSpecResolutionError(ValueError):
    """Raised when authoring intent cannot be resolved without guessing."""


def resolve_layer_split_authoring(
    layer: Mapping[str, Any],
    *,
    joints: Mapping[str, Mapping[str, Any]],
    bone_ids: set[str],
    canvas_width: int,
    canvas_height: int,
) -> dict[str, Any]:
    """Resolve v3 authoring or produce the explicit P2a heuristic candidate.

    The compatibility path remains a candidate only.  It does not gain a
    ``split_spec_sha256`` and therefore cannot later masquerade as reviewer
    authoring or satisfy a split acceptance binding.
    """

    layer_id = str(layer.get("id") or "")
    if "split_spec" in layer:
        return resolve_split_spec(
            layer_id,
            layer["split_spec"],
            joints=joints,
            bone_ids=bone_ids,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        )

    guide_names, pivot_name = _heuristic_guide_spec(
        str(layer.get("canonical_role") or "")
    )
    parts: dict[str, dict[str, Any]] = {}
    for side in _SIDES:
        parts[side] = {
            "guide_anchors": [
                _resolve_joint(layer_id, side, f"{name}.{side}", joints, (canvas_width, canvas_height))
                for name in guide_names
            ],
            "pivot_xy": _joint_point(
                layer_id,
                f"{pivot_name}.{side}",
                _require_joint(layer_id, f"{pivot_name}.{side}", joints),
                (canvas_width, canvas_height),
            ),
        }
    _validate_effective_guides(layer_id, parts)
    return {"parts": parts}


def resolve_split_spec(
    layer_id: str,
    value: Any,
    *,
    joints: Mapping[str, Mapping[str, Any]],
    bone_ids: set[str],
    canvas_width: int,
    canvas_height: int,
) -> dict[str, Any]:
    """Resolve a normalized bilateral spec against reviewed setup joints.

    The returned payload is deterministic and JSON-safe.  ``split_spec_sha256``
    identifies the canonical authoring intent, while every effective anchor
    pins the exact coordinate and review state used to render the preview.
    """

    _validate_context(layer_id, joints, bone_ids, canvas_width, canvas_height)
    issues: list[ValidationIssue] = []
    normalized = normalize_split_spec(
        value,
        path=f"$.layers.{layer_id}.split_spec",
        joint_ids=set(joints),
        bone_ids=bone_ids,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        issues=issues,
    )
    if normalized is None or issues:
        raise SplitSpecResolutionError(_issue_message(layer_id, issues))

    parts: dict[str, dict[str, Any]] = {}
    for side in _SIDES:
        authored = normalized["parts"][side]
        guide = [
            _resolve_anchor(
                layer_id,
                side,
                anchor,
                joints=joints,
                canvas=(canvas_width, canvas_height),
            )
            for anchor in authored["guide"]
        ]
        pivot = _resolve_anchor(
            layer_id,
            side,
            authored["pivot"],
            joints=joints,
            canvas=(canvas_width, canvas_height),
        )
        parts[side] = {
            "guide_anchors": guide,
            "pivot_anchor": pivot,
            "pivot_xy": list(pivot["xy"]),
            "candidate_bone": authored["candidate_bone"],
        }

    _validate_effective_guides(layer_id, parts)
    return {
        "split_spec_sha256": canonical_sha256(normalized),
        "parts": parts,
    }


def _resolve_anchor(
    layer_id: str,
    side: str,
    anchor: Mapping[str, Any],
    *,
    joints: Mapping[str, Mapping[str, Any]],
    canvas: tuple[int, int],
) -> dict[str, Any]:
    if anchor["kind"] == "manual_proxy":
        return deepcopy(dict(anchor))

    joint_id = str(anchor["joint_id"])
    return _resolve_joint(layer_id, side, joint_id, joints, canvas)


def _resolve_joint(
    layer_id: str,
    side: str,
    joint_id: str,
    joints: Mapping[str, Mapping[str, Any]],
    canvas: tuple[int, int],
) -> dict[str, Any]:
    joint = _require_joint(layer_id, joint_id, joints)
    state = joint.get("review_state")
    if state not in _USABLE_JOINT_STATES:
        raise SplitSpecResolutionError(
            f"Layer {layer_id} {side} split joint {joint_id} is not accepted; "
            "author a manual_proxy when anatomy is unobservable"
        )
    point = _joint_point(layer_id, joint_id, joint, canvas)
    return {
        "kind": "resolved_joint",
        "joint_id": joint_id,
        "xy": point,
        "review_state": state,
    }


def _require_joint(
    layer_id: str,
    joint_id: str,
    joints: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    if joint_id not in joints:
        raise SplitSpecResolutionError(f"Layer {layer_id} needs joint {joint_id}")
    return joints[joint_id]


def _heuristic_guide_spec(role: str) -> tuple[tuple[str, ...], str]:
    if role == "body.hand":
        return ("elbow", "wrist"), "wrist"
    if role == "body.foot":
        return ("knee", "ankle"), "ankle"
    if role.startswith("body.arm"):
        if role.endswith(".lower"):
            return ("elbow", "wrist"), "elbow"
        return ("shoulder", "elbow", "wrist"), "shoulder"
    if role.startswith("body.leg"):
        if role.endswith(".lower"):
            return ("knee", "ankle"), "knee"
        return ("hip", "knee", "ankle"), "hip"
    raise SplitSpecResolutionError(f"Unsupported bilateral role: {role or '<empty>'}")


def _joint_point(
    layer_id: str,
    joint_id: str,
    joint: Mapping[str, Any],
    canvas: tuple[int, int],
) -> list[float]:
    values = (joint.get("x"), joint.get("y"))
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in values
    ):
        raise SplitSpecResolutionError(
            f"Layer {layer_id} split joint {joint_id} has invalid coordinates"
        )
    point = [float(values[0]), float(values[1])]
    if not 0 <= point[0] <= canvas[0] or not 0 <= point[1] <= canvas[1]:
        raise SplitSpecResolutionError(
            f"Layer {layer_id} split joint {joint_id} lies outside the canvas"
        )
    return point


def _validate_effective_guides(
    layer_id: str, parts: Mapping[str, Mapping[str, Any]]
) -> None:
    points: dict[str, list[list[float]]] = {}
    for side in _SIDES:
        side_points = [list(anchor["xy"]) for anchor in parts[side]["guide_anchors"]]
        if len({tuple(point) for point in side_points}) != len(side_points):
            raise SplitSpecResolutionError(
                f"Layer {layer_id} {side} split guide resolves to duplicate points"
            )
        points[side] = side_points
    if points["left"] in (points["right"], list(reversed(points["right"]))):
        raise SplitSpecResolutionError(
            f"Layer {layer_id} split guides resolve to the same polyline"
        )


def _validate_context(
    layer_id: str,
    joints: Mapping[str, Mapping[str, Any]],
    bone_ids: set[str],
    width: int,
    height: int,
) -> None:
    if not isinstance(layer_id, str) or not layer_id:
        raise SplitSpecResolutionError("Split layer id is invalid")
    if not isinstance(joints, Mapping) or not all(
        isinstance(key, str) and isinstance(value, Mapping)
        for key, value in joints.items()
    ):
        raise SplitSpecResolutionError(f"Layer {layer_id} joint index is invalid")
    if not isinstance(bone_ids, set) or not all(isinstance(item, str) for item in bone_ids):
        raise SplitSpecResolutionError(f"Layer {layer_id} bone index is invalid")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in (width, height)):
        raise SplitSpecResolutionError(f"Layer {layer_id} canvas is invalid")


def _issue_message(layer_id: str, issues: list[ValidationIssue]) -> str:
    if not issues:
        return f"Layer {layer_id} split_spec is invalid"
    first = issues[0]
    suffix = f" (+{len(issues) - 1} more)" if len(issues) > 1 else ""
    return f"Layer {layer_id} split_spec {first.path}: {first.message}{suffix}"
