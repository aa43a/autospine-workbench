"""Exact static Layer Manifest/P3 admission for seam-anchor authoring."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import math
from typing import Any

from .manifest_artifacts import (
    LayerManifestError,
    canonical_layer_artifact_path,
    require_safe_token,
    require_sha256,
)
from .mesh_bundle_integrity import VerifiedMeshBundle
from . import seam_anchor_profile as profile
from .seam_anchor_json_snapshot import snapshot_layer_manifest
from .seam_anchor_source import SeamAnchorSourceError, admit_seam_anchor_source
from .split_derivation_contract import SplitDerivationError, normalize_derivation


_MANIFEST_FIELDS = {
    "format", "format_version", "project_id", "revision", "source",
    "layers", "qa",
}
_SOURCE_REQUIRED = {"psd_sha256", "canvas", "coordinate_system"}
_SOURCE_ALLOWED = _SOURCE_REQUIRED | {"audit_sha256", "relative_path"}
_COORDINATES = {
    "origin": "top_left", "x_axis": "right", "y_axis": "down",
    "units": "pixel", "side_naming": "character_side",
}
_LAYER_REQUIRED = {
    "layer_id", "source", "raster", "semantic", "rig_hint", "qa",
}
_LAYER_ALLOWED = _LAYER_REQUIRED | {"derivation"}
_RASTER_REQUIRED = {
    "artifact_path", "sha256", "canvas_size", "crop_bbox_xywh",
    "canvas_offset_xy", "channels", "alpha_mode", "color_space",
    "alpha_nonzero",
}


class SeamAnchorInputError(ValueError):
    """Raised when static seam inputs are stale, cross-wired, or excessive."""


@dataclass(frozen=True, slots=True)
class SeamAnchorInputs:
    """Copy-isolated static snapshots with an exact P3/image identity."""

    project_id: str
    layer_manifest_sha256: str
    attachment_image_set_sha256: str
    _manifest_json: str = field(repr=False)
    _rig_json: str = field(repr=False)
    _image_items: tuple[tuple[str, str, str, int, int, bytes], ...] = field(repr=False)
    _source_json: str = field(repr=False)

    @property
    def manifest(self) -> dict[str, Any]:
        return json.loads(self._manifest_json)

    @property
    def rig(self) -> dict[str, Any]:
        return json.loads(self._rig_json)

    @property
    def attachment_images(self) -> tuple[dict[str, Any], ...]:
        return tuple({
            "attachment_id": row[0], "image_path": row[1],
            "image_sha256": row[2], "width": row[3], "height": row[4],
        } for row in self._image_items)

    @property
    def png_by_attachment(self) -> dict[str, bytes]:
        return {row[0]: row[5] for row in self._image_items}

    @property
    def source(self) -> dict[str, Any]:
        return json.loads(self._source_json)


def require_seam_anchor_inputs(
    layer_manifest: Mapping[str, Any],
    mesh_bundle: VerifiedMeshBundle,
) -> SeamAnchorInputs:
    """Replay exact static P3 values; never admit motion or P10 clip state."""

    try:
        if type(mesh_bundle) is not VerifiedMeshBundle:
            raise SeamAnchorInputError(
                "Seam anchors require an exact VerifiedMeshBundle"
            )
        manifest, manifest_json = snapshot_layer_manifest(layer_manifest)
        canvas, layers = _require_manifest(manifest)
        admitted = admit_seam_anchor_source(
            manifest, canvas, layers, mesh_bundle
        )
        return SeamAnchorInputs(
            mesh_bundle.project_id, mesh_bundle.layer_manifest_sha256,
            admitted.attachment_image_set_sha256, manifest_json,
            admitted.rig_json, admitted.image_items, admitted.source_json,
        )
    except SeamAnchorInputError:
        raise
    except _FAILURES as exc:
        raise SeamAnchorInputError(
            f"Static seam-anchor input admission failed: {exc}"
        ) from exc


def _require_manifest(value: dict[str, Any]):
    _shape(value, _MANIFEST_FIELDS, _MANIFEST_FIELDS, "Layer Manifest")
    if value.get("format") != "autospine-layer-manifest" \
            or type(value.get("format_version")) is not int \
            or value["format_version"] != 1:
        raise SeamAnchorInputError("Layer Manifest format is unsupported")
    require_safe_token(value.get("project_id"), "Layer Manifest project id")
    if type(value.get("revision")) is not int or value["revision"] < 0:
        raise SeamAnchorInputError("Layer Manifest revision is invalid")
    source = _object(value.get("source"), "Layer Manifest source")
    _shape(source, _SOURCE_REQUIRED, _SOURCE_ALLOWED, "Layer Manifest source")
    require_sha256(source.get("psd_sha256"), "Layer Manifest PSD")
    if "audit_sha256" in source:
        require_sha256(source["audit_sha256"], "Layer Manifest audit")
    relative = source.get("relative_path")
    if "relative_path" in source and (
        not isinstance(relative, str) or not relative or "\\" in relative
        or relative.startswith("/") or ".." in relative.split("/")
        or (len(relative) > 1 and relative[1] == ":")
    ):
        raise SeamAnchorInputError("Layer Manifest relative path is unsafe")
    canvas = _positive_pair(source.get("canvas"), "Layer Manifest canvas")
    coordinates = _object(
        source.get("coordinate_system"), "Layer Manifest coordinates"
    )
    expected_coordinate_keys = set(_COORDINATES) | {
        "view_orientation", "mirror_state",
    }
    _shape(
        coordinates, expected_coordinate_keys, expected_coordinate_keys,
        "Layer Manifest coordinates",
    )
    if any(coordinates.get(key) != expected for key, expected in _COORDINATES.items()) \
            or coordinates.get("view_orientation") not in {
                "front", "three_quarter", "profile", "back", "unknown",
            } or coordinates.get("mirror_state") not in {
                "not_mirrored", "mirrored", "unknown",
            }:
        raise SeamAnchorInputError(
            "Layer Manifest coordinate space is unsupported"
        )
    rows = value.get("layers")
    if not isinstance(rows, list) or len(rows) > profile.MAX_MANIFEST_LAYERS:
        raise SeamAnchorInputError(
            "Layer Manifest layer inventory resource limit exceeded"
        )
    layers, folded = {}, set()
    for index, row in enumerate(rows):
        layer = _object(row, f"Layer Manifest layer {index}")
        _shape(layer, _LAYER_REQUIRED, _LAYER_ALLOWED, f"Layer {index}")
        identifier = require_safe_token(layer.get("layer_id"), f"Layer {index} id")
        if identifier.casefold() in folded:
            raise SeamAnchorInputError("Layer Manifest ids are duplicated")
        folded.add(identifier.casefold())
        _require_layer_shape(layer, identifier, canvas)
        layers[identifier] = layer
    _qa(value.get("qa"), "Layer Manifest")
    if value["qa"]["status"] != "passed":
        raise SeamAnchorInputError("Static seams require a passed Layer Manifest")
    return canvas, layers


def _require_layer_shape(layer, identifier, canvas) -> None:
    source = _object(layer.get("source"), f"Layer {identifier} source")
    _shape(source, {"name", "index", "visible", "opacity", "blend_mode"},
           {"name", "index", "group_path", "visible", "opacity", "blend_mode"},
           f"Layer {identifier} source")
    group = source.get("group_path", [])
    if not isinstance(source.get("name"), str) \
            or type(source.get("index")) is not int or source["index"] < 0 \
            or type(source.get("visible")) is not bool \
            or not _bounded_number(source.get("opacity"), 0, 1) \
            or not isinstance(source.get("blend_mode"), str) \
            or not source["blend_mode"] or not isinstance(group, list) \
            or any(not isinstance(item, str) for item in group):
        raise SeamAnchorInputError("Layer Manifest source values are invalid")
    raster = _object(layer.get("raster"), f"Layer {identifier} raster")
    _shape(raster, _RASTER_REQUIRED, _RASTER_REQUIRED | {"component_areas"},
           f"Layer {identifier} raster")
    if raster.get("artifact_path") != canonical_layer_artifact_path(identifier) \
            or _positive_pair(raster.get("canvas_size"), "raster canvas") != canvas \
            or raster.get("channels") != "RGBA" \
            or raster.get("alpha_mode") != "straight" \
            or raster.get("color_space") != "srgb":
        raise SeamAnchorInputError("Layer Manifest raster shape is unsupported")
    require_sha256(raster.get("sha256"), f"Layer {identifier} raster")
    crop = _integer_array(raster.get("crop_bbox_xywh"), 4, "raster crop")
    _integer_array(raster.get("canvas_offset_xy"), 2, "raster offset")
    alpha, areas = raster.get("alpha_nonzero"), raster.get("component_areas", [])
    if min(crop) < 0 or crop[0] + crop[2] > canvas[0] \
            or crop[1] + crop[3] > canvas[1] \
            or type(alpha) is not int or alpha < 0 \
            or not isinstance(areas, list) \
            or any(type(area) is not int or area < 1 for area in areas):
        raise SeamAnchorInputError("Layer Manifest raster values are invalid")
    semantic = _object(layer.get("semantic"), "layer semantic")
    _shape(semantic,
           {"source_tag", "canonical_role", "side", "mapping_method", "confidence"},
           {"source_tag", "canonical_role", "side", "stratum", "instance",
            "mapping_method", "confidence"}, "layer semantic")
    if not isinstance(semantic.get("source_tag"), str) \
            or not isinstance(semantic.get("canonical_role"), str) \
            or not semantic["canonical_role"] \
            or semantic.get("side") not in {"left", "right", "center", "bilateral", "unknown"} \
            or semantic.get("stratum", "unknown") not in {"back", "body", "front", "unknown"} \
            or type(semantic.get("instance", 0)) is not int \
            or semantic.get("instance", 0) < 0 \
            or semantic.get("mapping_method") not in {"exact", "alias", "components", "model", "manual", "unknown"} \
            or not _bounded_number(semantic.get("confidence"), 0, 1):
        raise SeamAnchorInputError("Layer Manifest semantic values are invalid")
    rig_hint = _object(layer.get("rig_hint"), "layer rig hint")
    _shape(rig_hint,
           {"attachment_kind", "setup_draw_order"},
           {"attachment_kind", "deform_class", "candidate_bone", "pivot",
            "setup_draw_order"}, "layer rig hint")
    if rig_hint.get("attachment_kind") not in {
        "region", "mesh", "sprite_set", "excluded", "unknown",
    } or rig_hint.get("deform_class", "unknown") not in {
        "rigid", "hinge", "soft", "hair", "cloth", "face", "unknown",
    } or type(rig_hint.get("setup_draw_order")) is not int:
        raise SeamAnchorInputError("Layer Manifest rig hint values are invalid")
    _qa(layer.get("qa"), f"Layer {identifier}")
    if "derivation" in layer:
        normalize_derivation(identifier, layer["derivation"])


def _shape(value, required, allowed, label):
    if not required <= set(value) or not set(value) <= allowed:
        raise SeamAnchorInputError(f"{label} fields are unsupported")


def _object(value, label):
    if not isinstance(value, Mapping):
        raise SeamAnchorInputError(f"{label} must be an object")
    return value


def _positive_pair(value, label):
    result = _integer_array(value, 2, label)
    if min(result) < 1:
        raise SeamAnchorInputError(f"{label} must be positive")
    return result


def _integer_array(value, length, label):
    if not isinstance(value, list) or len(value) != length \
            or any(type(item) is not int for item in value):
        raise SeamAnchorInputError(f"{label} must contain exact integers")
    return tuple(value)


def _bounded_number(value, minimum, maximum):
    return not isinstance(value, bool) and isinstance(value, (int, float)) \
        and math.isfinite(value) and minimum <= value <= maximum


def _qa(value, label):
    value = _object(value, f"{label} QA")
    _shape(value, {"status", "flags"}, {"status", "flags", "notes"}, f"{label} QA")
    if value.get("status") not in {"passed", "manual_required", "rejected"} \
            or not isinstance(value.get("flags"), list):
        raise SeamAnchorInputError(f"{label} QA is invalid")


_FAILURES = (
    AttributeError, KeyError, LayerManifestError, OverflowError,
    RecursionError, RuntimeError, SeamAnchorSourceError, SplitDerivationError,
    TypeError, UnicodeError, ValueError,
)
