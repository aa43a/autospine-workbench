"""Exact cross-binding between a reviewed manifest and its verified P2 base."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import re
from typing import Any

from .manifest_artifacts import LayerManifestError, canonical_layer_artifact_path
from .manifest_artifacts import require_sha256, validate_raster_geometry
from .mesh_contract import MeshContractError, require_base_region_rig
from .resolved_project import canonical_sha256


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_CANVAS_AXES = {
    "origin": "top_left", "x_axis": "right", "y_axis": "down", "units": "pixel",
}
_ATTACHMENT_FIELDS = {
    "id", "slot", "type", "image_path", "image_sha256",
    "source_layer_ids", "canvas_offset_xy", "pivot_xy", "size",
}
_SLOT_FIELDS = {
    "id", "bone", "setup_attachment", "setup_draw_order", "blend",
    "color_rgba",
}


class MeshManifestBindingError(ValueError):
    """Raised when P3 inputs do not describe the same reviewed P2 setup."""


def require_manifest_matches_base(
    manifest: Mapping[str, Any],
    base_rig: Mapping[str, Any],
    base_run: Mapping[str, Any],
    image_sizes: Mapping[str, Sequence[int]],
) -> None:
    """Bind all reader-returned assets; never follow latest or compare revision."""

    manifest = _mapping(manifest, "Layer Manifest")
    base_rig = _mapping(base_rig, "base RigIR")
    base_run = _mapping(base_run, "base compile run")
    image_sizes = _mapping(image_sizes, "manifest image sizes")
    try:
        base_identity = require_base_region_rig(base_rig, base_run)
        manifest_sha = canonical_sha256(manifest)
    except (MeshContractError, TypeError, ValueError) as exc:
        raise MeshManifestBindingError("P2 base or manifest identity is invalid") from exc

    if (
        manifest.get("format") != "autospine-layer-manifest"
        or manifest.get("format_version") != 1
        or isinstance(manifest.get("format_version"), bool)
    ):
        raise MeshManifestBindingError("Layer Manifest format is unsupported")
    if manifest_sha != base_identity["layer_manifest_sha256"]:
        raise MeshManifestBindingError("Manifest content address differs from P2 base")
    if manifest.get("project_id") != base_identity["project_id"]:
        raise MeshManifestBindingError("Manifest project differs from the P2 base")
    _passed_qa(manifest.get("qa"), "Layer Manifest")
    canvas = _require_canvas(manifest, base_rig)

    layers = _objects(manifest.get("layers"), "Layer Manifest layers")
    by_id: dict[str, Mapping[str, Any]] = {}
    sizes: dict[str, tuple[int, int]] = {}
    folded_ids: set[str] = set()
    for index, layer in enumerate(layers):
        layer_id = _safe_id(layer.get("layer_id"), f"layer {index} id")
        key = layer_id.casefold()
        if key in folded_ids:
            raise MeshManifestBindingError(f"Duplicate manifest layer id: {layer_id}")
        folded_ids.add(key)
        by_id[layer_id] = layer
        _passed_qa(layer.get("qa"), f"layer {layer_id}")
        sizes[layer_id] = _size(
            image_sizes.get(layer_id), f"layer {layer_id} image size"
        )
        _require_materialized_raster(layer, layer_id, sizes[layer_id], canvas)

    if any(not isinstance(key, str) for key in image_sizes) or set(image_sizes) != set(by_id):
        raise MeshManifestBindingError("Image sizes must match all manifest layers")

    attachments = _index_by_id(base_rig.get("attachments"), "base attachments")
    slots = _index_by_id(base_rig.get("slots"), "base slots")
    region_ids = _require_layer_kinds(by_id, attachments)
    if not region_ids:
        raise MeshManifestBindingError("Manifest has no region layers")
    if set(attachments) != region_ids or set(slots) != region_ids:
        raise MeshManifestBindingError("Base regions do not exactly match manifest")

    expected_skin: dict[str, list[str]] = {}
    for layer_id in sorted(region_ids):
        _require_region_binding(
            layer_id, by_id[layer_id], sizes[layer_id],
            attachments[layer_id], slots[layer_id],
        )
        expected_skin[layer_id] = [layer_id]
    skins = _mapping(base_rig.get("skins"), "base skins")
    if set(skins) != {"default"} or skins.get("default") != expected_skin:
        raise MeshManifestBindingError(
            "Base default skin does not exactly match manifest region layers"
        )


def _require_canvas(
    manifest: Mapping[str, Any], base_rig: Mapping[str, Any]
) -> tuple[int, int]:
    source = _mapping(manifest.get("source"), "Layer Manifest source")
    canvas = _size(source.get("canvas"), "Layer Manifest canvas")
    coordinates = _mapping(
        source.get("coordinate_system"), "Layer Manifest coordinate system"
    )
    if any(coordinates.get(key) != value for key, value in _CANVAS_AXES.items()):
        raise MeshManifestBindingError("Manifest coordinate system is unsupported")
    expected = {"width": canvas[0], "height": canvas[1], **_CANVAS_AXES}
    if base_rig.get("canvas") != expected:
        raise MeshManifestBindingError("Manifest canvas differs from the base RigIR")
    return canvas


def _require_materialized_raster(
    layer: Mapping[str, Any],
    layer_id: str,
    image_size: tuple[int, int],
    canvas: tuple[int, int],
) -> None:
    raster = _mapping(layer.get("raster"), f"layer {layer_id} raster")
    try:
        expected_path = canonical_layer_artifact_path(layer_id)
        require_sha256(raster.get("sha256"), f"Layer {layer_id} image")
        validate_raster_geometry(raster, image_size, canvas, layer_id=layer_id)
    except LayerManifestError as exc:
        raise MeshManifestBindingError(
            f"Layer {layer_id} materialized raster is invalid"
        ) from exc
    if raster.get("artifact_path") != expected_path:
        raise MeshManifestBindingError(f"Layer {layer_id} path is not canonical")
    if (
        raster.get("channels") != "RGBA"
        or raster.get("alpha_mode") != "straight"
        or raster.get("color_space") != "srgb"
    ):
        raise MeshManifestBindingError(f"Layer {layer_id} raster is unsupported")


def _require_layer_kinds(
    layers: Mapping[str, Mapping[str, Any]],
    attachments: Mapping[str, Mapping[str, Any]],
) -> set[str]:
    bound_sources: list[str] = []
    for attachment_id, attachment in attachments.items():
        if set(attachment) != _ATTACHMENT_FIELDS:
            raise MeshManifestBindingError(
                f"Base attachment {attachment_id} shape is unsupported"
            )
        source_ids = attachment.get("source_layer_ids")
        if not isinstance(source_ids, list) or len(source_ids) != 1:
            raise MeshManifestBindingError(
                f"Base attachment {attachment_id} must bind one source layer"
            )
        bound_sources.append(_safe_id(source_ids[0], "attachment source layer"))
    if len(set(bound_sources)) != len(bound_sources):
        raise MeshManifestBindingError("A manifest layer is bound more than once")

    region_ids: set[str] = set()
    for layer_id, layer in layers.items():
        hint = _mapping(layer.get("rig_hint"), f"layer {layer_id} rig hint")
        kind = hint.get("attachment_kind")
        if kind == "region":
            region_ids.add(layer_id)
        elif kind == "excluded":
            if layer_id in bound_sources or layer_id in attachments:
                raise MeshManifestBindingError(
                    f"Excluded layer {layer_id} has a base attachment"
                )
        else:
            raise MeshManifestBindingError(
                f"Layer {layer_id} has unsupported attachment kind: {kind}"
            )
    if set(bound_sources) != region_ids:
        raise MeshManifestBindingError(
            "Base attachment sources do not exactly match manifest regions"
        )
    return region_ids


def _require_region_binding(
    layer_id: str,
    layer: Mapping[str, Any],
    image_size: tuple[int, int],
    attachment: Mapping[str, Any],
    slot: Mapping[str, Any],
) -> None:
    if set(slot) != _SLOT_FIELDS:
        raise MeshManifestBindingError(f"Base slot {layer_id} shape is unsupported")
    source = _mapping(layer.get("source"), f"layer {layer_id} source")
    raster = _mapping(layer.get("raster"), f"layer {layer_id} raster")
    hint = _mapping(layer.get("rig_hint"), f"layer {layer_id} rig hint")
    pivot = _mapping(hint.get("pivot"), f"layer {layer_id} pivot")
    pivot_xy = pivot.get("xy")
    draw_order = hint.get("setup_draw_order")
    opacity = _opacity(source.get("opacity"), layer_id)
    visible = source.get("visible")
    if not isinstance(visible, bool):
        raise MeshManifestBindingError(f"Layer {layer_id} visibility is invalid")
    expected_attachment = {
        "id": layer_id,
        "slot": layer_id,
        "type": "region",
        "image_path": raster.get("artifact_path"),
        "image_sha256": raster.get("sha256"),
        "source_layer_ids": [layer_id],
        "canvas_offset_xy": raster.get("canvas_offset_xy"),
        "pivot_xy": pivot_xy,
        "size": list(image_size),
    }
    expected_slot = {
        "id": layer_id,
        "bone": hint.get("candidate_bone"),
        "setup_attachment": layer_id if visible else None,
        "setup_draw_order": draw_order,
        "blend": source.get("blend_mode"),
        "color_rgba": f"ffffff{math.floor(opacity * 255 + 0.5):02x}",
    }
    if not _canonical_equal(attachment, expected_attachment):
        raise MeshManifestBindingError(
            f"Base attachment {layer_id} differs from its manifest layer"
        )
    if not _canonical_equal(slot, expected_slot):
        raise MeshManifestBindingError(
            f"Base slot {layer_id} differs from its manifest layer"
        )


def _index_by_id(value: Any, label: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(_objects(value, label)):
        item_id = _safe_id(item.get("id"), f"{label} item {index} id")
        if item_id in result:
            raise MeshManifestBindingError(f"{label} contains duplicate id: {item_id}")
        result[item_id] = item
    return result


def _passed_qa(value: Any, label: str) -> None:
    if not isinstance(value, Mapping) or value.get("status") != "passed":
        raise MeshManifestBindingError(f"{label} QA must be passed")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MeshManifestBindingError(f"{label} must be an object")
    return value


def _objects(value: Any, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise MeshManifestBindingError(f"{label} must be an array")
    if any(not isinstance(item, Mapping) for item in value):
        raise MeshManifestBindingError(f"{label} must contain only objects")
    return tuple(value)


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise MeshManifestBindingError(f"{label} must be a safe id")
    return value


def _canonical_equal(first: Any, second: Any) -> bool:
    try:
        return canonical_sha256(first) == canonical_sha256(second)
    except (TypeError, ValueError):
        return False


def _size(value: Any, label: str) -> tuple[int, int]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or len(value) != 2
        or any(not isinstance(item, int) or isinstance(item, bool) or item < 1 for item in value)
    ):
        raise MeshManifestBindingError(f"{label} must contain two positive integers")
    return int(value[0]), int(value[1])


def _opacity(value: Any, layer_id: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0 <= float(value) <= 1
    ):
        raise MeshManifestBindingError(f"Layer {layer_id} opacity is invalid")
    return float(value)
