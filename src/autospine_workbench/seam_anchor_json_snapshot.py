"""Bounded canonical JSON snapshots for static seam-anchor inputs."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from . import seam_anchor_profile as profile


_MANIFEST_FIELDS = {
    "format", "format_version", "project_id", "revision", "source",
    "layers", "qa",
}


class SeamAnchorJsonSnapshotError(ValueError):
    """Raised before an excessive or non-JSON manifest is materialized."""


def snapshot_layer_manifest(
    value: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    """Copy one exact manifest without unbounded traversal or encoding."""

    if not isinstance(value, Mapping):
        raise SeamAnchorJsonSnapshotError("Layer Manifest must be an object")
    if len(value) > len(_MANIFEST_FIELDS):
        raise SeamAnchorJsonSnapshotError(
            "Layer Manifest root resource limit exceeded"
        )
    root = _bounded_root_copy(value)
    if set(root) != _MANIFEST_FIELDS:
        raise SeamAnchorJsonSnapshotError(
            "Layer Manifest fields are unsupported"
        )
    layers = root.get("layers")
    if type(layers) is not list:
        raise SeamAnchorJsonSnapshotError(
            "Layer Manifest layers must be an array"
        )
    if len(layers) > profile.MAX_MANIFEST_LAYERS:
        raise SeamAnchorJsonSnapshotError(
            "Layer Manifest layer inventory resource limit exceeded"
        )
    _bounded_json_preflight(root)
    text = _bounded_canonical_json(root)
    return json.loads(text), text


def _bounded_root_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    iterator = iter(value)
    for _ in range(len(_MANIFEST_FIELDS) + 1):
        try:
            key = next(iterator)
        except StopIteration:
            break
        if not isinstance(key, str):
            raise SeamAnchorJsonSnapshotError(
                "Layer Manifest keys must be strings"
            )
        if key in result:
            raise SeamAnchorJsonSnapshotError(
                "Layer Manifest keys are duplicated"
            )
        result[key] = value[key]
    else:
        raise SeamAnchorJsonSnapshotError(
            "Layer Manifest root resource limit exceeded"
        )
    return result


def _bounded_json_preflight(root: dict[str, Any]) -> None:
    maximum = profile.MAX_JSON_PREFLIGHT_NODES
    max_depth = profile.MAX_JSON_PREFLIGHT_DEPTH
    max_chars = profile.MAX_LAYER_MANIFEST_BYTES
    nodes = chars = 0
    stack: list[tuple[Any, int]] = [(root, 0)]
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > maximum or depth > max_depth:
            raise SeamAnchorJsonSnapshotError(
                "Layer Manifest JSON resource limit exceeded"
            )
        if isinstance(value, str):
            chars += len(value)
            if chars > max_chars:
                raise SeamAnchorJsonSnapshotError(
                    "Layer Manifest JSON resource limit exceeded"
                )
        elif type(value) is dict:
            remaining = maximum - nodes - len(stack)
            if 2 * len(value) > remaining:
                raise SeamAnchorJsonSnapshotError(
                    "Layer Manifest JSON resource limit exceeded"
                )
            items = _bounded_mapping_items(value)
            for key, item in reversed(items):
                stack.append((item, depth + 1))
                stack.append((key, depth + 1))
        elif type(value) is list:
            remaining = maximum - nodes - len(stack)
            if len(value) > remaining:
                raise SeamAnchorJsonSnapshotError(
                    "Layer Manifest JSON resource limit exceeded"
                )
            for item in reversed(value):
                stack.append((item, depth + 1))
        elif value is not None and type(value) not in {bool, int, float}:
            raise SeamAnchorJsonSnapshotError(
                "Layer Manifest contains a non-JSON value"
            )


def _bounded_mapping_items(
    value: dict[Any, Any],
) -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    for key, item in value.items():
        if not isinstance(key, str):
            raise SeamAnchorJsonSnapshotError(
                "Layer Manifest keys must be strings"
            )
        items.append((key, item))
    return items


def _bounded_canonical_json(value: dict[str, Any]) -> str:
    encoder = json.JSONEncoder(
        ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    )
    chunks: list[str] = []
    byte_count = 0
    for chunk in encoder.iterencode(value):
        byte_count += len(chunk.encode("utf-8"))
        if byte_count > profile.MAX_LAYER_MANIFEST_BYTES:
            raise SeamAnchorJsonSnapshotError(
                "Layer Manifest resource limit exceeded"
            )
        chunks.append(chunk)
    return "".join(chunks)
