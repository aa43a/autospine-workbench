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
    normalize_body_sway_pose_sample,
    number,
    point,
)
from .body_sway_probe_geometry_context import (
    PreparedBodySwayGeometryContext,
    PreparedBodySwayMesh,
    PreparedBodySwayRegion,
    prepare_body_sway_geometry_context,
)
from .body_sway_probe_deformation import (
    assess_prepared_body_sway_deformation,
)
from .body_sway_probe_math import BodySwayPoseSample
from .mesh_deformation_metrics import DeformationAssessment
from .mesh_skinning_prepared import (
    evaluate_skinning_pose,
    skin_prepared_vertices,
)
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

    context = prepare_body_sway_geometry_context(rig, target_profile)
    return evaluate_prepared_body_sway_geometry_sample(context, sample)


def evaluate_prepared_body_sway_geometry_sample(
    context: PreparedBodySwayGeometryContext,
    sample: BodySwayPoseSample,
) -> BodySwayGeometrySample:
    """Evaluate one sample while reusing exact immutable setup admission."""

    try:
        if type(context) is not PreparedBodySwayGeometryContext:
            raise BodySwayProbeGeometryError(
                "Prepared body-sway geometry context is invalid"
            )
        admitted_rotations, translation = normalize_body_sway_pose_sample(
            sample, context.bone_ids
        )
        rotations = dict(admitted_rotations)
        skinning_pose = evaluate_skinning_pose(
            context.skinning_rig, rotations
        )
        world = _world_geometry(context.bones, rotations, translation)
        results, failures = [], []
        for attachment in context.attachments:
            if type(attachment) not in {
                PreparedBodySwayMesh, PreparedBodySwayRegion,
            }:
                raise BodySwayProbeGeometryError(
                    "Prepared body-sway attachment is invalid"
                )
            posed = skin_prepared_vertices(
                skinning_pose, attachment.binding
            )
            posed = _translate(posed, translation)
            if type(attachment) is PreparedBodySwayMesh:
                topology = "passed"
                assessment = assess_prepared_body_sway_deformation(
                    attachment.deformation, posed
                )
            elif type(attachment) is PreparedBodySwayRegion:
                topology, assessment = "not_applicable", None
            outside = _outside(
                attachment.attachment_id, posed, context.canvas_size
            )
            failures.extend(outside)
            results.append(BodySwayAttachmentGeometry(
                attachment_id=attachment.attachment_id,
                attachment_type=attachment.attachment_type,
                slot_id=attachment.slot_id,
                slot_bone_id=attachment.slot_bone_id,
                setup_vertices_xy=attachment.setup_vertices_xy,
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
