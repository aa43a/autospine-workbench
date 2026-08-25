"""Map reviewed layer semantics to the canonical humanoid-v1 bone ids."""

from __future__ import annotations


_SIDES = frozenset({"left", "right"})


def region_bone_for_role(role: str, side: str) -> str | None:
    """Return one unambiguous region attachment bone, or ``None`` for review."""

    role = str(role or "")
    side = str(side or "unknown")
    suffix = f".{side}" if side in _SIDES else None
    if role.startswith("face") or role.startswith("hair"):
        return "neck-head"
    if role.startswith("accessory.head"):
        return "neck-head"
    if role == "body.neck":
        return "chest-neck"
    if role == "body.torso":
        return "spine-chest"
    if role == "body.pelvis":
        return "pelvis-spine"
    if role.startswith("body.arm"):
        if suffix is None:
            return None
        return f"forearm{suffix}" if role.endswith(".lower") else f"upper-arm{suffix}"
    if role == "body.hand":
        return f"forearm{suffix}" if suffix else None
    if role.startswith("body.leg"):
        if suffix is None:
            return None
        return f"calf{suffix}" if role.endswith(".lower") else f"thigh{suffix}"
    if role == "body.foot":
        return f"calf{suffix}" if suffix else None
    if role.startswith("accessory"):
        return "root-pelvis"
    return None
