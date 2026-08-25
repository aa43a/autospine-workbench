"""Rebuild the current bilateral split review target from trusted inputs."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .alpha_bilateral_split import AlphaBilateralSplitError, split_alpha_bilateral
from .manifest_artifacts import sha256_file
from .png_rgba import RgbaImage, RgbaPngError, encode_rgba_png, read_rgba_png
from .resolved_project import canonical_sha256
from .split_binding_manifest import (
    SplitBindingManifestError,
    build_manifest_review_target,
)
from .split_derivation_contract import (
    SPLIT_ALGORITHM_ID,
    SPLIT_ALGORITHM_VERSION,
    SPLIT_FORMAT_VERSION,
    SPLIT_TIE_BREAK,
    SplitDerivationError,
    build_split_derivation,
)
from .split_component_policy import default_split_component_policy
from .split_spec_resolution import SplitSpecResolutionError, resolve_split_spec


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SIDES = ("left", "right")
_SPLIT = frozenset({"split", "split_left_right"})


class SplitBindingTargetError(ValueError):
    """Raised when trusted context cannot be inspected safely."""


class SplitBindingArtifactError(SplitBindingTargetError):
    """Raised when an artifact contradicts its immutable bundle evidence."""


class _StaleTarget(ValueError):
    pass


def preview_matches_current(
    document: Mapping[str, Any],
    manifest: Mapping[str, Any],
    resolved: Mapping[str, Any],
    source_path: Path,
) -> bool:
    """Return whether preview, bundle, and current authoring describe one target."""

    _validate_resolved(resolved, str(document.get("project_id") or ""))
    try:
        manifest_target, manifest_config = build_manifest_review_target(
            manifest, str(document.get("layer_id") or "")
        )
    except SplitBindingManifestError as exc:
        raise SplitBindingArtifactError(str(exc)) from exc
    if document.get("review_target") != manifest_target:
        raise SplitBindingArtifactError(
            "Split preview does not match its referenced Layer Manifest"
        )
    try:
        current_target, current_spec = _current_target(
            resolved,
            str(document["layer_id"]),
            Path(source_path),
            manifest_target,
            manifest_config,
        )
    except _StaleTarget:
        return False
    return (
        document.get("split_spec") == current_spec
        and document.get("review_target") == current_target
    )


def _current_target(
    resolved: Mapping[str, Any],
    layer_id: str,
    source_path: Path,
    manifest_target: Mapping[str, Any],
    manifest_config: Mapping[str, Any],
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    layers = _index(resolved.get("layers"), "id", "resolved layer")
    layer = layers.get(layer_id)
    if layer is None or layer.get("side") != "bilateral" or layer.get("disposition") not in _SPLIT:
        raise _StaleTarget("Layer is no longer an authored bilateral split")
    skeleton = _mapping(resolved.get("skeleton"), "resolved skeleton")
    joints = _index(skeleton.get("joints"), "id", "resolved joint")
    bone_ids = set(_index(skeleton.get("bones", []), "id", "resolved bone"))
    width, height = _canvas(resolved)
    try:
        authoring = resolve_split_spec(
            layer_id,
            layer.get("split_spec"),
            joints=joints,
            bone_ids=bone_ids,
            canvas_width=width,
            canvas_height=height,
        )
    except SplitSpecResolutionError as exc:
        raise _StaleTarget(str(exc)) from exc
    image, raster_sha, rgba_sha = _source_image(source_path)
    offset = _source_offset(layer, image, (width, height))
    guides = {
        side: authoring["parts"][side]["guide_anchors"] for side in _SIDES
    }
    component_policy = default_split_component_policy()
    try:
        split = split_alpha_bilateral(
            image,
            canvas_offset_xy=offset,
            left_polyline_xy=[anchor["xy"] for anchor in guides["left"]],
            right_polyline_xy=[anchor["xy"] for anchor in guides["right"]],
            component_policy=component_policy,
        )
        outputs = {
            "left": hashlib.sha256(split.left.pixels).hexdigest(),
            "right": hashlib.sha256(split.right.pixels).hexdigest(),
        }
        rasters = {
            "left": hashlib.sha256(encode_rgba_png(split.left)).hexdigest(),
            "right": hashlib.sha256(encode_rgba_png(split.right)).hexdigest(),
        }
        config = {
            "format": "autospine-bilateral-alpha-split",
            "format_version": SPLIT_FORMAT_VERSION,
            "algorithm": {
                "id": SPLIT_ALGORITHM_ID,
                "version": SPLIT_ALGORITHM_VERSION,
            },
            "component_analysis": split.component_analysis,
            "component_policy": component_policy,
            "source_layer_id": layer_id,
            "source_raster_sha256": raster_sha,
            "source_rgba_sha256": rgba_sha,
            "output_rgba_sha256": outputs,
            "canvas_offset_xy": list(offset),
            "guide_anchors": guides,
            "tie_break": SPLIT_TIE_BREAK,
            "exact_partition": True,
        }
        operation_sha = build_split_derivation(config)["operation_config_sha256"]
    except (AlphaBilateralSplitError, SplitDerivationError) as exc:
        raise _StaleTarget(str(exc)) from exc
    orders = _child_orders(resolved.get("layers"), layer_id)
    parts = {
        side: {
            "layer_id": f"{layer_id}--{side}",
            "side": side,
            "pivot_xy": deepcopy(authoring["parts"][side]["pivot_xy"]),
            "candidate_bone": authoring["parts"][side]["candidate_bone"],
            "setup_draw_order": orders[side],
            "raster_sha256": rasters[side],
        }
        for side in _SIDES
    }
    target = {
        "source": {
            "layer_id": layer_id,
            "canonical_role": layer.get("canonical_role"),
            "raster_sha256": raster_sha,
            "rgba_sha256": rgba_sha,
        },
        "operation": {
            "algorithm": deepcopy(config["algorithm"]),
            "config_sha256": operation_sha,
            "output_rgba_sha256": outputs,
        },
        "parts": parts,
    }
    if config == manifest_config and target != manifest_target:
        raise _StaleTarget("Current rig review fields differ from the manifest")
    return target, layer["split_spec"]


def _validate_resolved(resolved: Any, project_id: str) -> None:
    if not isinstance(resolved, Mapping) or resolved.get("project_id") != project_id:
        raise SplitBindingTargetError("Resolved snapshot identity is invalid")
    digest = resolved.get("sha256")
    body = {key: value for key, value in resolved.items() if key != "sha256"}
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise SplitBindingTargetError("Resolved snapshot digest is invalid")
    if canonical_sha256(body) != digest:
        raise SplitBindingTargetError("Resolved snapshot content hash is invalid")


def _source_image(path: Path) -> tuple[RgbaImage, str, str]:
    try:
        resolved = path.resolve(strict=True)
        if path.is_symlink() or not resolved.is_file():
            raise OSError("unsafe source")
        image = read_rgba_png(resolved)
        return image, sha256_file(resolved), hashlib.sha256(image.pixels).hexdigest()
    except (OSError, RgbaPngError) as exc:
        raise SplitBindingTargetError("Current source raster is unavailable") from exc


def _source_offset(
    layer: Mapping[str, Any], image: RgbaImage, canvas: tuple[int, int]
) -> tuple[int, int]:
    bbox = layer.get("bbox")
    if not isinstance(bbox, Mapping):
        raise _StaleTarget("Current layer bbox is invalid")
    values = tuple(bbox.get(key) for key in ("x", "y", "width", "height"))
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise _StaleTarget("Current layer bbox is invalid")
    x, y, width, height = values
    if (image.width, image.height) == canvas:
        return (0, 0)
    if (image.width, image.height) == (width, height):
        return (x, y)
    raise _StaleTarget("Current source dimensions differ from the layer bbox")


def _child_orders(value: Any, layer_id: str) -> dict[str, int]:
    layers = list(_index(value, "id", "resolved layer").values())
    try:
        ordered = sorted(layers, key=lambda layer: layer["z_index"])
    except (KeyError, TypeError) as exc:
        raise _StaleTarget("Resolved draw order is invalid") from exc
    cursor = 0
    for layer in ordered:
        if layer.get("id") == layer_id:
            return {"left": cursor + 1, "right": cursor + 2}
        cursor += 3 if layer.get("disposition") in _SPLIT else 1
    raise _StaleTarget("Split layer is absent from draw order")


def _canvas(resolved: Mapping[str, Any]) -> tuple[int, int]:
    canvas = _mapping(resolved.get("canvas"), "resolved canvas")
    width, height = canvas.get("width"), canvas.get("height")
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in (width, height)):
        raise SplitBindingTargetError("Resolved canvas is invalid")
    return width, height


def _index(value: Any, key: str, label: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SplitBindingTargetError(f"{label} collection is invalid")
    result: dict[str, Mapping[str, Any]] = {}
    for item in value:
        if not isinstance(item, Mapping) or not isinstance(item.get(key), str):
            raise SplitBindingTargetError(f"{label} is invalid")
        identity = item[key]
        if identity in result:
            raise SplitBindingTargetError(f"{label} identity is duplicated")
        result[identity] = item
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SplitBindingTargetError(f"{label} is invalid")
    return value
