"""Strict logical-root profiles for BVH motion compilation."""

from __future__ import annotations

from dataclasses import dataclass

from .bvh_parser import BvhDocument


SINGLE_ROOT_PROFILE = "single-root-v1"
ZERO_WRAPPER_PROFILE = "zero-wrapper-logical-root-v1"
ROOT_PROFILE = "single-root-or-zero-wrapper-logical-root-v1"
_POSITIONS = frozenset(("Xposition", "Yposition", "Zposition"))
_ROTATIONS = frozenset(("Xrotation", "Yrotation", "Zrotation"))
_SIX_DOF = _POSITIONS | _ROTATIONS


class BvhMotionRootError(ValueError):
    """Raised when the declared motion root is not an admitted BVH profile."""


@dataclass(frozen=True, slots=True)
class BvhMotionRoot:
    """Resolved logical motion root and the exact admitted hierarchy profile."""

    joint_index: int
    wrapper_index: int | None
    profile: str


def require_bvh_motion_root(
    bvh: BvhDocument, declared_joint_name: str
) -> BvhMotionRoot:
    """Resolve a standard root or one zero-valued Kimodo-style wrapper."""

    if type(bvh) is not BvhDocument or not bvh.joints:
        raise BvhMotionRootError("BVH motion root requires a parsed hierarchy")
    names = [joint.name for joint in bvh.joints]
    if declared_joint_name not in names:
        raise BvhMotionRootError("Declared BVH motion root does not exist")
    index = names.index(declared_joint_name)
    if index == 0:
        _require_channel_inventory(bvh, {0})
        return BvhMotionRoot(0, None, SINGLE_ROOT_PROFILE)
    if index != 1 or bvh.joints[index].parent_index != 0:
        raise BvhMotionRootError(
            "Declared BVH motion root is neither ROOT nor its direct logical child"
        )
    _require_zero_wrapper(bvh, index)
    _require_channel_inventory(bvh, {0, index})
    return BvhMotionRoot(index, 0, ZERO_WRAPPER_PROFILE)


def _require_channel_inventory(bvh: BvhDocument, six_dof: set[int]) -> None:
    for index, joint in enumerate(bvh.joints):
        expected = _SIX_DOF if index in six_dof else _ROTATIONS
        if len(joint.channels) != len(expected) or set(joint.channels) != expected:
            raise BvhMotionRootError(
                "BVH joint channel inventory differs from the logical-root profile"
            )


def _require_zero_wrapper(bvh: BvhDocument, logical_root: int) -> None:
    wrapper = bvh.joints[0]
    children = [
        index for index, joint in enumerate(bvh.joints)
        if joint.parent_index == 0
    ]
    if children != [logical_root] or wrapper.offset != (0.0, 0.0, 0.0) \
            or wrapper.end_site_offset is not None:
        raise BvhMotionRootError(
            "Logical-root BVH requires one empty zero-offset wrapper"
        )
    wrapper_width = len(wrapper.channels)
    if any(any(value != 0.0 for value in frame[:wrapper_width])
           for frame in bvh.frames):
        raise BvhMotionRootError(
            "Logical-root BVH wrapper channels must be exactly zero in every frame"
        )
