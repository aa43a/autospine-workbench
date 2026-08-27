"""Strict canvas, layer, joint, and bone validation for resolved snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .resolved_snapshot_primitives import (
    array,
    bounded_number,
    contract,
    exact_string_list,
    fail,
    integer,
    object_exact,
    point,
    role,
    safe_id,
    text,
)


_SIDES = {"left", "right", "center", "bilateral", "unknown"}
_DISPOSITIONS = {
    "auto", "keep", "exclude", "ignore", "split", "split_left_right",
    "merge", "review",
}
_REVIEWED_FIELDS = {
    "canonical_role", "side", "disposition", "visible", "pivot_xy",
    "candidate_bone", "notes",
}
_JOINT_STATES = {
    "unreviewed", "candidate_accepted", "manual_adjusted",
    "candidate_rejected", "unobservable",
}
_LAYER_REQUIRED = {
    "schema_version", "contract", "id", "source_index", "name",
    "canonical_role", "side", "disposition", "visible", "empty",
    "opacity", "blend_mode", "z_index", "bbox", "pivot_xy", "image_url",
    "metrics", "review_state", "reviewed_fields",
}
_LAYER_OPTIONAL = {
    "decision_revision", "candidate_bone", "notes", "split_spec",
    "split_spec_revision", "split_decision", "split_decision_revision",
}
_JOINT_REQUIRED = {
    "id", "role", "side", "x", "y", "confidence", "source", "editable",
    "model_confidence", "review_state",
}
_JOINT_OPTIONAL = {
    "decision_kind", "decision_revision", "decision", "review_reason",
    "legacy_review_confidence",
}


@dataclass(frozen=True, slots=True)
class ResolvedEntities:
    width: int
    height: int
    layers: tuple[Mapping[str, Any], ...]
    joints: Mapping[str, Mapping[str, Any]]
    bones: Mapping[str, Mapping[str, Any]]
    requires_review: bool


def validate_entities(
    canvas_value: Any,
    layers_value: Any,
    skeleton_value: Any,
    *,
    project_id: str,
) -> ResolvedEntities:
    width, height = _canvas(canvas_value)
    skeleton, joints, bones, requires_review = _skeleton(
        skeleton_value, width, height
    )
    layers = _layers(layers_value, project_id, width, height)
    return ResolvedEntities(
        width=width,
        height=height,
        layers=tuple(layers),
        joints=joints,
        bones=bones,
        requires_review=requires_review,
    )


def _canvas(value: Any) -> tuple[int, int]:
    root = object_exact(
        value,
        required={"width", "height", "coordinate_system"},
        path="$.canvas",
    )
    width = integer(root.get("width"), "$.canvas.width", minimum=1)
    height = integer(root.get("height"), "$.canvas.height", minimum=1)
    if root.get("coordinate_system") != "canvas-top-left-y-down":
        fail("$.canvas.coordinate_system", "coordinate system is unsupported", "enum")
    return width, height


def _layers(value: Any, project_id: str, width: int, height: int) -> list[Mapping[str, Any]]:
    layers = array(value, "$.layers")
    result: list[Mapping[str, Any]] = []
    identifiers: set[str] = set()
    source_indices: set[int] = set()
    for index, raw in enumerate(layers):
        path = f"$.layers[{index}]"
        layer = object_exact(
            raw, required=_LAYER_REQUIRED, optional=_LAYER_OPTIONAL, path=path
        )
        if layer.get("schema_version") != "autospine-workbench.layer/v1":
            fail(f"{path}.schema_version", "layer version is unsupported", "version")
        contract(layer.get("contract"), f"{path}.contract", "autospine-workbench.layer")
        layer_id = safe_id(layer.get("id"), f"{path}.id")
        if layer_id in identifiers:
            fail(f"{path}.id", "layer id is duplicated", "duplicate")
        identifiers.add(layer_id)
        source_index = integer(layer.get("source_index"), f"{path}.source_index")
        if source_index in source_indices:
            fail(f"{path}.source_index", "source index is duplicated", "duplicate")
        source_indices.add(source_index)
        text(layer.get("name"), f"{path}.name", maximum=512)
        role(layer.get("canonical_role"), f"{path}.canonical_role")
        if layer.get("side") not in _SIDES:
            fail(f"{path}.side", "side is unsupported", "enum")
        if layer.get("disposition") not in _DISPOSITIONS:
            fail(f"{path}.disposition", "disposition is unsupported", "enum")
        if type(layer.get("visible")) is not bool or type(layer.get("empty")) is not bool:
            fail(path, "visible and empty must be booleans", "type")
        bounded_number(layer.get("opacity"), f"{path}.opacity", 0, 1)
        text(layer.get("blend_mode"), f"{path}.blend_mode", maximum=128, nonblank=True)
        if integer(layer.get("z_index"), f"{path}.z_index") != index:
            fail(f"{path}.z_index", "must match canonical layer order", "order")
        _bbox(layer.get("bbox"), f"{path}.bbox", width, height)
        point(layer.get("pivot_xy"), f"{path}.pivot_xy", width, height)
        expected_url = f"/api/projects/{project_id}/layers/{layer_id}/image"
        if layer.get("image_url") != expected_url:
            fail(f"{path}.image_url", "does not match project and layer identity", "identity")
        _metrics(layer.get("metrics"), f"{path}.metrics")
        if layer.get("review_state") not in {"unreviewed", "manual_adjusted"}:
            fail(f"{path}.review_state", "layer review state is unsupported", "enum")
        exact_string_list(
            layer.get("reviewed_fields"), f"{path}.reviewed_fields",
            allowed=_REVIEWED_FIELDS,
        )
        if "candidate_bone" in layer:
            safe_id(layer["candidate_bone"], f"{path}.candidate_bone")
        if "notes" in layer:
            text(layer["notes"], f"{path}.notes", maximum=1000)
        for field in ("decision_revision", "split_spec_revision", "split_decision_revision"):
            if field in layer:
                integer(layer[field], f"{path}.{field}")
        for field in ("split_spec", "split_decision"):
            if field in layer and not isinstance(layer[field], Mapping):
                fail(f"{path}.{field}", "must be a JSON object", "type")
        result.append(layer)
    return result


def _bbox(value: Any, path: str, width: int, height: int) -> None:
    box = object_exact(
        value, required={"x", "y", "width", "height", "right", "bottom"}, path=path
    )
    x = integer(box.get("x"), f"{path}.x")
    y = integer(box.get("y"), f"{path}.y")
    box_width = integer(box.get("width"), f"{path}.width")
    box_height = integer(box.get("height"), f"{path}.height")
    right = integer(box.get("right"), f"{path}.right")
    bottom = integer(box.get("bottom"), f"{path}.bottom")
    if right != x + box_width or bottom != y + box_height:
        fail(path, "right/bottom do not match x/y/width/height", "geometry")
    if right > width or bottom > height:
        fail(path, "bounding box extends outside the canvas", "bounds")


def _metrics(value: Any, path: str) -> None:
    metrics = object_exact(
        value,
        required={
            "alpha_nonzero", "alpha_perceptible", "component_count",
            "main_component_ratio", "fills_bbox_ratio",
        },
        path=path,
    )
    nonzero = integer(metrics.get("alpha_nonzero"), f"{path}.alpha_nonzero")
    perceptible = integer(metrics.get("alpha_perceptible"), f"{path}.alpha_perceptible")
    integer(metrics.get("component_count"), f"{path}.component_count")
    if perceptible > nonzero:
        fail(f"{path}.alpha_perceptible", "cannot exceed alpha_nonzero", "bounds")
    bounded_number(metrics.get("main_component_ratio"), f"{path}.main_component_ratio", 0, 1)
    bounded_number(metrics.get("fills_bbox_ratio"), f"{path}.fills_bbox_ratio", 0, 1)


def _skeleton(
    value: Any, width: int, height: int
) -> tuple[Mapping[str, Any], dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]], bool]:
    root = object_exact(
        value,
        required={
            "schema_version", "contract", "template", "coordinate_system",
            "generation", "joints", "bones",
        },
        path="$.skeleton",
    )
    if root.get("schema_version") != "autospine-workbench.skeleton/v1":
        fail("$.skeleton.schema_version", "skeleton version is unsupported", "version")
    contract(root.get("contract"), "$.skeleton.contract", "autospine-workbench.skeleton")
    safe_id(root.get("template"), "$.skeleton.template")
    coordinates = object_exact(
        root.get("coordinate_system"),
        required={"origin", "x_axis", "y_axis", "side_semantics"},
        path="$.skeleton.coordinate_system",
    )
    expected = {
        "origin": "canvas-top-left", "x_axis": "right", "y_axis": "down",
        "side_semantics": "character-own-left-right",
    }
    if dict(coordinates) != expected:
        fail("$.skeleton.coordinate_system", "coordinate system is unsupported", "enum")
    generation = object_exact(
        root.get("generation"), required={"method", "requires_review"},
        path="$.skeleton.generation",
    )
    text(generation.get("method"), "$.skeleton.generation.method", maximum=128, nonblank=True)
    requires_review = generation.get("requires_review")
    if type(requires_review) is not bool:
        fail("$.skeleton.generation.requires_review", "must be boolean", "type")
    joints = _joints(root.get("joints"), width, height)
    bones = _bones(root.get("bones"), joints)
    return root, joints, bones, requires_review


def _joints(value: Any, width: int, height: int) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(array(value, "$.skeleton.joints")):
        path = f"$.skeleton.joints[{index}]"
        joint = object_exact(raw, required=_JOINT_REQUIRED, optional=_JOINT_OPTIONAL, path=path)
        joint_id = safe_id(joint.get("id"), f"{path}.id")
        if joint_id in result:
            fail(f"{path}.id", "joint id is duplicated", "duplicate")
        role(joint.get("role"), f"{path}.role")
        side = joint.get("side")
        if side not in _SIDES - {"bilateral", "unknown"}:
            fail(f"{path}.side", "joint side is unsupported", "enum")
        if joint_id.endswith(".left") and side != "left" \
                or joint_id.endswith(".right") and side != "right":
            fail(f"{path}.side", "does not match joint id", "side")
        point([joint.get("x"), joint.get("y")], path, width, height)
        confidence = bounded_number(joint.get("confidence"), f"{path}.confidence", 0, 1)
        model = bounded_number(
            joint.get("model_confidence"), f"{path}.model_confidence", 0, 1
        )
        if confidence != model:
            fail(f"{path}.model_confidence", "must preserve model confidence", "identity")
        safe_id(joint.get("source"), f"{path}.source")
        if type(joint.get("editable")) is not bool:
            fail(f"{path}.editable", "must be boolean", "type")
        if joint.get("review_state") not in _JOINT_STATES:
            fail(f"{path}.review_state", "joint review state is unsupported", "enum")
        for field in ("decision_revision",):
            if field in joint:
                integer(joint[field], f"{path}.{field}")
        if "decision" in joint and not isinstance(joint["decision"], Mapping):
            fail(f"{path}.decision", "must be a JSON object", "type")
        if "review_reason" in joint:
            text(joint["review_reason"], f"{path}.review_reason", maximum=1000)
        if "legacy_review_confidence" in joint:
            bounded_number(
                joint["legacy_review_confidence"],
                f"{path}.legacy_review_confidence", 0, 1,
            )
        result[joint_id] = joint
    if not result:
        fail("$.skeleton.joints", "must contain at least one joint", "length")
    return result


def _bones(
    value: Any, joints: Mapping[str, Mapping[str, Any]]
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(array(value, "$.skeleton.bones")):
        path = f"$.skeleton.bones[{index}]"
        bone = object_exact(
            raw,
            required={"id", "role", "parent_id", "start_joint_id", "end_joint_id"},
            path=path,
        )
        bone_id = safe_id(bone.get("id"), f"{path}.id")
        if bone_id in result:
            fail(f"{path}.id", "bone id is duplicated", "duplicate")
        role(bone.get("role"), f"{path}.role")
        parent = bone.get("parent_id")
        if parent is not None:
            safe_id(parent, f"{path}.parent_id")
        start = safe_id(bone.get("start_joint_id"), f"{path}.start_joint_id")
        end = safe_id(bone.get("end_joint_id"), f"{path}.end_joint_id")
        if start not in joints or end not in joints:
            fail(path, "bone references an unknown joint", "cross_reference")
        if start == end:
            fail(path, "bone endpoints must differ", "geometry")
        result[bone_id] = bone
    if not result:
        fail("$.skeleton.bones", "must contain at least one bone", "length")
    for bone_id, bone in result.items():
        parent_id = bone.get("parent_id")
        if parent_id is not None:
            if parent_id not in result:
                fail(f"$.skeleton.bones.{bone_id}.parent_id", "unknown parent bone", "cross_reference")
            if result[parent_id]["end_joint_id"] != bone["start_joint_id"]:
                fail(f"$.skeleton.bones.{bone_id}", "does not connect to its parent", "topology")
        _walk_parent_chain(bone_id, result)
    return result


def _walk_parent_chain(bone_id: str, bones: Mapping[str, Mapping[str, Any]]) -> None:
    seen: set[str] = set()
    cursor: str | None = bone_id
    while cursor is not None:
        if cursor in seen:
            fail(f"$.skeleton.bones.{bone_id}.parent_id", "bone hierarchy contains a cycle", "cycle")
        seen.add(cursor)
        parent = bones[cursor].get("parent_id")
        cursor = parent if isinstance(parent, str) else None
