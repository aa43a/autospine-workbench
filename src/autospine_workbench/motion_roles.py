"""Single source of truth for target-independent humanoid-v1 motion roles."""

from __future__ import annotations

from types import MappingProxyType


CANONICAL_BONE_ROLE_ITEMS = (
    ("humanoid.root", "root-pelvis"),
    ("humanoid.spine.lower", "pelvis-spine"),
    ("humanoid.spine.upper", "spine-chest"),
    ("humanoid.neck", "chest-neck"),
    ("humanoid.head", "neck-head"),
    ("humanoid.clavicle.left", "chest-shoulder.left"),
    ("humanoid.arm.upper.left", "upper-arm.left"),
    ("humanoid.arm.lower.left", "forearm.left"),
    ("humanoid.hip.left", "pelvis-hip.left"),
    ("humanoid.leg.upper.left", "thigh.left"),
    ("humanoid.leg.lower.left", "calf.left"),
    ("humanoid.clavicle.right", "chest-shoulder.right"),
    ("humanoid.arm.upper.right", "upper-arm.right"),
    ("humanoid.arm.lower.right", "forearm.right"),
    ("humanoid.hip.right", "pelvis-hip.right"),
    ("humanoid.leg.upper.right", "thigh.right"),
    ("humanoid.leg.lower.right", "calf.right"),
)

CANONICAL_BONE_ID_BY_ROLE = MappingProxyType(dict(CANONICAL_BONE_ROLE_ITEMS))
CANONICAL_BONE_ROLE_BY_ID = MappingProxyType({
    bone_id: role for role, bone_id in CANONICAL_BONE_ROLE_ITEMS
})
CANONICAL_BONE_ROLES = frozenset(CANONICAL_BONE_ID_BY_ROLE)
_CANONICAL_PARENT_INDEX = (
    None, 0, 1, 2, 3, 2, 5, 6, 0, 8, 9, 2, 11, 12, 0, 14, 15,
)
CANONICAL_PARENT_ROLE_BY_ROLE = MappingProxyType({
    role: (
        None if parent is None else CANONICAL_BONE_ROLE_ITEMS[parent][0]
    )
    for (role, _bone_id), parent in zip(
        CANONICAL_BONE_ROLE_ITEMS, _CANONICAL_PARENT_INDEX
    )
})
CANONICAL_IK_HANDLES = (
    "arm.left", "arm.right", "leg.left", "leg.right",
)
IK_BONE_ROLES_BY_HANDLE = MappingProxyType({
    "arm.left": ("humanoid.arm.upper.left", "humanoid.arm.lower.left"),
    "arm.right": ("humanoid.arm.upper.right", "humanoid.arm.lower.right"),
    "leg.left": ("humanoid.leg.upper.left", "humanoid.leg.lower.left"),
    "leg.right": ("humanoid.leg.upper.right", "humanoid.leg.lower.right"),
})
CONTACT_LIMBS = frozenset(CANONICAL_IK_HANDLES)


def nearest_mapped_parent_role(role: str, mapped_roles) -> str | None:
    """Return the nearest explicit canonical ancestor, collapsing omitted roles."""

    parent = CANONICAL_PARENT_ROLE_BY_ROLE.get(role)
    while parent is not None and parent not in mapped_roles:
        parent = CANONICAL_PARENT_ROLE_BY_ROLE[parent]
    return parent
