"""Strict prepared-input validation for dynamic seam interval geometry."""

from __future__ import annotations

from fractions import Fraction

from .body_sway_dynamic_seam_locator import (
    PreparedBodySwayDynamicSeamLocator,
    PreparedBodySwayDynamicSeamLocatorSet,
    PreparedBodySwayDynamicSeamPair,
    PreparedBodySwayDynamicSeamRelationship,
    resolve_prepared_dynamic_seam_setup_exact,
)
from .body_sway_dynamic_seam_moments import (
    prepare_dynamic_seam_moments,
)
from .body_sway_interval_arithmetic import OutwardInterval
from .body_sway_interval_pose import PreparedBodySwayIntervalPose
from .mesh_skinning_prepared import PreparedSkinningRig
from .reviewed_seam_anchor_set_profile import RELATIONSHIP_IDS


_Q4096_HALF_STEP_EXACT = Fraction(1, 8192)


def require_dynamic_seam_interval_inputs(locator_set, pose):
    """Require one exact-rig pose and the complete canonical review inventory."""

    if type(locator_set) is not PreparedBodySwayDynamicSeamLocatorSet \
            or type(pose) is not PreparedBodySwayIntervalPose \
            or type(pose._rig) is not PreparedSkinningRig \
            or locator_set._rig is not pose._rig:
        raise ValueError(
            "Dynamic seam locator set and interval pose are cross-wired"
        )
    rig = pose._rig
    pose_intervals = _require_pose(pose, rig)
    relationships = locator_set.relationships
    if type(relationships) is not tuple \
            or len(relationships) != len(RELATIONSHIP_IDS) \
            or tuple(row.relationship_id for row in relationships) \
                != RELATIONSHIP_IDS:
        raise ValueError(
            "Dynamic seam relationships differ from canonical order"
        )
    for relationship in relationships:
        _require_relationship(relationship)
    return rig, any(not value.finite for value in pose_intervals)


def require_dynamic_seam_locator(locator, rig):
    """Recompute retained moments and bind every bone index to the exact rig."""

    if type(locator) is not PreparedBodySwayDynamicSeamLocator:
        raise ValueError("Prepared dynamic seam locator is invalid")
    rebuilt = prepare_dynamic_seam_moments(locator.vertices)
    dynamic_setup = resolve_prepared_dynamic_seam_setup_exact(locator)
    if rebuilt != locator.moments \
            or locator.attachment_type not in {"region", "mesh"}:
        raise ValueError("Prepared dynamic seam locator moments differ")
    if locator.attachment_type == "region":
        setup_matches = dynamic_setup == locator.setup_canvas_xy
    else:
        setup_matches = all(
            abs(dynamic - static) <= _Q4096_HALF_STEP_EXACT
            for dynamic, static in zip(
                dynamic_setup, locator.setup_canvas_xy, strict=True
            )
        )
    if not setup_matches:
        raise ValueError("Prepared dynamic seam locator setup differs")
    for moment in rebuilt:
        if not 0 <= moment.bone_index < len(rig._bones) \
                or rig._bones[moment.bone_index].identifier != moment.bone_id:
            raise ValueError("Dynamic seam moment bone is cross-wired")
    return rebuilt


def _require_pose(pose, rig):
    rotations = pose.rotation_deltas_deg
    if type(rotations) is not tuple or len(rotations) != len(rig._bones) \
            or any(
                type(row) is not tuple or len(row) != 2
                for row in rotations
            ) \
            or tuple(row[0] for row in rotations) != rig.bone_ids \
            or any(type(row[1]) is not OutwardInterval for row in rotations):
        raise ValueError("Prepared body-sway interval rotations are invalid")
    root = pose.root_translation_xy
    if type(root) is not tuple or len(root) != 2 \
            or any(type(value) is not OutwardInterval or not value.finite
                   for value in root):
        raise ValueError(
            "Prepared body-sway interval root translation is invalid"
        )
    matrices = pose.skin_matrices
    if type(matrices) is not tuple or len(matrices) != len(rig._bones):
        raise ValueError("Prepared body-sway interval matrices are invalid")
    intervals = tuple(row[1] for row in rotations)
    for matrix in matrices:
        if type(matrix) is not tuple or len(matrix) != 6 \
                or any(type(value) is not OutwardInterval for value in matrix):
            raise ValueError("Prepared body-sway interval matrices are invalid")
        intervals += matrix
    return intervals


def _require_relationship(relationship):
    if type(relationship) is not PreparedBodySwayDynamicSeamRelationship \
            or type(relationship.anchors) is not tuple \
            or not 2 <= len(relationship.anchors) <= 8:
        raise ValueError("Dynamic seam relationship is invalid")
    for index, pair in enumerate(relationship.anchors):
        if type(pair) is not PreparedBodySwayDynamicSeamPair \
                or pair.pair_id != f"anchor.{index:03d}":
            raise ValueError(
                "Dynamic seam pair ids differ from canonical order"
            )
