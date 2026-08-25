"""Cross-layer and pixel replay checks for materialized bilateral splits."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from .alpha_bilateral_split import (
    AlphaBilateralSplitError,
    split_alpha_bilateral,
    split_alpha_bilateral_v1_1,
)
from .png_rgba import RgbaImage, RgbaPngError, read_rgba_png
from .split_derivation_contract import (
    SPLIT_ALGORITHM_ID,
    SPLIT_ALGORITHM_VERSION,
    SplitDerivationError,
    normalize_derivation,
)


class SplitBundleValidationError(ValueError):
    """Raised when split children cannot be reproduced from their bundled parent."""


def validate_split_bundle(
    manifest: Mapping[str, Any], image_paths: Mapping[str, Path]
) -> None:
    """Validate every split group and replay its deterministic pixel partition."""

    layers = manifest.get("layers")
    if not isinstance(layers, list):
        raise SplitBundleValidationError("Layer Manifest has no layer list")
    by_id: dict[str, Mapping[str, Any]] = {}
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    source_configs: dict[str, str] = {}
    for index, raw_layer in enumerate(layers):
        if not isinstance(raw_layer, Mapping):
            raise SplitBundleValidationError(f"Layer {index} is invalid")
        layer_id = raw_layer.get("layer_id")
        if not isinstance(layer_id, str) or layer_id in by_id:
            raise SplitBundleValidationError("Layer ids must be non-empty and unique")
        by_id[layer_id] = raw_layer
        try:
            derivation = normalize_derivation(layer_id, raw_layer.get("derivation"))
        except SplitDerivationError as exc:
            raise SplitBundleValidationError(str(exc)) from exc
        if derivation["operation"] != "split":
            continue
        source_id = derivation["parent_layer_ids"][0]
        config_hash = derivation["operation_config_sha256"]
        previous = source_configs.setdefault(source_id, config_hash)
        if previous != config_hash:
            raise SplitBundleValidationError(
                f"Split source {source_id} has multiple operation configs"
            )
        groups.setdefault((source_id, config_hash), []).append(raw_layer)
    for (source_id, _), children in sorted(groups.items()):
        _validate_group(source_id, children, by_id, image_paths)


def _validate_group(
    source_id: str,
    children: list[Mapping[str, Any]],
    layers: Mapping[str, Mapping[str, Any]],
    image_paths: Mapping[str, Path],
) -> None:
    parent = layers.get(source_id)
    if parent is None:
        raise SplitBundleValidationError(f"Split parent is not bundled: {source_id}")
    parent_derivation = normalize_derivation(source_id, parent.get("derivation"))
    if parent_derivation["operation"] != "source":
        raise SplitBundleValidationError(f"Split parent is not a source layer: {source_id}")
    if (parent.get("rig_hint") or {}).get("attachment_kind") != "excluded":
        raise SplitBundleValidationError(f"Split parent is not excluded: {source_id}")
    sides: dict[str, Mapping[str, Any]] = {}
    for child in children:
        side = (child.get("semantic") or {}).get("side")
        if side not in {"left", "right"} or side in sides:
            raise SplitBundleValidationError(
                f"Split source {source_id} must have one child per side"
            )
        if (child.get("rig_hint") or {}).get("attachment_kind") != "region":
            raise SplitBundleValidationError(f"Split child {side} is not a region")
        if child.get("layer_id") != f"{source_id}--{side}":
            raise SplitBundleValidationError(
                f"Split child id is not stable for {source_id} {side}"
            )
        sides[side] = child
    if set(sides) != {"left", "right"}:
        raise SplitBundleValidationError(
            f"Split source {source_id} must have exactly left and right children"
        )
    left_derivation = normalize_derivation(
        str(sides["left"].get("layer_id")), sides["left"].get("derivation")
    )
    right_derivation = normalize_derivation(
        str(sides["right"].get("layer_id")), sides["right"].get("derivation")
    )
    if left_derivation != right_derivation:
        raise SplitBundleValidationError(f"Split children disagree on config: {source_id}")
    config = left_derivation["operation_config"]
    _validate_metadata(source_id, parent, sides, config)
    parent_image = _image(source_id, image_paths)
    if _rgba_sha(parent_image) != config["source_rgba_sha256"]:
        raise SplitBundleValidationError(f"Split parent RGBA hash differs: {source_id}")
    try:
        anchors = config["guide_anchors"]
        arguments = {
            "canvas_offset_xy": config["canvas_offset_xy"],
            "left_polyline_xy": [anchor["xy"] for anchor in anchors["left"]],
            "right_polyline_xy": [anchor["xy"] for anchor in anchors["right"]],
        }
        algorithm = config["algorithm"]
        if algorithm == {"id": SPLIT_ALGORITHM_ID, "version": "1.1.0"}:
            replay = split_alpha_bilateral_v1_1(parent_image, **arguments)
        elif algorithm == {
            "id": SPLIT_ALGORITHM_ID,
            "version": SPLIT_ALGORITHM_VERSION,
        }:
            replay = split_alpha_bilateral(
                parent_image,
                component_policy=config["component_policy"],
                **arguments,
            )
            if replay.component_analysis != config["component_analysis"]:
                raise SplitBundleValidationError(
                    f"Split component analysis differs: {source_id}"
                )
        else:
            raise SplitBundleValidationError(
                f"Cannot replay unsupported split algorithm: {algorithm}"
            )
    except AlphaBilateralSplitError as exc:
        raise SplitBundleValidationError(f"Cannot replay split {source_id}: {exc}") from exc
    expected = {"left": replay.left, "right": replay.right}
    counts = {
        "left": replay.left_foreground_pixels,
        "right": replay.right_foreground_pixels,
    }
    for side in ("left", "right"):
        child = sides[side]
        child_id = str(child["layer_id"])
        image = _image(child_id, image_paths)
        if image != expected[side]:
            raise SplitBundleValidationError(f"Split child pixels differ: {child_id}")
        if _rgba_sha(image) != config["output_rgba_sha256"][side]:
            raise SplitBundleValidationError(f"Split child RGBA hash differs: {child_id}")
        alpha_nonzero = ((child.get("raster") or {}).get("alpha_nonzero"))
        if alpha_nonzero != counts[side]:
            raise SplitBundleValidationError(f"Split child alpha count differs: {child_id}")


def _validate_metadata(source_id, parent, sides, config) -> None:
    parent_raster = parent.get("raster") or {}
    if parent_raster.get("sha256") != config["source_raster_sha256"]:
        raise SplitBundleValidationError(f"Split parent raster hash differs: {source_id}")
    if parent_raster.get("canvas_offset_xy") != config["canvas_offset_xy"]:
        raise SplitBundleValidationError(f"Split parent offset differs: {source_id}")
    parent_role = (parent.get("semantic") or {}).get("canonical_role")
    if (parent.get("semantic") or {}).get("side") != "bilateral":
        raise SplitBundleValidationError(f"Split parent is not bilateral: {source_id}")
    for side, child in sides.items():
        child_raster = child.get("raster") or {}
        if child_raster.get("canvas_offset_xy") != parent_raster.get("canvas_offset_xy"):
            raise SplitBundleValidationError(f"Split child offset differs: {side}")
        if child_raster.get("crop_bbox_xywh") != parent_raster.get("crop_bbox_xywh"):
            raise SplitBundleValidationError(f"Split child crop differs: {side}")
        if (child.get("semantic") or {}).get("canonical_role") != parent_role:
            raise SplitBundleValidationError(f"Split child role differs: {side}")


def _image(layer_id: str, paths: Mapping[str, Path]) -> RgbaImage:
    path = paths.get(layer_id)
    if path is None:
        raise SplitBundleValidationError(f"Split raster is missing: {layer_id}")
    try:
        return read_rgba_png(Path(path))
    except RgbaPngError as exc:
        raise SplitBundleValidationError(f"Split raster is unreadable: {layer_id}") from exc


def _rgba_sha(image: RgbaImage) -> str:
    return hashlib.sha256(image.pixels).hexdigest()
