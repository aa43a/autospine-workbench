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
CANONICAL_IK_HANDLES = (
    "arm.left", "arm.right", "leg.left", "leg.right",
)
CONTACT_LIMBS = frozenset(CANONICAL_IK_HANDLES)
