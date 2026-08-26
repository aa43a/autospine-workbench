"""One-sample structural geometry for reviewed P10.2 body sway.

The result proves sampled FK, indexed geometry, containment, and deformation
only. A shared posed vertex array is not seam, raster, visual, continuous-time,
or safety evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, TypeAlias

from .body_sway_probe_geometry_inputs import (
    BodySwayProbeGeometryError,
    normalize_body_sway_geometry_input,
    number,
    point,
    points,
)
from .body_sway_probe_math import BodySwayPoseSample
from .body_sway_probe_profile import (
    MAX_AREA_RATIO,
    MAX_EDGE_STRETCH,
    MIN_AREA_RATIO,
)
from .mesh_action_probe_inputs import normalize_probe_input
from .mesh_deformation_metrics import DeformationAssessment, measure_deformation
from .mesh_rig_profile import RIG_TRIANGLE_LIMIT, RIG_VERTEX_LIMIT
from .mesh_skinning import skin_vertices_lbs
from .rig_fk import evaluate_world_setup


Point: TypeAlias = tuple[float, float]


@dataclass(frozen=True, slots=True)
class BodySwayBoneGeometry:
    bone_id: str
    origin_xy: Point
    rotation_deg: float
    endpoint_xy: Point


@dataclass(frozen=True, slots=True)
class BodySwayCanvasFailure:
    attachment_id: str
    vertex_index: int
    point_xy: Point
    sides: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BodySwayAttachmentGeometry:
    attachment_id: str
    attachment_type: str
    slot_id: str
    slot_bone_id: str
    setup_vertices_xy: tuple[Point, ...]
    posed_vertices_xy: tuple[Point, ...]
    canvas_status: str
    outside_vertex_indices: tuple[int, ...]
    shared_index_topology_status: str
    deformation: DeformationAssessment | None


@dataclass(frozen=True, slots=True)
class BodySwayGeometrySample:
    """Frozen, detached structural result for one exact sampled pose."""

    tick: int
    status: str
    fk_status: str
    bones: tuple[BodySwayBoneGeometry, ...]
    attachments: tuple[BodySwayAttachmentGeometry, ...]
    canvas_failures: tuple[BodySwayCanvasFailure, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_body_sway_geometry_sample(
    rig: Mapping[str, Any],
    target_profile: Mapping[str, Any],
    sample: BodySwayPoseSample,
) -> BodySwayGeometrySample:
    """Pose every setup attachment and return sampled structural evidence."""

    try:
        admitted = normalize_body_sway_geometry_input(
            rig, target_profile, sample
        )
        rotations = dict(admitted.rotations)
        slots, targets = dict(admitted.slots), dict(admitted.mesh_targets)
        world = _world_geometry(
            admitted.bones, rotations, admitted.root_translation_xy
        )
        results, failures = [], []
        mesh_vertices = mesh_triangles = 0
        for attachment in sorted(admitted.attachments,
                                 key=lambda row: row["id"]):
            slot_id = attachment["slot"]
            slot_bone = slots[slot_id]
            if attachment["type"] == "region":
                setup, posed, topology, assessment = _region(
                    admitted.bones, attachment, slot_bone, rotations,
                    admitted.root_translation_xy,
                )
            else:
                setup, posed, topology, assessment, counts = _mesh(
                    admitted.bones, attachment, targets[attachment["id"]],
                    rotations, admitted.root_translation_xy,
                )
                mesh_vertices += counts[0]
                mesh_triangles += counts[1]
                if mesh_vertices > RIG_VERTEX_LIMIT \
                        or mesh_triangles > RIG_TRIANGLE_LIMIT:
                    raise BodySwayProbeGeometryError(
                        "Body-sway mesh geometry exceeds resource limits"
                    )
            outside = _outside(
                attachment["id"], posed, admitted.canvas_size
            )
            failures.extend(outside)
            results.append(BodySwayAttachmentGeometry(
                attachment_id=attachment["id"],
                attachment_type=attachment["type"],
                slot_id=slot_id,
                slot_bone_id=slot_bone,
                setup_vertices_xy=setup,
                posed_vertices_xy=posed,
                canvas_status="rejected" if outside else "passed",
                outside_vertex_indices=tuple(
                    item.vertex_index for item in outside
                ),
                shared_index_topology_status=topology,
                deformation=assessment,
            ))
        rejected = bool(failures) or any(
            item.deformation is not None
            and item.deformation.status == "rejected"
            for item in results
        )
        return BodySwayGeometrySample(
            tick=sample.tick,
            status="rejected" if rejected else "passed",
            fk_status="passed",
            bones=world,
            attachments=tuple(results),
            canvas_failures=tuple(failures),
        )
    except BodySwayProbeGeometryError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise BodySwayProbeGeometryError(
            f"Body-sway structural geometry failed: {exc}"
        ) from exc


def _world_geometry(bones, rotations, translation):
    posed = []
    for bone in bones:
        setup = dict(bone["setup"])
        setup["rotation_deg"] = number(
            setup["rotation_deg"], "setup rotation"
        ) + rotations.get(bone["id"], 0.0)
        if bone["id"] == "root-pelvis":
            setup["x"] = number(setup["x"], "root x") + translation[0]
            setup["y"] = number(setup["y"], "root y") + translation[1]
        posed.append({
            "id": bone["id"], "parent": bone.get("parent"), "setup": setup,
        })
    world = evaluate_world_setup(posed)
    return tuple(
        BodySwayBoneGeometry(
            bone_id,
            point(world[bone_id]["origin_xy"], f"bone {bone_id} origin"),
            number(world[bone_id]["rotation_deg"], f"bone {bone_id} rotation"),
            point(world[bone_id]["endpoint_xy"], f"bone {bone_id} endpoint"),
        )
        for bone_id in sorted(world)
    )


def _region(bones, attachment, slot_bone, rotations, translation):
    x, y = point(attachment.get("canvas_offset_xy"), "region offset")
    width, height = point(attachment.get("size"), "region size")
    if width <= 0.0 or height <= 0.0:
        raise BodySwayProbeGeometryError("Region size must be positive")
    setup = ((x, y), (x + width, y),
             (x + width, y + height), (x, y + height))
    weights = tuple(({"bone": slot_bone, "weight": 1.0},) for _ in setup)
    posed = skin_vertices_lbs(bones, setup, weights, rotations)
    return setup, _translate(posed, translation), "not_applicable", None


def _mesh(bones, attachment, target, rotations, translation):
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
    referenced = {index for triangle in normalized.triangles
                  for index in triangle}
    if referenced != set(range(len(normalized.vertices_xy))):
        raise BodySwayProbeGeometryError(
            "Mesh topology has unreferenced vertices"
        )
    thresholds = {
        "min_area_ratio": MIN_AREA_RATIO,
        "max_area_ratio": MAX_AREA_RATIO,
        "max_edge_stretch": MAX_EDGE_STRETCH,
    }
    setup_assessment = measure_deformation(
        normalized.vertices_xy, normalized.vertices_xy,
        normalized.triangles, **thresholds,
    )
    if setup_assessment.status != "passed":
        raise BodySwayProbeGeometryError("Mesh setup topology is rejected")
    posed = skin_vertices_lbs(
        normalized.rig_bones, normalized.vertices_xy,
        normalized.weights, rotations,
    )
    posed = _translate(posed, translation)
    assessment = measure_deformation(
        normalized.vertices_xy, posed, normalized.triangles, **thresholds,
    )
    return (
        normalized.vertices_xy, posed, "passed", assessment,
        (len(normalized.vertices_xy), len(normalized.triangles)),
    )


def _outside(identifier, vertices, canvas):
    failures = []
    for index, position in enumerate(vertices):
        x, y = position
        sides = tuple(name for name, failed in (
            ("left", x < 0.0), ("right", x > canvas[0]),
            ("top", y < 0.0), ("bottom", y > canvas[1]),
        ) if failed)
        if sides:
            failures.append(
                BodySwayCanvasFailure(identifier, index, position, sides)
            )
    return tuple(failures)


def _translate(vertices, translation):
    return tuple(
        (number(x + translation[0], "posed x"),
         number(y + translation[1], "posed y"))
        for x, y in vertices
    )
