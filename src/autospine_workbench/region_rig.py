"""Compile a reviewed Layer Manifest into a region-only RigIR setup."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import math
import re
from typing import Any, Mapping, Sequence

from .resolved_project import canonical_sha256
from .rig_fk import compile_setup_bones
from .region_rig_contract import (
    RegionRigContractError,
    is_finite as _finite,
    is_integer as _integer,
    mapping as _mapping,
    point as _point,
    positive_size as _positive_size,
    required_sha as _required_sha,
    review_gate,
    safe_image_path as _relative_path,
    validate_compile_inputs,
)
from .rig_validation import RigSemanticValidationError, RigSemanticValidator


_COMPILER_VERSION = "1.0.0"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_BLENDS = frozenset({"normal", "additive", "multiply", "screen"})
_PIVOT_METHODS = frozenset({"landmark", "overlap", "manual"})


class RegionRigError(ValueError):
    """Raised when region-only compilation would lose or invent setup data."""


@dataclass(frozen=True, slots=True)
class RegionRigCompilation:
    """Immutable compilation result; accessors return isolated JSON values."""

    _rig_json: str
    _run_manifest_json: str

    @property
    def rig(self) -> dict[str, Any]:
        return json.loads(self._rig_json)

    @property
    def run_manifest(self) -> dict[str, Any]:
        return json.loads(self._run_manifest_json)

    def to_dict(self) -> dict[str, Any]:
        return {"rig": self.rig, "run_manifest": self.run_manifest}


def compile_region_rig(
    manifest: Mapping[str, Any],
    resolved: Mapping[str, Any],
    *,
    layer_manifest_sha256: str,
    image_sizes: Mapping[str, Sequence[int]],
    allow_manual_required: bool = False,
) -> RegionRigCompilation:
    """Compile only lossless region attachments from two pinned P2 inputs."""

    if not isinstance(allow_manual_required, bool):
        raise RegionRigError("allow_manual_required must be a boolean")
    try:
        identity = validate_compile_inputs(manifest, resolved, layer_manifest_sha256)
        manual_required = review_gate(manifest, resolved, allow_manual_required)
        skeleton = _mapping(resolved.get("skeleton"), "resolved skeleton")
    except RegionRigContractError as exc:
        raise RegionRigError(str(exc)) from exc
    try:
        bones = compile_setup_bones(skeleton)
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise RegionRigError(f"Could not compile setup bones: {exc}") from exc
    bone_ids = _compiled_bone_ids(bones)
    try:
        regions = _compile_regions(
            manifest, skeleton, bone_ids, image_sizes, identity["canvas"]
        )
    except RegionRigContractError as exc:
        raise RegionRigError(str(exc)) from exc
    run_manifest = _run_manifest(identity, allow_manual_required)
    source = {
        "run_manifest_sha256": canonical_sha256(run_manifest),
        "layer_manifest_sha256": identity["layer_manifest_sha256"],
    }
    if identity["override_patch_sha256"] is not None:
        source["override_patch_sha256"] = identity["override_patch_sha256"]
    review_status = "manual_required" if manual_required else "passed"
    rig = {
        "format": "autospine-rig-ir",
        "format_version": 1,
        "source": source,
        "canvas": {
            "width": identity["canvas"][0], "height": identity["canvas"][1],
            "origin": "top_left", "x_axis": "right", "y_axis": "down",
            "units": "pixel",
        },
        "capabilities": ["region_attachment", "setup_draw_order"],
        "unsupported_feature_policy": "fail",
        "bones": deepcopy(bones),
        "slots": [item["slot"] for item in regions],
        "attachments": [item["attachment"] for item in regions],
        "skins": {"default": {
            item["slot"]["id"]: [item["attachment"]["id"]]
            for item in regions
        }},
        "animations": [],
        "qa": {
            "status": review_status,
            "checks": [{
                "id": "layer-manifest-review", "status": review_status,
                "message": (
                    "Manual-required Layer Manifest was explicitly allowed."
                    if manual_required else "Layer Manifest review gate passed."
                ),
            }],
            "manual_override_ids": sorted(
                item["layer_id"] for item in regions if item["manual"]
            ),
        },
    }
    try:
        RigSemanticValidator().raise_for_errors(rig)
        canonical_sha256(rig)
    except (RigSemanticValidationError, TypeError, ValueError) as exc:
        raise RegionRigError(f"Compiled RigIR is invalid: {exc}") from exc
    encode = lambda value: json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    return RegionRigCompilation(encode(rig), encode(run_manifest))


def _compile_regions(manifest, skeleton, bone_ids, image_sizes, canvas):
    if not isinstance(image_sizes, Mapping):
        raise RegionRigError("image_sizes must be keyed by layer id")
    source_bones = skeleton.get("bones")
    if not isinstance(source_bones, list):
        raise RegionRigError("Resolved skeleton bones must be an array")
    seen_layers: set[str] = set()
    draw_orders: set[int] = set()
    result: list[dict[str, Any]] = []
    for index, raw_layer in enumerate(manifest["layers"]):
        layer = _mapping(raw_layer, f"layer {index}")
        layer_id = layer.get("layer_id")
        if not isinstance(layer_id, str) or not _SAFE_ID.fullmatch(layer_id) or layer_id in seen_layers:
            raise RegionRigError("Layer ids must be safe and unique")
        seen_layers.add(layer_id)
        hint = _mapping(layer.get("rig_hint"), f"layer {layer_id} rig hint")
        kind = hint.get("attachment_kind")
        if kind == "excluded":
            continue
        if kind != "region":
            raise RegionRigError(f"Layer {layer_id} has unsupported attachment kind: {kind}")
        source = _mapping(layer.get("source"), f"layer {layer_id} source")
        raster = _mapping(layer.get("raster"), f"layer {layer_id} raster")
        draw_order = hint.get("setup_draw_order")
        if not _integer(draw_order) or draw_order in draw_orders:
            raise RegionRigError(f"Layer {layer_id} has invalid or duplicate draw order")
        draw_orders.add(draw_order)
        blend = source.get("blend_mode")
        if blend not in _BLENDS:
            raise RegionRigError(f"Layer {layer_id} has unsupported blend mode: {blend}")
        opacity = source.get("opacity")
        if not _finite(opacity) or not 0 <= float(opacity) <= 1:
            raise RegionRigError(f"Layer {layer_id} opacity is invalid")
        if not isinstance(source.get("visible"), bool):
            raise RegionRigError(f"Layer {layer_id} visibility is invalid")
        pivot = _mapping(hint.get("pivot"), f"layer {layer_id} pivot")
        if pivot.get("method") not in _PIVOT_METHODS:
            raise RegionRigError(f"Layer {layer_id} pivot is unknown")
        pivot_xy = _point(pivot.get("xy"), f"layer {layer_id} pivot")
        if not 0 <= pivot_xy[0] <= canvas[0] or not 0 <= pivot_xy[1] <= canvas[1]:
            raise RegionRigError(f"Layer {layer_id} pivot is outside the canvas")
        size = _positive_size(image_sizes.get(layer_id), f"layer {layer_id} image size")
        offset = _point(raster.get("canvas_offset_xy"), f"layer {layer_id} canvas offset")
        _validate_raster(layer_id, raster, size, offset, canvas)
        bone = _resolve_candidate_bone(hint.get("candidate_bone"), bone_ids, source_bones)
        image_path = _relative_path(raster.get("artifact_path"), layer_id)
        image_sha = _required_sha(raster.get("sha256"), f"layer {layer_id} image")
        alpha = math.floor(float(opacity) * 255 + 0.5)
        attachment = {
            "id": layer_id, "slot": layer_id, "type": "region",
            "image_path": image_path, "image_sha256": image_sha,
            "source_layer_ids": [layer_id], "canvas_offset_xy": offset,
            "pivot_xy": pivot_xy, "size": size,
        }
        slot = {
            "id": layer_id, "bone": bone,
            "setup_attachment": layer_id if source["visible"] else None,
            "setup_draw_order": draw_order, "blend": blend,
            "color_rgba": f"ffffff{alpha:02x}",
        }
        semantic = _mapping(layer.get("semantic"), f"layer {layer_id} semantic")
        manual = semantic.get("mapping_method") == "manual" or pivot.get("method") == "manual"
        result.append({"layer_id": layer_id, "slot": slot, "attachment": attachment, "manual": manual})
    return sorted(result, key=lambda item: (item["slot"]["setup_draw_order"], item["layer_id"]))


def _validate_raster(layer_id, raster, size, offset, canvas) -> None:
    if _positive_size(raster.get("canvas_size"), f"layer {layer_id} raster canvas") != canvas:
        raise RegionRigError(f"Layer {layer_id} raster canvas differs from the project")
    bbox = raster.get("crop_bbox_xywh")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4 or not all(_integer(v) for v in bbox):
        raise RegionRigError(f"Layer {layer_id} crop bbox is invalid")
    x, y, width, height = bbox
    cropped = size == [width, height] and offset == [x, y]
    full_canvas = size == canvas and offset == [0, 0]
    if width < 1 or height < 1 or x < 0 or y < 0 or x + width > canvas[0] or y + height > canvas[1]:
        raise RegionRigError(f"Layer {layer_id} crop bbox is outside the canvas")
    if not cropped and not full_canvas:
        raise RegionRigError(f"Layer {layer_id} image size or offset does not match its raster")


def _resolve_candidate_bone(hint, bone_ids: set[str], source_bones: list[Any]) -> str:
    if not isinstance(hint, str) or not _SAFE_ID.fullmatch(hint):
        raise RegionRigError("Region candidate_bone is missing or invalid")
    if hint in bone_ids:
        return hint
    matches = {
        item.get("id") for item in source_bones
        if isinstance(item, Mapping) and item.get("end_joint_id") == hint
        and item.get("id") in bone_ids
    }
    if len(matches) == 1:
        return next(iter(matches))
    if len(matches) > 1:
        raise RegionRigError(f"Legacy candidate_bone {hint} is ambiguous")
    raise RegionRigError(f"candidate_bone {hint} does not exist in compiled bones")


def _run_manifest(identity: Mapping[str, Any], allow_manual_required: bool) -> dict[str, Any]:
    inputs = {
        "layer_manifest_sha256": identity["layer_manifest_sha256"],
        "resolved_project_sha256": identity["resolved_project_sha256"],
    }
    if identity["override_patch_sha256"] is not None:
        inputs["override_patch_sha256"] = identity["override_patch_sha256"]
    return {
        "format": "autospine-rig-compile-run", "format_version": 1,
        "project_id": identity["project_id"], "inputs": inputs,
        "compiler": {
            "id": "region-rig-compiler", "version": _COMPILER_VERSION,
            "config": {
                "attachment_profile": "region-only",
                "allow_manual_required": bool(allow_manual_required),
            },
        },
    }


def _compiled_bone_ids(bones: Any) -> set[str]:
    if not isinstance(bones, list) or not bones:
        raise RegionRigError("Setup bone compiler returned no bones")
    ids = [item.get("id") for item in bones if isinstance(item, Mapping)]
    if len(ids) != len(bones) or any(not isinstance(item, str) or not _SAFE_ID.fullmatch(item) for item in ids):
        raise RegionRigError("Setup bone compiler returned invalid bone ids")
    if len(set(ids)) != len(ids):
        raise RegionRigError("Setup bone compiler returned duplicate bone ids")
    return set(ids)
