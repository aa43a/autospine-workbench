"""Deterministic two-bone linear-blend skinning in canvas coordinates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeAlias


QUANTIZATION_PER_PIXEL = 4096
Point: TypeAlias = tuple[float, float]


class MeshSkinningError(ValueError):
    """Raised when a rig, pose, vertex, or influence cannot be skinned safely."""


def skin_vertices_lbs(
    rig_bones: Sequence[Mapping[str, Any]],
    vertices_xy: Sequence[Sequence[int | float]],
    weights: Sequence[Sequence[Mapping[str, Any]]],
    pose_rotation_deltas_deg: Mapping[str, int | float],
) -> tuple[Point, ...]:
    """Skin canvas-space bind vertices with one or two positive influences.

    This compatibility entry point delegates the sole numerical implementation
    to the prepared API. Results retain 1/4096 px decimal ROUND_HALF_UP.
    """

    from .mesh_skinning_prepared import (
        evaluate_skinning_pose,
        prepare_skinning_binding,
        prepare_skinning_rig,
        skin_prepared_vertices,
    )

    rig = prepare_skinning_rig(rig_bones)
    pose = evaluate_skinning_pose(rig, pose_rotation_deltas_deg)
    binding = prepare_skinning_binding(rig, vertices_xy, weights)
    return skin_prepared_vertices(pose, binding)
