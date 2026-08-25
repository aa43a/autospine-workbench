"""Immutable reviewer target for one materialized bilateral split."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Mapping, Sequence

from .resolved_project import canonical_sha256
from .split_derivation_contract import SplitDerivationError, normalize_derivation
from .split_preview_contract import (
    SPLIT_PREVIEW_FORMAT,
    SplitPreviewContractError,
    require_valid_split_preview,
)
from .split_spec_resolution import SplitSpecResolutionError, resolve_split_spec
from .split_specs import infer_humanoid_bone_ids, normalize_split_spec


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SAFE_ROLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SIDES = ("left", "right")


class SplitPreviewError(ValueError):
    """Raised when a split preview cannot be proven from its inputs."""


def build_split_preview(
    project: Mapping[str, Any],
    materialized_layers: Any,
    manifest: Mapping[str, Any],
    *,
    layer_manifest_sha256: str,
    parent_layer_id: str,
) -> dict[str, Any]:
    """Build the exact review target for one authored bilateral split."""

    if not isinstance(project, Mapping) or not isinstance(manifest, Mapping):
        raise SplitPreviewError("Project and Layer Manifest must be objects")
    project_id = _safe_id(project.get("id"), "project id")
    parent_layer_id = _safe_id(parent_layer_id, "parent layer id")
    resolved = _mapping(project.get("resolved"), "resolved snapshot")
    resolved_sha = _snapshot_sha(resolved)
    if resolved.get("project_id") not in {None, project_id}:
        raise SplitPreviewError("Resolved snapshot belongs to another project")
    if manifest.get("project_id") != project_id:
        raise SplitPreviewError("Layer Manifest belongs to another project")
    if manifest.get("revision") != resolved.get("revision"):
        raise SplitPreviewError("Layer Manifest revision differs from the snapshot")
    manifest_sha = _sha(layer_manifest_sha256, "Layer Manifest digest")
    if canonical_sha256(manifest) != manifest_sha:
        raise SplitPreviewError("Layer Manifest does not match its digest")

    resolved_layers = _index_layers(resolved.get("layers"), "resolved")
    overlay = getattr(materialized_layers, "layers", materialized_layers)
    overlay_layers = _index_layers(overlay, "materialized")
    manifest_layers = _index_manifest_layers(manifest.get("layers"))
    parent = _required(resolved_layers, parent_layer_id, "resolved parent")
    overlay_parent = _required(overlay_layers, parent_layer_id, "materialized parent")
    manifest_parent = _required(manifest_layers, parent_layer_id, "manifest parent")
    role = _validate_parent(parent_layer_id, parent, overlay_parent, manifest_parent)
    split_spec, effective_spec = _canonical_split_spec(parent, resolved)

    children: dict[str, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    derivation: dict[str, Any] | None = None
    for side in _SIDES:
        child_id = f"{parent_layer_id}--{side}"
        child = _required(overlay_layers, child_id, f"materialized {side} child")
        manifest_child = _required(manifest_layers, child_id, f"manifest {side} child")
        current = _split_derivation(child_id, child.get("derivation"))
        manifest_derivation = _split_derivation(
            child_id, manifest_child.get("derivation")
        )
        if current != manifest_derivation:
            raise SplitPreviewError(f"{side} child derivation differs from the manifest")
        if derivation is None:
            derivation = current
        elif current != derivation:
            raise SplitPreviewError("Split children do not share one operation config")
        children[side] = (child, manifest_child)
    assert derivation is not None
    if derivation["parent_layer_ids"] != [parent_layer_id]:
        raise SplitPreviewError("Split derivation references the wrong parent")
    config = derivation["operation_config"]
    operation_sha = derivation["operation_config_sha256"]
    if config["source_raster_sha256"] != _raster_sha(manifest_parent):
        raise SplitPreviewError("Split source raster differs from the manifest parent")
    _match_effective_guides(effective_spec, config)

    target_parts: dict[str, Any] = {}
    for side in _SIDES:
        child, manifest_child = children[side]
        effective_part = effective_spec["parts"][side]
        target_parts[side] = _target_part(
            parent_layer_id,
            role,
            side,
            child,
            manifest_child,
            effective_part,
        )
    review_target = {
        "source": {
            "layer_id": parent_layer_id,
            "canonical_role": role,
            "raster_sha256": _raster_sha(manifest_parent),
            "rgba_sha256": config["source_rgba_sha256"],
        },
        "operation": {
            "algorithm": deepcopy(config["algorithm"]),
            "config_sha256": operation_sha,
            "output_rgba_sha256": deepcopy(config["output_rgba_sha256"]),
        },
        "parts": target_parts,
    }
    document = {
        "format": SPLIT_PREVIEW_FORMAT,
        "project_id": project_id,
        "layer_id": parent_layer_id,
        "resolved_snapshot_sha256": resolved_sha,
        "layer_manifest_sha256": manifest_sha,
        "split_spec": split_spec,
        "operation_config_sha256": operation_sha,
        "review_target": review_target,
        "review_target_sha256": canonical_sha256(review_target),
    }
    try:
        require_valid_split_preview(document)
    except SplitPreviewContractError as exc:
        raise SplitPreviewError(str(exc)) from exc
    return document


def _validate_parent(layer_id, source, overlay, manifest) -> str:
    if source.get("side") != "bilateral" or source.get("disposition") not in {
        "split", "split_left_right",
    }:
        raise SplitPreviewError(f"Layer {layer_id} is not an authored bilateral split")
    if overlay.get("disposition") != "exclude":
        raise SplitPreviewError("Materialized split parent must be excluded")
    if overlay.get("side") != "bilateral":
        raise SplitPreviewError("Materialized split parent must remain bilateral")
    semantic = _mapping(manifest.get("semantic"), "manifest parent semantic")
    hint = _mapping(manifest.get("rig_hint"), "manifest parent rig hint")
    role = source.get("canonical_role")
    if not isinstance(role, str) or not _SAFE_ROLE.fullmatch(role):
        raise SplitPreviewError("Split parent role is invalid")
    if overlay.get("canonical_role") != role or semantic.get("canonical_role") != role:
        raise SplitPreviewError("Split parent role differs across inputs")
    if semantic.get("side") != "bilateral" or hint.get("attachment_kind") != "excluded":
        raise SplitPreviewError("Manifest split parent identity is invalid")
    try:
        overlay_source = normalize_derivation(layer_id, overlay.get("derivation"))
        manifest_source = normalize_derivation(layer_id, manifest.get("derivation"))
        if overlay_source["operation"] != "source" or manifest_source["operation"] != "source":
            raise SplitPreviewError("Split parent is not a source layer")
    except SplitDerivationError as exc:
        raise SplitPreviewError(str(exc)) from exc
    return role


def _canonical_split_spec(
    parent: Mapping[str, Any], resolved: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = parent.get("split_spec")
    skeleton = _mapping(resolved.get("skeleton"), "resolved skeleton")
    joints = _index_named(skeleton.get("joints"), "joint")
    bone_ids = set(infer_humanoid_bone_ids(set(joints)))
    for bone in _sequence(skeleton.get("bones", []), "resolved bones"):
        if isinstance(bone, Mapping) and isinstance(bone.get("id"), str):
            bone_ids.add(bone["id"])
    canvas = _mapping(resolved.get("canvas"), "resolved canvas")
    width, height = canvas.get("width"), canvas.get("height")
    if not _positive_int(width) or not _positive_int(height):
        raise SplitPreviewError("Resolved canvas is invalid")
    issues: list[Any] = []
    normalized = normalize_split_spec(
        spec,
        path="$.split_spec",
        joint_ids=set(joints),
        bone_ids=bone_ids,
        canvas_width=width,
        canvas_height=height,
        issues=issues,
    )
    if issues or normalized is None:
        detail = issues[0].message if issues else "invalid split spec"
        raise SplitPreviewError(f"Split spec is invalid: {detail}")
    if normalized != spec:
        raise SplitPreviewError("Split spec is not in canonical normalized form")
    try:
        effective = resolve_split_spec(
            str(parent.get("id") or ""),
            normalized,
            joints=joints,
            bone_ids=bone_ids,
            canvas_width=width,
            canvas_height=height,
        )
    except SplitSpecResolutionError as exc:
        raise SplitPreviewError(str(exc)) from exc
    if effective.get("split_spec_sha256") != canonical_sha256(normalized):
        raise SplitPreviewError("Resolved split_spec identity is inconsistent")
    return deepcopy(normalized), effective


def _match_effective_guides(effective_spec, config) -> None:
    anchors = config.get("guide_anchors")
    if not isinstance(anchors, Mapping):
        raise SplitPreviewError("Effective split guides are missing")
    for side in _SIDES:
        expected = effective_spec["parts"][side]["guide_anchors"]
        if anchors.get(side) != expected:
            raise SplitPreviewError(
                f"{side} effective guide differs from the resolved split_spec"
            )


def _target_part(parent_id, role, side, child, manifest_child, effective_part):
    child_id = f"{parent_id}--{side}"
    semantic = _mapping(manifest_child.get("semantic"), f"{side} child semantic")
    hint = _mapping(manifest_child.get("rig_hint"), f"{side} child rig hint")
    if (
        child.get("id") != child_id
        or child.get("side") != side
        or child.get("canonical_role") != role
        or child.get("disposition") != "keep"
    ):
        raise SplitPreviewError(f"Materialized {side} child identity is invalid")
    if semantic.get("side") != side or semantic.get("canonical_role") != role:
        raise SplitPreviewError(f"Manifest {side} child semantic identity is invalid")
    if hint.get("attachment_kind") != "region":
        raise SplitPreviewError(f"Manifest {side} child is not a region")
    pivot = list(effective_part["pivot_xy"])
    manifest_pivot = _mapping(hint.get("pivot"), f"{side} child pivot")
    if child.get("pivot_xy") != pivot or manifest_pivot.get("xy") != pivot:
        raise SplitPreviewError(f"{side} child pivot differs from split_spec")
    bone = effective_part["candidate_bone"]
    if hint.get("candidate_bone") != bone:
        raise SplitPreviewError(f"{side} child bone differs from split_spec")
    if child.get("proposed_candidate_bone") != bone:
        raise SplitPreviewError(
            f"Materialized {side} child proposed bone differs from split_spec"
        )
    order = child.get("z_index")
    if not isinstance(order, int) or isinstance(order, bool) or hint.get("setup_draw_order") != order:
        raise SplitPreviewError(f"{side} child draw order differs across inputs")
    return {
        "layer_id": child_id,
        "side": side,
        "pivot_xy": pivot,
        "candidate_bone": bone,
        "setup_draw_order": order,
        "raster_sha256": _raster_sha(manifest_child),
    }


def _split_derivation(layer_id: str, value: Any) -> dict[str, Any]:
    try:
        derivation = normalize_derivation(layer_id, value)
    except SplitDerivationError as exc:
        raise SplitPreviewError(str(exc)) from exc
    if derivation["operation"] != "split":
        raise SplitPreviewError(f"Layer {layer_id} is not a split child")
    return derivation


def _snapshot_sha(resolved: Mapping[str, Any]) -> str:
    digest = _sha(resolved.get("sha256"), "resolved snapshot digest")
    body = {key: value for key, value in resolved.items() if key != "sha256"}
    if canonical_sha256(body) != digest:
        raise SplitPreviewError("Resolved snapshot does not match its digest")
    return digest


def _raster_sha(layer: Mapping[str, Any]) -> str:
    return _sha(_mapping(layer.get("raster"), "layer raster").get("sha256"), "raster digest")


def _index_layers(value: Any, label: str) -> dict[str, Mapping[str, Any]]:
    return _index(value, label, "id")


def _index_manifest_layers(value: Any) -> dict[str, Mapping[str, Any]]:
    return _index(value, "manifest", "layer_id")


def _index_named(value: Any, label: str) -> dict[str, Mapping[str, Any]]:
    return _index(value, label, "id")


def _index(value: Any, label: str, id_field: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in _sequence(value, f"{label} layers"):
        if not isinstance(item, Mapping):
            raise SplitPreviewError(f"{label} item is not an object")
        item_id = _safe_id(item.get(id_field), f"{label} item id")
        if item_id in result:
            raise SplitPreviewError(f"{label} item id is duplicated")
        result[item_id] = item
    return result


def _required(index, item_id, label):
    if item_id not in index:
        raise SplitPreviewError(f"{label} is missing: {item_id}")
    return index[item_id]


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SplitPreviewError(f"{label} must be an object")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SplitPreviewError(f"{label} must be an array")
    return value


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise SplitPreviewError(f"{label} is invalid")
    return value


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise SplitPreviewError(f"{label} is not a lowercase SHA-256")
    return value


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
