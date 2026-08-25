"""Semantic contract for materialized bilateral layer split provenance."""

from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any, Mapping

from .alpha_bilateral_split import MAX_GUIDE_POINTS
from .resolved_project import canonical_sha256


SPLIT_ALGORITHM_ID = "nearest-limb-polyline"
SPLIT_ALGORITHM_VERSION = "1.1.0"
SPLIT_TIE_BREAK = "left"

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ID_TOKENS = re.compile(r"[._-]+")
_REVIEW_STATES = frozenset(
    {
        "unreviewed",
        "candidate_accepted",
        "manual_adjusted",
        "candidate_rejected",
        "unobservable",
    }
)


class SplitDerivationError(ValueError):
    """Raised when split provenance is incomplete or internally inconsistent."""


def normalize_derivation(layer_id: str, value: Any) -> dict[str, Any]:
    if value is None:
        return {"operation": "source", "parent_layer_ids": []}
    if not isinstance(value, Mapping):
        raise SplitDerivationError(f"Layer {layer_id} derivation must be an object")
    result = deepcopy(dict(value))
    operation = result.get("operation")
    parents = result.get("parent_layer_ids")
    if operation == "source":
        if parents != [] or set(result) != {"operation", "parent_layer_ids"}:
            raise SplitDerivationError(f"Layer {layer_id} source derivation is invalid")
        return result
    if operation != "split":
        raise SplitDerivationError(f"Layer {layer_id} derivation is unsupported")
    _validate_split(layer_id, result)
    return result


def build_split_derivation(config: Mapping[str, Any]) -> dict[str, Any]:
    config_copy = deepcopy(dict(config))
    source_layer_id = config_copy.get("source_layer_id")
    if not isinstance(source_layer_id, str):
        raise SplitDerivationError("Split config has no source layer id")
    if config_copy.get("algorithm") != {
        "id": SPLIT_ALGORITHM_ID,
        "version": SPLIT_ALGORITHM_VERSION,
    }:
        raise SplitDerivationError("New split config must use the current algorithm")
    result = {
        "operation": "split",
        "parent_layer_ids": [source_layer_id],
        "operation_config_sha256": canonical_sha256(config_copy),
        "operation_config": config_copy,
    }
    _validate_split(f"{source_layer_id} child", result)
    return result


def _validate_split(layer_id: str, derivation: Mapping[str, Any]) -> None:
    if set(derivation) != {
        "operation",
        "parent_layer_ids",
        "operation_config_sha256",
        "operation_config",
    }:
        raise SplitDerivationError(f"Layer {layer_id} split derivation fields are invalid")
    config = derivation.get("operation_config")
    if not isinstance(config, Mapping):
        raise SplitDerivationError(f"Layer {layer_id} split config is missing")
    expected_hash = derivation.get("operation_config_sha256")
    if not isinstance(expected_hash, str) or canonical_sha256(config) != expected_hash:
        raise SplitDerivationError(f"Layer {layer_id} split config hash is invalid")
    required = {
        "format",
        "format_version",
        "algorithm",
        "source_layer_id",
        "source_raster_sha256",
        "source_rgba_sha256",
        "output_rgba_sha256",
        "canvas_offset_xy",
        "guide_anchors",
        "tie_break",
        "exact_partition",
    }
    if set(config) != required:
        raise SplitDerivationError(f"Layer {layer_id} split config fields are invalid")
    source_id = config.get("source_layer_id")
    if not _safe_id(source_id) or derivation.get("parent_layer_ids") != [source_id]:
        raise SplitDerivationError(f"Layer {layer_id} split parent is invalid")
    if (
        config.get("format") != "autospine-bilateral-alpha-split"
        or config.get("format_version") != 1
    ):
        raise SplitDerivationError(f"Layer {layer_id} split format is unsupported")
    algorithm = config.get("algorithm")
    if not isinstance(algorithm, Mapping) or set(algorithm) != {"id", "version"}:
        raise SplitDerivationError(f"Layer {layer_id} split algorithm is invalid")
    version = algorithm.get("version")
    if (
        not _safe_id(algorithm.get("id"))
        or not isinstance(version, str)
        or not version
        or len(version) > 64
        or any(character.isspace() for character in version)
    ):
        raise SplitDerivationError(f"Layer {layer_id} split algorithm is invalid")
    if not _sha(config.get("source_raster_sha256")) or not _sha(
        config.get("source_rgba_sha256")
    ):
        raise SplitDerivationError(f"Layer {layer_id} split source identity is invalid")
    output_hashes = config.get("output_rgba_sha256")
    if (
        not isinstance(output_hashes, Mapping)
        or set(output_hashes) != {"left", "right"}
        or not all(_sha(output_hashes.get(side)) for side in ("left", "right"))
    ):
        raise SplitDerivationError(f"Layer {layer_id} split output identity is invalid")
    _point(config.get("canvas_offset_xy"), f"Layer {layer_id} split offset", integer=True)
    guide_anchors = config.get("guide_anchors")
    if not isinstance(guide_anchors, Mapping):
        raise SplitDerivationError(f"Layer {layer_id} split guides are invalid")
    if set(guide_anchors) != {"left", "right"}:
        raise SplitDerivationError(f"Layer {layer_id} split sides are invalid")
    points_by_side: dict[str, list[list[float]]] = {}
    anchor_ids: set[str] = set()
    for side in ("left", "right"):
        anchors = guide_anchors.get(side)
        if (
            not isinstance(anchors, list)
            or not 2 <= len(anchors) <= MAX_GUIDE_POINTS
        ):
            raise SplitDerivationError(
                f"Layer {layer_id} {side} split guide needs 2 to {MAX_GUIDE_POINTS} anchors"
            )
        points: list[list[float]] = []
        for anchor in anchors:
            anchor_id, point = _anchor(layer_id, side, anchor)
            if anchor_id in anchor_ids:
                raise SplitDerivationError(
                    f"Layer {layer_id} split anchor id is duplicated: {anchor_id}"
                )
            anchor_ids.add(anchor_id)
            points.append(point)
        if any(start == end for start, end in zip(points, points[1:])):
            raise SplitDerivationError(
                f"Layer {layer_id} {side} split guide has a zero-length segment"
            )
        if len({tuple(point) for point in points}) != len(points):
            raise SplitDerivationError(
                f"Layer {layer_id} {side} split guide has duplicate points"
            )
        points_by_side[side] = points
    left_points = points_by_side["left"]
    right_points = points_by_side["right"]
    if left_points == right_points or left_points == list(reversed(right_points)):
        raise SplitDerivationError(f"Layer {layer_id} split side guides are identical")
    if (
        config.get("tie_break") != SPLIT_TIE_BREAK
        or config.get("exact_partition") is not True
    ):
        raise SplitDerivationError(f"Layer {layer_id} split partition declaration is invalid")


def _anchor(layer_id: str, side: str, value: Any) -> tuple[str, list[float]]:
    if not isinstance(value, Mapping):
        raise SplitDerivationError(f"Layer {layer_id} {side} split anchor is invalid")
    kind = value.get("kind")
    if kind == "resolved_joint":
        required = {"kind", "joint_id", "xy", "review_state"}
        if set(value) != required:
            raise SplitDerivationError(
                f"Layer {layer_id} {side} resolved joint anchor fields are invalid"
            )
        anchor_id = value.get("joint_id")
        if value.get("review_state") not in _REVIEW_STATES:
            raise SplitDerivationError(
                f"Layer {layer_id} {side} joint review state is invalid"
            )
        side_ids = (anchor_id,)
    elif kind == "manual_proxy":
        required = {"kind", "proxy_id", "xy", "label", "reason"}
        allowed = required | {"proxy_for_joint_id"}
        if not required.issubset(value) or not set(value).issubset(allowed):
            raise SplitDerivationError(
                f"Layer {layer_id} {side} manual proxy anchor fields are invalid"
            )
        anchor_id = value.get("proxy_id")
        if any(
            not isinstance(value.get(field), str) or not value[field].strip()
            for field in ("label", "reason")
        ):
            raise SplitDerivationError(
                f"Layer {layer_id} {side} manual proxy description is empty"
            )
        proxy_for = value.get("proxy_for_joint_id")
        if "proxy_for_joint_id" in value and not _safe_id(proxy_for):
            raise SplitDerivationError(
                f"Layer {layer_id} {side} manual proxy joint reference is invalid"
            )
        side_ids = (anchor_id, proxy_for)
    else:
        raise SplitDerivationError(
            f"Layer {layer_id} {side} split anchor kind is unsupported"
        )
    if not _safe_id(anchor_id):
        raise SplitDerivationError(f"Layer {layer_id} {side} split anchor id is invalid")
    for side_id in side_ids:
        if side_id is None:
            continue
        if not _safe_id(side_id):
            raise SplitDerivationError(
                f"Layer {layer_id} {side} split anchor reference is invalid"
            )
        inferred = _infer_side(side_id)
        if inferred is not None and inferred != side:
            raise SplitDerivationError(
                f"Layer {layer_id} {side} split anchor has mismatched side: {side_id}"
            )
    point = value.get("xy")
    _point(point, f"Layer {layer_id} {side} split anchor point")
    return str(anchor_id), list(point)


def _infer_side(value: str) -> str | None:
    tokens = set(_ID_TOKENS.split(value.lower()))
    sides = tokens & {"left", "right"}
    return next(iter(sides)) if len(sides) == 1 else None


def _point(value: Any, label: str, *, integer: bool = False) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise SplitDerivationError(f"{label} must be a point")
    for coordinate in value:
        if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
            raise SplitDerivationError(f"{label} must be numeric")
        if not math.isfinite(float(coordinate)) or (integer and not isinstance(coordinate, int)):
            raise SplitDerivationError(f"{label} is invalid")


def _safe_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_SAFE_ID.fullmatch(value))


def _sha(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))
