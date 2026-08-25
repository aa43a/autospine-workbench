"""Strict input normalization for deterministic mesh action probes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any, TypeAlias


Point: TypeAlias = tuple[float, float]
Triangle: TypeAlias = tuple[int, int, int]
Influence: TypeAlias = dict[str, str | float]


class ActionProbeInputError(ValueError):
    """Raised when a mesh and its designated chain are not probeable."""


@dataclass(frozen=True, slots=True)
class NormalizedProbeInput:
    rig_bones: tuple[Mapping[str, Any], ...]
    vertices_xy: tuple[Point, ...]
    triangles: tuple[Triangle, ...]
    weights: tuple[tuple[Influence, ...], ...]


def normalize_probe_input(
    rig_bones: Sequence[Mapping[str, Any]],
    mesh_attachment: Mapping[str, Any],
    proximal_bone_id: str,
    distal_bone_id: str,
) -> NormalizedProbeInput:
    """Copy a source-local attachment into validated canvas-space probe input."""

    attachment = _mapping(mesh_attachment, "mesh attachment")
    if attachment.get("type") != "mesh":
        raise ActionProbeInputError("action probe requires a mesh attachment")
    indexed, normalized_bones = _bones(rig_bones)
    _chain(indexed, proximal_bone_id, distal_bone_id)
    vertices = _canvas_vertices(
        attachment.get("vertices"), attachment.get("canvas_offset_xy")
    )
    triangles = _triangles(attachment.get("triangles"))
    weights = _weights(
        attachment.get("weights"), len(vertices), proximal_bone_id, distal_bone_id
    )
    return NormalizedProbeInput(normalized_bones, vertices, triangles, weights)


def _bones(value: Any):
    if not _sequence(value) or not value:
        raise ActionProbeInputError("rig bones must be a non-empty array")
    indexed: dict[str, Mapping[str, Any]] = {}
    normalized: list[Mapping[str, Any]] = []
    for index, raw in enumerate(value):
        bone = _mapping(raw, f"bone {index}")
        bone_id = bone.get("id")
        if not isinstance(bone_id, str) or not bone_id or bone_id in indexed:
            raise ActionProbeInputError("rig bone ids must be non-empty and unique")
        indexed[bone_id] = bone
        normalized.append(bone)
    return indexed, tuple(normalized)


def _chain(bones, proximal_id, distal_id) -> None:
    if not isinstance(proximal_id, str) or not isinstance(distal_id, str):
        raise ActionProbeInputError("action probe references an unknown hinge bone")
    if proximal_id not in bones or distal_id not in bones:
        raise ActionProbeInputError("action probe references an unknown hinge bone")
    if proximal_id == distal_id or bones[distal_id].get("parent") != proximal_id:
        raise ActionProbeInputError("distal hinge bone must directly parent to proximal")


def _canvas_vertices(value: Any, offset_value: Any) -> tuple[Point, ...]:
    if not _sequence(value) or not value:
        raise ActionProbeInputError("mesh vertices must be a non-empty array")
    if not _sequence(offset_value) or len(offset_value) != 2:
        raise ActionProbeInputError("mesh canvas offset must contain two finite numbers")
    offset = (_number(offset_value[0]), _number(offset_value[1]))
    result: list[Point] = []
    for index, point in enumerate(value):
        if not _sequence(point) or len(point) != 2:
            raise ActionProbeInputError(
                f"mesh vertex {index} must contain two coordinates"
            )
        result.append(
            (offset[0] + _number(point[0]), offset[1] + _number(point[1]))
        )
    return tuple(result)


def _triangles(value: Any) -> tuple[Triangle, ...]:
    if not _sequence(value) or not value or len(value) % 3:
        raise ActionProbeInputError(
            "mesh triangle index array must be non-empty triples"
        )
    if any(not isinstance(item, int) or isinstance(item, bool) for item in value):
        raise ActionProbeInputError("mesh triangle indices must be integers")
    return tuple(
        (value[index], value[index + 1], value[index + 2])
        for index in range(0, len(value), 3)
    )


def _weights(value, vertex_count, proximal_id, distal_id):
    if not _sequence(value) or len(value) != vertex_count:
        raise ActionProbeInputError("two-bone weights must match the mesh vertices")
    allowed, used = {proximal_id, distal_id}, set()
    result: list[tuple[Influence, ...]] = []
    for vertex, raw_items in enumerate(value):
        if not _sequence(raw_items) or len(raw_items) not in (1, 2):
            raise ActionProbeInputError(
                f"vertex {vertex} must have one or two hinge influences"
            )
        items: list[Influence] = []
        seen: set[str] = set()
        total = 0.0
        for raw in raw_items:
            if not isinstance(raw, Mapping) or set(raw) != {"bone", "weight"}:
                raise ActionProbeInputError("hinge influence fields must be exact")
            bone_id, weight = raw.get("bone"), raw.get("weight")
            if not isinstance(bone_id, str) or bone_id not in allowed:
                raise ActionProbeInputError(
                    "mesh weights must use only the two hinge bones"
                )
            if bone_id in seen:
                raise ActionProbeInputError("vertex hinge bones must be unique")
            numeric = _positive_weight(weight)
            seen.add(bone_id)
            used.add(bone_id)
            total += numeric
            items.append({"bone": bone_id, "weight": numeric})
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ActionProbeInputError("vertex hinge weights must sum to one")
        result.append(tuple(sorted(items, key=lambda item: str(item["bone"]))))
    if used != allowed:
        raise ActionProbeInputError("mesh weights must use both hinge bones")
    return tuple(result)


def _positive_weight(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ActionProbeInputError("hinge weights must be finite and positive")
    try:
        numeric = float(value)
    except OverflowError as exc:
        raise ActionProbeInputError(
            "hinge weights must be finite and positive"
        ) from exc
    if not math.isfinite(numeric) or not 0.0 < numeric <= 1.0:
        raise ActionProbeInputError("hinge weights must be finite and positive")
    return numeric


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ActionProbeInputError(f"{label} must be an object")
    return value


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ActionProbeInputError("mesh coordinates must be finite numbers")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ActionProbeInputError("mesh coordinates must be finite numbers") from exc
    if not math.isfinite(result):
        raise ActionProbeInputError("mesh coordinates must be finite numbers")
    return result


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    )
