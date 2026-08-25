"""Materialize bilateral alpha partitions for Layer Manifest authoring."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re
from typing import Any, Mapping

from .alpha_bilateral_split import AlphaBilateralSplitError, split_alpha_bilateral
from .alpha_geometry import analyze_alpha_png
from .layer_manifest import sha256_file
from .png_rgba import RgbaImage, RgbaPngError, read_rgba_png, write_rgba_png
from .split_derivation_contract import (
    SPLIT_ALGORITHM_ID,
    SPLIT_ALGORITHM_VERSION,
    SPLIT_TIE_BREAK,
    SplitDerivationError,
    build_split_derivation,
)


class LayerSplitMaterializationError(ValueError):
    """Raised when a split cannot be reproduced without guessing."""


@dataclass(frozen=True, slots=True)
class MaterializedLayerSet:
    """Transient layer overlay; it never impersonates a resolved snapshot."""

    layers: tuple[dict[str, Any], ...]
    assets: dict[str, Path]


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SPLIT = frozenset({"split", "split_left_right"})
_USABLE_GUIDE_JOINT = frozenset({"candidate_accepted", "manual_adjusted"})


def materialize_bilateral_splits(
    project: Mapping[str, Any],
    layer_assets: Mapping[str, Path],
    output_dir: Path,
) -> MaterializedLayerSet:
    """Build an exact overlay with excluded parents and stable split children."""
    if not isinstance(project, Mapping) or not isinstance(layer_assets, Mapping):
        raise LayerSplitMaterializationError("project and layer_assets must be mappings")
    resolved = project.get("resolved")
    if not isinstance(resolved, Mapping) or not isinstance(resolved.get("layers"), list):
        raise LayerSplitMaterializationError("Project has no resolved layer snapshot")
    canvas_value = resolved.get("canvas") or project.get("canvas")
    if not isinstance(canvas_value, Mapping):
        raise LayerSplitMaterializationError("Resolved snapshot has no canvas")
    width, height = canvas_value.get("width"), canvas_value.get("height")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in (width, height)
    ):
        raise LayerSplitMaterializationError("Resolved canvas is invalid")
    canvas = (width, height)
    layers = _ordered_layers(resolved["layers"])
    ids = [layer["id"] for layer in layers]
    derived_ids = [
        f"{layer['id']}--{side}"
        for layer in layers
        if layer.get("disposition") in _SPLIT
        for side in ("left", "right")
    ]
    if any(not _SAFE_ID.fullmatch(value) for value in derived_ids):
        raise LayerSplitMaterializationError("Derived layer id is unsafe")
    if set(ids) & set(derived_ids) or len(derived_ids) != len(set(derived_ids)):
        raise LayerSplitMaterializationError("Derived layer id collides with another layer")
    joints = _joint_index(resolved.get("skeleton"))
    target = _output_directory(output_dir)
    assets = {str(key): Path(value) for key, value in layer_assets.items()}
    expanded: list[dict[str, Any]] = []
    for source_layer in layers:
        layer = deepcopy(dict(source_layer))
        if layer.get("disposition") not in _SPLIT:
            expanded.append(layer)
            continue
        children, derived_assets = _materialize_layer(layer, joints, assets, target, canvas)
        layer["disposition"] = "exclude"
        layer["reviewed_fields"] = [v for v in layer.get("reviewed_fields", []) if v != "disposition"]
        expanded.append(layer)
        expanded.extend(children)
        assets.update(derived_assets)
    for z_index, layer in enumerate(expanded):
        layer["z_index"] = z_index
    return MaterializedLayerSet(tuple(expanded), assets)


def _ordered_layers(value: list[Any]) -> list[Mapping[str, Any]]:
    """Validate and restore the authoritative setup order before expansion."""

    layers: list[Mapping[str, Any]] = []
    ids: set[str] = set()
    z_indices: set[int] = set()
    for layer in value:
        if not isinstance(layer, Mapping) or not isinstance(layer.get("id"), str):
            raise LayerSplitMaterializationError("Resolved snapshot has an invalid layer")
        layer_id = layer["id"]
        if not _SAFE_ID.fullmatch(layer_id):
            raise LayerSplitMaterializationError(f"Layer id is unsafe: {layer_id}")
        if layer_id in ids:
            raise LayerSplitMaterializationError("Resolved layer ids are not unique")
        z_index = layer.get("z_index")
        if isinstance(z_index, bool) or not isinstance(z_index, int):
            raise LayerSplitMaterializationError(
                f"Layer {layer_id} z_index must be an integer"
            )
        if z_index in z_indices:
            raise LayerSplitMaterializationError(
                f"Resolved layer z_index is duplicated: {z_index}"
            )
        ids.add(layer_id)
        z_indices.add(z_index)
        layers.append(layer)
    return sorted(layers, key=lambda layer: layer["z_index"])


def _materialize_layer(
    layer: dict[str, Any],
    joints: Mapping[str, Mapping[str, Any]],
    assets: Mapping[str, Path],
    target: Path,
    canvas: tuple[int, int],
) -> tuple[list[dict[str, Any]], dict[str, Path]]:
    layer_id = layer["id"]
    if layer.get("side") != "bilateral":
        raise LayerSplitMaterializationError(f"Layer {layer_id} must be bilateral")
    guide_names, pivot_name = _guide_spec(str(layer.get("canonical_role") or ""))
    source = _source_asset(layer_id, assets.get(layer_id))
    try:
        image = read_rgba_png(source)
    except RgbaPngError as exc:
        raise LayerSplitMaterializationError(f"Layer {layer_id} is not RGBA PNG") from exc
    bbox, offset = _raster_geometry(layer_id, layer.get("bbox"), image, canvas)
    guide_anchors = {
        side: [
            _resolved_joint_anchor(layer_id, joints, f"{name}.{side}")
            for name in guide_names
        ]
        for side in ("left", "right")
    }
    guide_points = {
        side: [anchor["xy"] for anchor in guide_anchors[side]]
        for side in ("left", "right")
    }
    try:
        split = split_alpha_bilateral(
            image,
            canvas_offset_xy=offset,
            left_polyline_xy=guide_points["left"],
            right_polyline_xy=guide_points["right"],
        )
    except AlphaBilateralSplitError as exc:
        raise LayerSplitMaterializationError(f"Layer {layer_id} split failed: {exc}") from exc
    config = {
        "format": "autospine-bilateral-alpha-split",
        "format_version": 1,
        "algorithm": {"id": SPLIT_ALGORITHM_ID, "version": SPLIT_ALGORITHM_VERSION},
        "source_layer_id": layer_id,
        "source_raster_sha256": sha256_file(source),
        "source_rgba_sha256": hashlib.sha256(image.pixels).hexdigest(),
        "output_rgba_sha256": {
            "left": hashlib.sha256(split.left.pixels).hexdigest(),
            "right": hashlib.sha256(split.right.pixels).hexdigest(),
        },
        "canvas_offset_xy": list(offset),
        "guide_anchors": guide_anchors,
        "tie_break": SPLIT_TIE_BREAK,
        "exact_partition": True,
    }
    try:
        derivation = build_split_derivation(config)
    except SplitDerivationError as exc:
        raise LayerSplitMaterializationError(str(exc)) from exc
    paths = {side: target / f"{layer_id}--{side}.png" for side in ("left", "right")}
    if any(path.exists() or path.is_symlink() for path in paths.values()):
        raise LayerSplitMaterializationError(f"Layer {layer_id} output already exists")

    children: list[dict[str, Any]] = []
    for side, output_image in (("left", split.left), ("right", split.right)):
        path = paths[side]
        try:
            write_rgba_png(path, output_image)
        except RgbaPngError as exc:
            raise LayerSplitMaterializationError(f"Layer {layer_id} write failed") from exc
        pivot_id = f"{pivot_name}.{side}"
        children.append(
            _child_layer(
                layer,
                side,
                bbox,
                output_image,
                path,
                derivation,
                _joint_point(layer_id, joints, pivot_id),
            )
        )
    return children, {child["id"]: paths[child["side"]] for child in children}


def _child_layer(
    parent: Mapping[str, Any],
    side: str,
    bbox: Mapping[str, int],
    image: RgbaImage,
    path: Path,
    derivation: Mapping[str, Any],
    pivot_xy: list[float],
) -> dict[str, Any]:
    child = deepcopy(dict(parent))
    child["id"] = f"{parent['id']}--{side}"
    child["name"] = f"{parent.get('name') or parent['id']} ({side})"
    child.update(side=side, disposition="keep", empty=False)
    child["bbox"] = deepcopy(dict(bbox))
    child["pivot_xy"] = pivot_xy
    child["derivation"] = deepcopy(dict(derivation))
    child.pop("image_url", None)
    child.pop("candidate_bone", None)
    # A reviewed source layer or guide joint does not approve the generated
    # child raster, semantic side, pivot, or binding.  P2b may add reviewed
    # fields only after a decision is bound to this exact split artifact.
    child["reviewed_fields"] = []
    child["review_state"] = "unreviewed"
    alphas = image.pixels[3::4]
    geometry = analyze_alpha_png(path, threshold=1)
    areas = [component.area for component in geometry.components]
    nonzero = sum(value > 0 for value in alphas)
    child["metrics"] = {
        "alpha_nonzero": nonzero,
        "alpha_perceptible": sum(value >= 8 for value in alphas),
        "component_count": len(areas),
        "main_component_ratio": max(areas, default=0) / nonzero,
        "fills_bbox_ratio": min(1.0, nonzero / (bbox["width"] * bbox["height"])),
    }
    return child


def _guide_spec(role: str) -> tuple[tuple[str, ...], str]:
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
    raise LayerSplitMaterializationError(f"Unsupported bilateral role: {role or '<empty>'}")


def _joint_index(value: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, Mapping) or not isinstance(value.get("joints"), list):
        raise LayerSplitMaterializationError("Resolved snapshot has no skeleton joints")
    result: dict[str, Mapping[str, Any]] = {}
    for joint in value["joints"]:
        if not isinstance(joint, Mapping) or not isinstance(joint.get("id"), str):
            raise LayerSplitMaterializationError("Resolved skeleton has an invalid joint")
        if joint["id"] in result:
            raise LayerSplitMaterializationError("Resolved joint ids are not unique")
        result[joint["id"]] = joint
    return result


def _joint_point(
    layer_id: str, joints: Mapping[str, Mapping[str, Any]], joint_id: str
) -> list[float]:
    if joint_id not in joints:
        raise LayerSplitMaterializationError(f"Layer {layer_id} needs joint {joint_id}")
    values = (joints[joint_id].get("x"), joints[joint_id].get("y"))
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in values
    ):
        raise LayerSplitMaterializationError(f"Guide joint {joint_id} is invalid")
    return [float(value) for value in values]


def _resolved_joint_anchor(
    layer_id: str, joints: Mapping[str, Mapping[str, Any]], joint_id: str
) -> dict[str, Any]:
    if joint_id not in joints:
        raise LayerSplitMaterializationError(f"Layer {layer_id} needs joint {joint_id}")
    review_state = joints[joint_id].get("review_state")
    if review_state not in _USABLE_GUIDE_JOINT:
        raise LayerSplitMaterializationError(
            f"Layer {layer_id} guide joint {joint_id} is not accepted"
        )
    return {
        "kind": "resolved_joint",
        "joint_id": joint_id,
        "xy": _joint_point(layer_id, joints, joint_id),
        "review_state": review_state,
    }


def _raster_geometry(
    layer_id: str, value: Any, image: RgbaImage, canvas: tuple[int, int]
) -> tuple[dict[str, int], tuple[int, int]]:
    keys = ("x", "y", "width", "height")
    if not isinstance(value, Mapping) or any(
        isinstance(value.get(key), bool) or not isinstance(value.get(key), int)
        for key in keys
    ):
        raise LayerSplitMaterializationError(f"Layer {layer_id} alpha bbox is invalid")
    bbox = {key: value[key] for key in keys}
    x, y, width, height = (bbox[key] for key in keys)
    outside = x < 0 or y < 0 or x + width > canvas[0] or y + height > canvas[1]
    if width < 1 or height < 1 or outside:
        raise LayerSplitMaterializationError(f"Layer {layer_id} alpha bbox is invalid")
    if (image.width, image.height) == canvas:
        return bbox, (0, 0)
    if (image.width, image.height) == (width, height):
        return bbox, (x, y)
    raise LayerSplitMaterializationError(f"Layer {layer_id} dimensions differ from bbox")


def _output_directory(value: Path) -> Path:
    path = Path(value)
    try:
        path.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or not path.is_dir():
            raise LayerSplitMaterializationError("Split output directory is unsafe")
        return path.resolve(strict=True)
    except OSError as exc:
        raise LayerSplitMaterializationError("Split output directory is unavailable") from exc


def _source_asset(layer_id: str, value: Any) -> Path:
    if value is None:
        raise LayerSplitMaterializationError(f"Layer asset is missing: {layer_id}")
    path = Path(value)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise LayerSplitMaterializationError(f"Layer asset is missing: {layer_id}") from exc
    if path.is_symlink() or not resolved.is_file():
        raise LayerSplitMaterializationError(f"Layer asset is unsafe: {layer_id}")
    return resolved
