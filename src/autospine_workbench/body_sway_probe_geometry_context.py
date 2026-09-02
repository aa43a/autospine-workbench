"""Immutable setup context for repeated body-sway geometry samples."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, TypeAlias

from .body_sway_probe_deformation import (
    PreparedBodySwayDeformation,
    prepare_body_sway_deformation,
)
from .body_sway_probe_geometry_inputs import (
    BodySwayProbeGeometryError,
    normalize_body_sway_static_geometry_input,
    point,
    points,
)
from .body_sway_probe_profile import (
    MAX_AREA_RATIO,
    MAX_EDGE_STRETCH,
    MIN_AREA_RATIO,
)
from .mesh_action_probe_inputs import normalize_probe_input
from .mesh_rig_profile import RIG_TRIANGLE_LIMIT, RIG_VERTEX_LIMIT
from .mesh_skinning_prepared import (
    PreparedSkinningBinding,
    PreparedSkinningRig,
    prepare_skinning_binding,
    prepare_skinning_rig,
)


Point: TypeAlias = tuple[float, float]


@dataclass(frozen=True, slots=True)
class PreparedBodySwayRegion:
    attachment_id: str
    attachment_type: str
    slot_id: str
    slot_bone_id: str
    setup_vertices_xy: tuple[Point, ...]
    binding: PreparedSkinningBinding


@dataclass(frozen=True, slots=True)
class PreparedBodySwayMesh:
    attachment_id: str
    attachment_type: str
    slot_id: str
    slot_bone_id: str
    setup_vertices_xy: tuple[Point, ...]
    binding: PreparedSkinningBinding
    deformation: PreparedBodySwayDeformation


PreparedAttachment: TypeAlias = PreparedBodySwayRegion | PreparedBodySwayMesh


@dataclass(frozen=True, slots=True)
class PreparedBodySwayGeometryContext:
    """Detached, sample-independent RigIR and attachment geometry."""

    bones: tuple[Mapping[str, Any], ...]
    bone_ids: frozenset[str]
    canvas_origin: Point
    canvas_size: Point
    skinning_rig: PreparedSkinningRig
    attachments: tuple[PreparedAttachment, ...]


def prepare_body_sway_geometry_context(
    rig: Mapping[str, Any],
    target_profile: Mapping[str, Any],
) -> PreparedBodySwayGeometryContext:
    """Validate and normalize every sample-independent term exactly once."""

    try:
        admitted = normalize_body_sway_static_geometry_input(
            rig, target_profile
        )
        return _prepare_body_sway_geometry_context(admitted)
    except BodySwayProbeGeometryError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise BodySwayProbeGeometryError(
            f"Body-sway structural geometry failed: {exc}"
        ) from exc


def _prepare_body_sway_geometry_context(
    admitted,
) -> PreparedBodySwayGeometryContext:
    """Build a detached context from already admitted static fields."""

    bones = _freeze_bones(admitted.bones)
    bone_ids = frozenset(row["id"] for row in bones)
    skinning_rig = prepare_skinning_rig(bones)
    slots, targets = dict(admitted.slots), dict(admitted.mesh_targets)
    attachments: list[PreparedAttachment] = []
    mesh_vertices = mesh_triangles = 0
    for attachment in sorted(
        admitted.attachments, key=lambda row: row["id"]
    ):
        slot_id = attachment["slot"]
        slot_bone_id = slots[slot_id]
        if attachment["type"] == "region":
            attachments.append(_prepare_region(
                skinning_rig, attachment, slot_bone_id
            ))
            continue
        prepared, counts = _prepare_mesh(
            skinning_rig, bones, attachment,
            targets[attachment["id"]], slot_bone_id,
        )
        mesh_vertices += counts[0]
        mesh_triangles += counts[1]
        if mesh_vertices > RIG_VERTEX_LIMIT \
                or mesh_triangles > RIG_TRIANGLE_LIMIT:
            raise BodySwayProbeGeometryError(
                "Body-sway mesh geometry exceeds resource limits"
            )
        attachments.append(prepared)
    return PreparedBodySwayGeometryContext(
        bones=bones, bone_ids=bone_ids,
        canvas_origin=(0.0, 0.0),
        canvas_size=admitted.canvas_size,
        skinning_rig=skinning_rig,
        attachments=tuple(attachments),
    )


def prepare_body_sway_geometry_context_for_viewport(
    rig: Mapping[str, Any],
    target_profile: Mapping[str, Any],
    world_viewport: Mapping[str, Any],
) -> PreparedBodySwayGeometryContext:
    """Retain exact geometry while replacing only the reviewed view bounds."""

    context = prepare_body_sway_geometry_context(rig, target_profile)
    fields = {"x", "y", "width", "height"}
    if not isinstance(world_viewport, Mapping) \
            or set(world_viewport) != fields:
        raise BodySwayProbeGeometryError(
            "Body-sway world viewport fields are invalid"
        )
    x, y = point(
        (world_viewport["x"], world_viewport["y"]),
        "world viewport origin",
    )
    width, height = point(
        (world_viewport["width"], world_viewport["height"]),
        "world viewport size",
    )
    if width <= 0.0 or height <= 0.0:
        raise BodySwayProbeGeometryError(
            "Body-sway world viewport size must be positive"
        )
    return PreparedBodySwayGeometryContext(
        bones=context.bones, bone_ids=context.bone_ids,
        canvas_origin=(x, y), canvas_size=(width, height),
        skinning_rig=context.skinning_rig,
        attachments=context.attachments,
    )


def _prepare_region(skinning_rig, attachment, slot_bone_id):
    x, y = point(attachment.get("canvas_offset_xy"), "region offset")
    width, height = point(attachment.get("size"), "region size")
    if width <= 0.0 or height <= 0.0:
        raise BodySwayProbeGeometryError("Region size must be positive")
    setup = (
        (x, y), (x + width, y),
        (x + width, y + height), (x, y + height),
    )
    weights = tuple(
        ({"bone": slot_bone_id, "weight": 1.0},) for _point in setup
    )
    return PreparedBodySwayRegion(
        attachment_id=attachment["id"], attachment_type="region",
        slot_id=attachment["slot"], slot_bone_id=slot_bone_id,
        setup_vertices_xy=setup,
        binding=prepare_skinning_binding(skinning_rig, setup, weights),
    )


def _prepare_mesh(
    skinning_rig, bones, attachment, target, slot_bone_id,
):
    normalized = normalize_probe_input(
        bones, attachment,
        target["proximal_bone_id"], target["distal_bone_id"],
    )
    uvs = points(attachment.get("uvs"), "mesh UVs")
    if len(uvs) != len(normalized.vertices_xy) or any(
        not 0.0 <= value <= 1.0 for pair in uvs for value in pair
    ):
        raise BodySwayProbeGeometryError(
            "Mesh shared-index UV inventory is invalid"
        )
    referenced = {
        index for triangle in normalized.triangles for index in triangle
    }
    if referenced != set(range(len(normalized.vertices_xy))):
        raise BodySwayProbeGeometryError(
            "Mesh topology has unreferenced vertices"
        )
    try:
        deformation = prepare_body_sway_deformation(
            normalized.vertices_xy, normalized.triangles,
            min_area_ratio=MIN_AREA_RATIO,
            max_area_ratio=MAX_AREA_RATIO,
            max_edge_stretch=MAX_EDGE_STRETCH,
        )
    except ValueError as exc:
        if str(exc) == "Mesh setup topology is rejected":
            raise BodySwayProbeGeometryError(str(exc)) from exc
        raise
    return PreparedBodySwayMesh(
        attachment_id=attachment["id"], attachment_type="mesh",
        slot_id=attachment["slot"], slot_bone_id=slot_bone_id,
        setup_vertices_xy=normalized.vertices_xy,
        binding=prepare_skinning_binding(
            skinning_rig, normalized.vertices_xy, normalized.weights
        ),
        deformation=deformation,
    ), (len(normalized.vertices_xy), len(normalized.triangles))


def _freeze_bones(value) -> tuple[Mapping[str, Any], ...]:
    fields = ("x", "y", "rotation_deg", "scale_x", "scale_y", "length")
    return tuple(
        MappingProxyType({
            "id": row["id"], "parent": row.get("parent"),
            "setup": MappingProxyType({
                field: row["setup"][field] for field in fields
            }),
        })
        for row in value
    )
