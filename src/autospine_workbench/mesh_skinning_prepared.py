"""Prepared deterministic LBS with reusable rig, pose, and binding stages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any

from .mesh_skinning import MeshSkinningError
from .mesh_skinning_prepared_core import (
    Bone,
    Matrix,
    Point,
    apply,
    bones,
    compose,
    finite_matrix,
    influences,
    inverse,
    matrix,
    pose_deltas,
    quantize,
    sequence,
    topological_ids,
    vertices,
)


@dataclass(frozen=True, slots=True)
class PreparedSkinningRig:
    """Validated setup hierarchy with cached inverse world matrices."""

    _bones: tuple[Bone, ...]
    _order: tuple[str, ...]
    _bone_index: Mapping[str, int]
    _setup_inverse: tuple[Matrix, ...]

    @property
    def bone_ids(self) -> tuple[str, ...]:
        return tuple(bone.identifier for bone in self._bones)


@dataclass(frozen=True, slots=True)
class PreparedSkinningBinding:
    """Validated bind vertices and bone-indexed one/two-weight influences."""

    _rig: PreparedSkinningRig
    _vertices: tuple[Point, ...]
    _influences: tuple[tuple[tuple[int, float], ...], ...]

    @property
    def vertex_count(self) -> int:
        return len(self._vertices)


@dataclass(frozen=True, slots=True)
class PreparedSkinningPose:
    """One finite pose evaluated into cached per-bone skin matrices."""

    _rig: PreparedSkinningRig
    _skin_matrices: tuple[Matrix, ...]


def prepare_skinning_rig(
    rig_bones: Sequence[Mapping[str, Any]],
) -> PreparedSkinningRig:
    """Validate setup bones and cache topology plus setup inverses once."""

    normalized = bones(rig_bones)
    index = {
        bone.identifier: position
        for position, bone in enumerate(normalized)
    }
    parents = {bone.identifier: bone.parent for bone in normalized}
    order = topological_ids(parents)
    setup_world: dict[str, Matrix] = {}
    for bone_id in order:
        bone = normalized[index[bone_id]]
        value = matrix(bone, 0.0)
        if bone.parent is not None:
            value = compose(setup_world[bone.parent], value)
        setup_world[bone_id] = finite_matrix(value, bone_id, "setup")
    inverses = tuple(
        inverse(setup_world[bone.identifier], bone.identifier)
        for bone in normalized
    )
    return PreparedSkinningRig(
        normalized, order, MappingProxyType(index), inverses
    )


def prepare_skinning_binding(
    rig: PreparedSkinningRig,
    vertices_xy: Sequence[Sequence[int | float]],
    weights: Sequence[Sequence[Mapping[str, Any]]],
) -> PreparedSkinningBinding:
    """Validate bind geometry once and replace bone ids with stable indices."""

    _require_rig(rig)
    normalized = vertices(vertices_xy)
    if not sequence(weights) or len(weights) != len(normalized):
        raise MeshSkinningError("weights must match the vertex count")
    bound = tuple(
        influences(weights[index], rig, index)
        for index in range(len(normalized))
    )
    return PreparedSkinningBinding(rig, normalized, bound)


def evaluate_skinning_pose(
    rig: PreparedSkinningRig,
    pose_rotation_deltas_deg: Mapping[str, int | float],
) -> PreparedSkinningPose:
    """Evaluate one setup-local rotation-delta pose for a prepared rig."""

    _require_rig(rig)
    deltas = pose_deltas(pose_rotation_deltas_deg, rig)
    world: dict[str, Matrix] = {}
    for bone_id in rig._order:
        bone = rig._bones[rig._bone_index[bone_id]]
        value = matrix(bone, deltas.get(bone_id, 0.0))
        if bone.parent is not None:
            value = compose(world[bone.parent], value)
        world[bone_id] = finite_matrix(value, bone_id, "pose")
    matrices = tuple(
        finite_matrix(
            compose(world[bone.identifier], rig._setup_inverse[index]),
            bone.identifier,
            "skinning",
        )
        for index, bone in enumerate(rig._bones)
    )
    return PreparedSkinningPose(rig, matrices)


def skin_prepared_vertices(
    pose: PreparedSkinningPose,
    binding: PreparedSkinningBinding,
) -> tuple[Point, ...]:
    """Skin one prepared binding with a pose from the exact same rig."""

    if type(pose) is not PreparedSkinningPose:
        raise MeshSkinningError("pose must be an exact PreparedSkinningPose")
    if type(binding) is not PreparedSkinningBinding:
        raise MeshSkinningError(
            "binding must be an exact PreparedSkinningBinding"
        )
    if pose._rig is not binding._rig:
        raise MeshSkinningError("prepared pose and binding use different rigs")
    result: list[Point] = []
    for index, bind in enumerate(binding._vertices):
        x, y = 0.0, 0.0
        for bone_index, weight in binding._influences[index]:
            posed = apply(pose._skin_matrices[bone_index], bind)
            x += weight * posed[0]
            y += weight * posed[1]
        if not math.isfinite(x) or not math.isfinite(y):
            raise MeshSkinningError(
                f"vertex {index} produced a non-finite result"
            )
        result.append((quantize(x), quantize(y)))
    return tuple(result)


def _require_rig(value: Any) -> PreparedSkinningRig:
    if type(value) is not PreparedSkinningRig:
        raise MeshSkinningError("rig must be an exact PreparedSkinningRig")
    return value
