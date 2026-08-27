"""Exact RigIR/prepared-geometry binding for dynamic seam locators."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction
import math
from typing import TypeAlias

from .body_sway_dynamic_seam_moments import FractionPoint
from .body_sway_probe_geometry_context import (
    PreparedBodySwayGeometryContext,
    PreparedBodySwayMesh,
    PreparedBodySwayRegion,
)
from .mesh_skinning_prepared import (
    prepare_skinning_binding,
    prepare_skinning_rig,
)
from .rig_validation import RigSemanticValidator


BoundAttachment: TypeAlias = tuple[
    Mapping[str, object], PreparedBodySwayRegion | PreparedBodySwayMesh,
]


def bind_dynamic_seam_geometry(
    rig: Mapping[str, object], context: PreparedBodySwayGeometryContext,
) -> dict[str, BoundAttachment]:
    """Prove that every prepared attachment is from this exact RigIR."""

    RigSemanticValidator(max_influences=2).raise_for_errors(rig)
    bones = _rows(rig.get("bones"), "bones")
    expected_rig = prepare_skinning_rig(bones)
    if expected_rig != context.skinning_rig:
        raise ValueError("Prepared skinning rig differs from exact RigIR")
    expected_bones = tuple((row["id"], row.get("parent"), tuple(
        row["setup"][field] for field in _BONE_SETUP_FIELDS
    )) for row in bones)
    actual_bones = tuple((row["id"], row.get("parent"), tuple(
        row["setup"][field] for field in _BONE_SETUP_FIELDS
    )) for row in context.bones)
    if actual_bones != expected_bones \
            or context.bone_ids != frozenset(row[0] for row in expected_bones):
        raise ValueError("Prepared bone inventory differs from exact RigIR")
    canvas = rig.get("canvas")
    if not isinstance(canvas, Mapping) or context.canvas_size != (
        float(canvas.get("width")), float(canvas.get("height")),
    ):
        raise ValueError("Prepared canvas differs from exact RigIR")
    slots = {
        row["id"]: row["bone"] for row in _rows(rig.get("slots"), "slots")
    }
    originals = {
        row["id"]: row for row in _rows(rig.get("attachments"), "attachments")
    }
    prepared = {row.attachment_id: row for row in context.attachments}
    if len(originals) != len(prepared) or set(originals) != set(prepared) \
            or tuple(row.attachment_id for row in context.attachments) \
                != tuple(sorted(originals)):
        raise ValueError(
            "Prepared attachment inventory differs from exact RigIR"
        )
    for identifier in sorted(originals):
        _bind_attachment(
            originals[identifier], prepared[identifier], slots, context
        )
    return {
        identifier: (originals[identifier], prepared[identifier])
        for identifier in originals
    }


def fraction_point(value, label: str) -> FractionPoint:
    """Detach one admitted JSON point into its canonical decimal rationals."""

    rows = _sequence(value, label)
    if len(rows) != 2:
        raise ValueError(f"RigIR {label} must be a point")
    result = []
    for item in rows:
        if isinstance(item, bool) or not isinstance(item, (int, float)) \
                or not math.isfinite(item):
            raise ValueError(f"RigIR {label} must contain finite numbers")
        result.append(Fraction(str(item)))
    return result[0], result[1]


def _bind_attachment(original, prepared, slots, context):
    identifier, kind, slot_id = (
        original.get("id"), original.get("type"), original.get("slot")
    )
    if kind == "region" and type(prepared) is not PreparedBodySwayRegion \
            or kind == "mesh" and type(prepared) is not PreparedBodySwayMesh:
        raise ValueError(f"Prepared attachment type differs: {identifier}")
    if kind not in {"region", "mesh"} or slot_id not in slots \
            or prepared.attachment_type != kind \
            or prepared.slot_id != slot_id \
            or prepared.slot_bone_id != slots[slot_id] \
            or prepared.binding._rig is not context.skinning_rig:
        raise ValueError(f"Prepared attachment binding differs: {identifier}")
    offset = _float_point(original.get("canvas_offset_xy"), "canvas offset")
    if kind == "region":
        setup, weights = _region_binding(original, offset, slots[slot_id])
    else:
        setup = _mesh_vertices(original, offset)
        weights = original.get("weights")
        triangles = _triangles(original.get("triangles"), len(setup))
        if prepared.deformation.triangles != triangles \
                or prepared.deformation.setup_vertices_xy != setup:
            raise ValueError(f"Prepared mesh topology differs: {identifier}")
    expected = prepare_skinning_binding(context.skinning_rig, setup, weights)
    if prepared.setup_vertices_xy != setup \
            or prepared.binding._vertices != expected._vertices \
            or prepared.binding._influences != expected._influences:
        raise ValueError(f"Prepared attachment weights differ: {identifier}")


def _region_binding(original, offset, bone_id):
    size = _float_point(original.get("size"), "region size")
    setup = (
        offset, (offset[0] + size[0], offset[1]),
        (offset[0] + size[0], offset[1] + size[1]),
        (offset[0], offset[1] + size[1]),
    )
    weights = tuple(({"bone": bone_id, "weight": 1.0},)
                    for _vertex in setup)
    return setup, weights


def _mesh_vertices(original, offset):
    local = tuple(_float_point(row, "mesh vertex") for row in _sequence(
        original.get("vertices"), "mesh vertices"
    ))
    return tuple((offset[0] + x, offset[1] + y) for x, y in local)


def _rows(value, label):
    if type(value) is not list or any(not isinstance(row, Mapping) for row in value):
        raise ValueError(f"RigIR {label} must be an array")
    return value


def _sequence(value, label):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"RigIR {label} must be an array")
    return value


def _float_point(value, label):
    point = fraction_point(value, label)
    return float(point[0]), float(point[1])


def _triangles(value, vertex_count):
    rows = _sequence(value, "mesh triangles")
    if not rows or len(rows) % 3 or any(
        type(item) is not int or not 0 <= item < vertex_count for item in rows
    ):
        raise ValueError("RigIR mesh triangle topology is invalid")
    return tuple(tuple(rows[index:index + 3])
                 for index in range(0, len(rows), 3))


_BONE_SETUP_FIELDS = (
    "x", "y", "rotation_deg", "scale_x", "scale_y", "length",
)
