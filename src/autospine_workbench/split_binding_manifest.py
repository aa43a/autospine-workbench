"""Extract an immutable split-review target from a strict manifest bundle."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from .split_derivation_contract import SplitDerivationError, normalize_derivation


_SIDES = ("left", "right")
_REVIEW_FLAGS = {
    "SEMANTIC_REVIEW_REQUIRED",
    "PIVOT_REVIEW_REQUIRED",
    "BONE_BINDING_REVIEW_REQUIRED",
}


class SplitBindingManifestError(ValueError):
    """Raised when immutable manifest evidence is not a reviewable split."""


def build_manifest_review_target(
    manifest: Mapping[str, Any], layer_id: str
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    """Return the target and operation config proven by one manifest bundle."""

    layers = _index(manifest.get("layers"), "layer_id", "manifest layer")
    parent = _required(layers, layer_id, "manifest split parent")
    parent_raster = _mapping(parent.get("raster"), "manifest parent raster")
    semantic = _mapping(parent.get("semantic"), "manifest parent semantic")
    children: dict[str, Mapping[str, Any]] = {}
    derivation: dict[str, Any] | None = None
    for side in _SIDES:
        child_id = f"{layer_id}--{side}"
        child = _required(layers, child_id, f"manifest {side} child")
        current = _split_derivation(child_id, child.get("derivation"))
        if derivation is not None and current != derivation:
            raise SplitBindingManifestError(
                "Manifest split children disagree on derivation"
            )
        derivation = current
        _require_unreviewed_child(child, semantic.get("canonical_role"), side)
        children[side] = child
    assert derivation is not None
    config = _mapping(derivation.get("operation_config"), "split operation config")
    parts: dict[str, Any] = {}
    for side, child in children.items():
        hint = _mapping(child.get("rig_hint"), f"manifest {side} rig hint")
        raster = _mapping(child.get("raster"), f"manifest {side} raster")
        pivot = _mapping(hint.get("pivot"), f"manifest {side} pivot").get("xy")
        parts[side] = {
            "layer_id": f"{layer_id}--{side}",
            "side": side,
            "pivot_xy": deepcopy(pivot),
            "candidate_bone": hint.get("candidate_bone"),
            "setup_draw_order": hint.get("setup_draw_order"),
            "raster_sha256": raster.get("sha256"),
        }
    target = {
        "source": {
            "layer_id": layer_id,
            "canonical_role": semantic.get("canonical_role"),
            "raster_sha256": parent_raster.get("sha256"),
            "rgba_sha256": config.get("source_rgba_sha256"),
        },
        "operation": {
            "algorithm": deepcopy(config.get("algorithm")),
            "config_sha256": derivation.get("operation_config_sha256"),
            "output_rgba_sha256": deepcopy(config.get("output_rgba_sha256")),
        },
        "parts": parts,
    }
    return target, config


def _require_unreviewed_child(child: Mapping[str, Any], role: Any, side: str) -> None:
    semantic = _mapping(child.get("semantic"), f"manifest {side} semantic")
    hint = _mapping(child.get("rig_hint"), f"manifest {side} rig hint")
    pivot = _mapping(hint.get("pivot"), f"manifest {side} pivot")
    qa = _mapping(child.get("qa"), f"manifest {side} QA")
    flags = qa.get("flags")
    valid_flags = isinstance(flags, list) and all(isinstance(flag, str) for flag in flags)
    if (
        semantic.get("canonical_role") != role
        or semantic.get("side") != side
        or semantic.get("mapping_method") != "alias"
        or hint.get("attachment_kind") != "region"
        or pivot.get("method") != "unknown"
        or qa.get("status") != "manual_required"
        or not valid_flags
        or not _REVIEW_FLAGS.issubset(set(flags))
    ):
        raise SplitBindingManifestError(
            f"Manifest {side} child is not an unreviewed split target"
        )


def _split_derivation(layer_id: str, value: Any) -> dict[str, Any]:
    try:
        result = normalize_derivation(layer_id, value)
    except SplitDerivationError as exc:
        raise SplitBindingManifestError(str(exc)) from exc
    if result.get("operation") != "split":
        raise SplitBindingManifestError(f"Layer {layer_id} is not a split child")
    return result


def _index(value: Any, key: str, label: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SplitBindingManifestError(f"{label} collection is invalid")
    result: dict[str, Mapping[str, Any]] = {}
    for item in value:
        if not isinstance(item, Mapping) or not isinstance(item.get(key), str):
            raise SplitBindingManifestError(f"{label} is invalid")
        identity = item[key]
        if identity in result:
            raise SplitBindingManifestError(f"{label} identity is duplicated")
        result[identity] = item
    return result


def _required(index: Mapping[str, Any], key: str, label: str) -> Mapping[str, Any]:
    if key not in index:
        raise SplitBindingManifestError(f"{label} is missing")
    return index[key]


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SplitBindingManifestError(f"{label} is invalid")
    return value
