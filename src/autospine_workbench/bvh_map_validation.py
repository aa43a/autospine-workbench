"""Fail-closed semantics for explicit BVH-to-MotionIR maps."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
import re
from typing import Any

from .bvh_parser import BvhDocument
from .bvh_motion_root import BvhMotionRootError, require_bvh_motion_root
from .motion_roles import (
    CANONICAL_BONE_ROLE_ITEMS,
    nearest_mapped_parent_role,
)


FORMAT = "autospine-bvh-map"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_SOURCE_UNITS = 1_000_000.0
MAX_SPEED_SOURCE_UNITS_PER_SECOND = 1_000_000_000.0
MAX_CONTACT_FRAMES = 20_000
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_AXES = frozenset(("+X", "-X", "+Y", "-Y", "+Z", "-Z"))
_ROLE_ORDER = {role: index for index, (role, _) in enumerate(
    CANONICAL_BONE_ROLE_ITEMS
)}
_TOP = {"format", "format_version", "map_id", "clip", "basis", "root", "bones", "contact"}
_BONE = {"role", "joint_name", "aim", "rotation_policy"}
_CONTACT_ON = {
    "enabled", "feet", "floor_height_source_units",
    "height_threshold_source_units",
    "speed_threshold_source_units_per_second", "minimum_frames",
    "gap_frames", "height_policy", "speed_policy", "mode", "interval",
}


class BvhMapValidationError(ValueError):
    """Raised when a BVH mapping requires guessing or violates its source."""


def bvh_map_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical identity of one fully validated explicit map."""

    require_bvh_map(document)
    encoded = json.dumps(
        dict(document), allow_nan=False, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_bvh_map(
    document: Mapping[str, Any], *, bvh: BvhDocument | None = None
) -> None:
    """Validate one explicit map, optionally against its parsed BVH snapshot."""
    try:
        root = _object(document, "BVH map")
        _exact(root, _TOP, "BVH map")
        _identity(root)
        _clip(root.get("clip"))
        _basis(root.get("basis"))
        root_joint = _root(root.get("root"))
        bones = _bones(root.get("bones"), root_joint)
        contact = _contact(root.get("contact"))
        if bvh is not None:
            _cross_bvh(bvh, root_joint, bones, contact)
        encoded = json.dumps(
            root, allow_nan=False, ensure_ascii=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise BvhMapValidationError("BVH map document byte limit exceeded")
    except BvhMapValidationError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise BvhMapValidationError(f"BVH map validation failed: {exc}") from exc

def _identity(root: dict[str, Any]) -> None:
    if root.get("format") != FORMAT or type(root.get("format_version")) is not int \
            or root.get("format_version") != FORMAT_VERSION:
        raise BvhMapValidationError("BVH map format version is unsupported")
    _safe_id(root.get("map_id"), "map_id")

def _clip(value: Any) -> None:
    clip = _object(value, "BVH map clip")
    _exact(clip, {"clip_id", "loop"}, "BVH map clip")
    _safe_id(clip.get("clip_id"), "clip_id")
    if type(clip.get("loop")) is not bool:
        raise BvhMapValidationError("BVH map clip loop must be boolean")

def _basis(value: Any) -> None:
    basis = _object(value, "BVH map basis")
    _exact(
        basis, {"screen_x", "screen_y", "depth", "rotation_convention"},
        "BVH map basis",
    )
    axes = [basis.get(name) for name in ("screen_x", "screen_y", "depth")]
    if any(axis not in _AXES for axis in axes) or len({axis[1] for axis in axes}) != 3:
        raise BvhMapValidationError("BVH map basis axes must be signed and orthogonal")
    if basis.get("rotation_convention") != "bvh_declared_channel_postmultiply":
        raise BvhMapValidationError("BVH map Euler convention is unsupported")

def _root(value: Any) -> str:
    root = _object(value, "BVH map root")
    _exact(
        root, {"joint_name", "reference_length_source_units", "translation_policy"},
        "BVH map root",
    )
    name = _joint_name(root.get("joint_name"), "root joint_name")
    _number(
        root.get("reference_length_source_units"), "reference length", 0.0,
        MAX_SOURCE_UNITS, exclusive_minimum=True,
    )
    if root.get("translation_policy") != \
            "projected_frame0_delta_normalized_reference_length":
        raise BvhMapValidationError("BVH map root translation policy is unsupported")
    return name

def _bones(value: Any, root_joint: str) -> dict[str, dict[str, Any]]:
    rows = _array(value, "BVH map bones")
    if not 1 <= len(rows) <= len(_ROLE_ORDER):
        raise BvhMapValidationError("BVH map bone resource limit exceeded")
    indexed: dict[str, dict[str, Any]] = {}
    joint_names, aims, previous = set(), set(), -1
    for raw in rows:
        row = _object(raw, "BVH map bone")
        _exact(row, _BONE, "BVH map bone")
        role = row.get("role")
        order = _ROLE_ORDER.get(role, -1)
        if order <= previous or role in indexed:
            raise BvhMapValidationError("BVH map bones must be canonically sorted and unique")
        previous = order
        joint = _joint_name(row.get("joint_name"), "bone joint_name")
        if joint in joint_names:
            raise BvhMapValidationError("BVH map bone joints must be unique")
        joint_names.add(joint)
        aim = _aim(row.get("aim"), joint)
        if aim in aims:
            raise BvhMapValidationError("BVH map bone aims must be unique")
        aims.add(aim)
        if row.get("rotation_policy") != "projected_setup_local_delta":
            raise BvhMapValidationError("BVH map bone rotation policy is unsupported")
        indexed[str(role)] = row
    if indexed.get("humanoid.root", {}).get("joint_name") != root_joint:
        raise BvhMapValidationError("BVH map humanoid root must bind the declared root joint")
    return indexed

def _aim(value: Any, source_joint: str) -> tuple[str, str]:
    aim = _object(value, "BVH map bone aim")
    kind = aim.get("kind")
    fields = {"kind", "joint_name"} if kind == "joint" else {"kind"}
    _exact(aim, fields, "BVH map bone aim")
    if kind == "joint":
        name = _joint_name(aim.get("joint_name"), "aim joint_name")
        if name == source_joint:
            raise BvhMapValidationError("BVH map bone cannot aim at itself")
        return kind, name
    if kind != "end_site":
        raise BvhMapValidationError("BVH map bone aim kind is unsupported")
    return kind, source_joint

def _contact(value: Any) -> dict[str, Any]:
    contact = _object(value, "BVH map contact")
    if type(contact.get("enabled")) is not bool:
        raise BvhMapValidationError("BVH map contact enabled must be boolean")
    fields = _CONTACT_ON if contact["enabled"] else {"enabled", "mode", "interval"}
    _exact(contact, fields, "BVH map contact")
    if contact.get("mode") != "annotation_only" or contact.get("interval") != "half_open":
        raise BvhMapValidationError("BVH map contact output contract is unsupported")
    if not contact["enabled"]:
        return contact
    if contact.get("height_policy") != \
            "absolute_signed_basis_screen_y_distance_to_floor" or \
            contact.get("speed_policy") != "source_world_3d_euclidean":
        raise BvhMapValidationError("BVH map contact measurement policy is unsupported")
    _number(contact.get("floor_height_source_units"), "contact floor", -MAX_SOURCE_UNITS, MAX_SOURCE_UNITS)
    _number(contact.get("height_threshold_source_units"), "contact height threshold", 0.0, MAX_SOURCE_UNITS)
    _number(contact.get("speed_threshold_source_units_per_second"), "contact speed threshold", 0.0, MAX_SPEED_SOURCE_UNITS_PER_SECOND)
    for field, minimum in (("minimum_frames", 1), ("gap_frames", 0)):
        number = contact.get(field)
        if type(number) is not int or not minimum <= number <= MAX_CONTACT_FRAMES:
            raise BvhMapValidationError(f"BVH map contact {field} is invalid")
    feet = _array(contact.get("feet"), "BVH map contact feet")
    if not 1 <= len(feet) <= 2:
        raise BvhMapValidationError("BVH map contact feet resource limit exceeded")
    previous, names = -1, set()
    for raw in feet:
        foot = _object(raw, "BVH map contact foot")
        _exact(foot, {"limb", "foot_joint_name"}, "BVH map contact foot")
        limb = foot.get("limb")
        order = {"leg.left": 0, "leg.right": 1}.get(limb, -1)
        name = _joint_name(foot.get("foot_joint_name"), "contact foot_joint_name")
        if order <= previous or name in names:
            raise BvhMapValidationError("BVH map contact feet must be sorted and unique")
        previous, names = order, names | {name}
    return contact

def _cross_bvh(
    bvh: BvhDocument, root_joint: str, bones: dict[str, dict[str, Any]],
    contact: dict[str, Any],
) -> None:
    if type(bvh) is not BvhDocument or not bvh.joints:
        raise BvhMapValidationError("BVH map requires a parsed non-empty BvhDocument")
    names = [joint.name for joint in bvh.joints]
    bad_parent = any(
        type(joint.parent_index) is not int or not 0 <= joint.parent_index < index
        for index, joint in enumerate(bvh.joints[1:], 1)
    )
    if len(names) != len(set(names)) or bvh.joints[0].parent_index is not None \
            or bad_parent:
        raise BvhMapValidationError("BVH source hierarchy is invalid")
    indexed = {name: index for index, name in enumerate(names)}
    try:
        require_bvh_motion_root(bvh, root_joint)
    except BvhMotionRootError as exc:
        raise BvhMapValidationError(str(exc)) from exc
    for role, row in bones.items():
        source = _known(indexed, row["joint_name"], "bone")
        aim = row["aim"]
        if aim["kind"] == "end_site":
            if bvh.joints[source].end_site_offset is None:
                raise BvhMapValidationError("BVH map references a missing End Site")
        else:
            target = _known(indexed, aim["joint_name"], "aim")
            if not _descends(bvh, target, source, allow_same=False):
                raise BvhMapValidationError("BVH map aim must descend from its source joint")
        parent = nearest_mapped_parent_role(role, bones)
        if parent is not None:
            parent_index = indexed[bones[parent]["joint_name"]]
            if not _descends(bvh, source, parent_index, allow_same=False):
                raise BvhMapValidationError("BVH map role topology differs from humanoid-v1")
    if contact["enabled"]:
        for foot in contact["feet"]:
            foot_index = _known(indexed, foot["foot_joint_name"], "contact foot")
            role = "humanoid.leg.lower." + foot["limb"].split(".")[1]
            if role in bones and not _descends(
                bvh, foot_index, indexed[bones[role]["joint_name"]], allow_same=True
            ):
                raise BvhMapValidationError("BVH contact foot is outside its mapped leg")

def _descends(bvh: BvhDocument, child: int, parent: int, *, allow_same: bool) -> bool:
    if allow_same and child == parent:
        return True
    cursor = bvh.joints[child].parent_index
    visited = set()
    while cursor is not None and cursor not in visited:
        if type(cursor) is not int or not 0 <= cursor < len(bvh.joints):
            return False
        if cursor == parent:
            return True
        visited.add(cursor)
        cursor = bvh.joints[cursor].parent_index
    return False

def _known(indexed: dict[str, int], name: str, label: str) -> int:
    if name not in indexed:
        raise BvhMapValidationError(f"BVH map {label} joint does not exist")
    return indexed[name]

def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise BvhMapValidationError(f"BVH map {label} is invalid")
    return value

def _joint_name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 256 or not value.isascii() \
            or any(character.isspace() or character in "{}" for character in value):
        raise BvhMapValidationError(f"BVH map {label} is not an ASCII BVH token")
    return value

def _number(value: Any, label: str, minimum: float, maximum: float, *, exclusive_minimum: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise BvhMapValidationError(f"BVH map {label} must be finite and bounded")
    below = value <= minimum if exclusive_minimum else value < minimum
    if below or value > maximum:
        raise BvhMapValidationError(f"BVH map {label} must be finite and bounded")
    return float(value)

def _object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise BvhMapValidationError(f"{label} must be a JSON object")
    return value

def _array(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise BvhMapValidationError(f"{label} must be a JSON array")
    return value

def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise BvhMapValidationError(f"{label} fields are incomplete or unsupported")
