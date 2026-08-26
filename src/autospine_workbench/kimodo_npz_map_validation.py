"""Fail-closed SOMA77-to-MotionIR mapping for validated Kimodo NPZ."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
import re
from typing import Any

from .kimodo_npz_source import (
    CONTACT_LAYOUTS,
    KimodoNpzSourceError,
    require_kimodo_npz_source,
)
from .kimodo_soma77 import SOMA77_INDEX_BY_NAME, soma77_descends
from .motion_roles import CANONICAL_BONE_ROLE_ITEMS, nearest_mapped_parent_role


FORMAT = "autospine-kimodo-npz-map"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_REFERENCE_METERS = 1_000_000.0
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_AXES = frozenset(("+X", "-X", "+Y", "-Y", "+Z", "-Z"))
_ROLE_ORDER = {
    role: index for index, (role, _bone) in enumerate(CANONICAL_BONE_ROLE_ITEMS)
}
_TOP = {
    "format", "format_version", "map_id", "clip", "basis", "root",
    "bones", "contact",
}
_BONE = {"role", "joint_name", "aim_joint_name", "rotation_policy"}
_CONTACT_LAYOUT_ROWS = {
    "left-heel-toe-right-heel-toe-v1": (
        (0, "leg.left", "heel"),
        (1, "leg.left", "toe"),
        (2, "leg.right", "heel"),
        (3, "leg.right", "toe"),
    ),
    "left-heel-toe-toe_end-right-heel-toe-toe_end-v1": (
        (0, "leg.left", "heel"),
        (1, "leg.left", "toe"),
        (2, "leg.left", "toe_end"),
        (3, "leg.right", "heel"),
        (4, "leg.right", "toe"),
        (5, "leg.right", "toe_end"),
    ),
}


class KimodoNpzMapError(ValueError):
    """Raised when NPZ projection, role, or contact semantics require guessing."""


def kimodo_npz_map_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical identity of one fully validated explicit map."""

    require_kimodo_npz_map(document)
    return hashlib.sha256(_canonical(document)).hexdigest()


def require_kimodo_npz_map(
    document: Mapping[str, Any], *, source: Mapping[str, Any] | None = None
) -> None:
    """Validate a map, optionally against one exact source interpretation."""

    try:
        root = _object(document, "Kimodo NPZ map")
        _exact(root, _TOP, "Kimodo NPZ map")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise KimodoNpzMapError("Kimodo NPZ map format is unsupported")
        _safe_id(root.get("map_id"), "map_id")
        _clip(root.get("clip"))
        _basis(root.get("basis"))
        root_joint = _root(root.get("root"))
        bones = _bones(root.get("bones"), root_joint)
        contact_layout = _contact(root.get("contact"))
        if source is not None:
            _cross_source(source, contact_layout)
        if len(_canonical(root)) > MAX_DOCUMENT_BYTES:
            raise KimodoNpzMapError("Kimodo NPZ map byte limit exceeded")
    except KimodoNpzMapError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise KimodoNpzMapError(
            f"Kimodo NPZ map validation failed: {exc}"
        ) from exc


def _clip(value: Any) -> None:
    clip = _object(value, "Kimodo NPZ map clip")
    _exact(clip, {"clip_id", "loop"}, "Kimodo NPZ map clip")
    _safe_id(clip.get("clip_id"), "clip_id")
    if type(clip.get("loop")) is not bool:
        raise KimodoNpzMapError("Kimodo NPZ clip loop must be boolean")


def _basis(value: Any) -> None:
    basis = _object(value, "Kimodo NPZ map basis")
    _exact(
        basis, {"screen_x", "screen_y", "depth", "rotation_convention"},
        "Kimodo NPZ map basis",
    )
    axes = [basis.get(field) for field in ("screen_x", "screen_y", "depth")]
    if any(axis not in _AXES for axis in axes) \
            or len({str(axis)[1] for axis in axes}) != 3:
        raise KimodoNpzMapError("Kimodo NPZ basis axes must be signed and orthogonal")
    if basis.get("rotation_convention") != \
            "validated_matrix_fk_projected_segment":
        raise KimodoNpzMapError("Kimodo NPZ rotation convention is unsupported")


def _root(value: Any) -> str:
    root = _object(value, "Kimodo NPZ map root")
    _exact(root, {
        "joint_name", "position_source", "reference_length_meters",
        "translation_policy", "baseline_policy",
    }, "Kimodo NPZ map root")
    if root.get("joint_name") != "Hips" \
            or root.get("position_source") != "root_positions" \
            or root.get("translation_policy") != \
            "projected_frame0_delta_normalized_reference_length" \
            or root.get("baseline_policy") != "source_frame0":
        raise KimodoNpzMapError("Kimodo NPZ root contract is unsupported")
    reference = root.get("reference_length_meters")
    if isinstance(reference, bool) or not isinstance(reference, (int, float)) \
            or not math.isfinite(reference) \
            or not 0 < float(reference) <= MAX_REFERENCE_METERS:
        raise KimodoNpzMapError("Kimodo NPZ reference length is invalid")
    return "Hips"


def _bones(value: Any, root_joint: str) -> dict[str, Mapping[str, Any]]:
    rows = _array(value, "Kimodo NPZ map bones")
    if not 1 <= len(rows) <= len(_ROLE_ORDER):
        raise KimodoNpzMapError("Kimodo NPZ bone resource limit exceeded")
    indexed: dict[str, Mapping[str, Any]] = {}
    joints, aims, previous = set(), set(), -1
    for raw in rows:
        row = _object(raw, "Kimodo NPZ map bone")
        _exact(row, _BONE, "Kimodo NPZ map bone")
        role = row.get("role")
        order = _ROLE_ORDER.get(role, -1)
        if order <= previous or role in indexed:
            raise KimodoNpzMapError(
                "Kimodo NPZ bones must be canonically sorted and unique"
            )
        previous = order
        joint = _joint(row.get("joint_name"), "bone joint_name")
        aim = _joint(row.get("aim_joint_name"), "bone aim_joint_name")
        if joint in joints or aim in aims or not soma77_descends(aim, joint):
            raise KimodoNpzMapError(
                "Kimodo NPZ bone sources/aims must be unique descendants"
            )
        if row.get("rotation_policy") != \
                "projected_setup_local_delta_from_validated_fk":
            raise KimodoNpzMapError("Kimodo NPZ bone rotation policy is unsupported")
        joints.add(joint)
        aims.add(aim)
        indexed[str(role)] = row
    if indexed.get("humanoid.root", {}).get("joint_name") != root_joint:
        raise KimodoNpzMapError("Kimodo NPZ humanoid root must bind Hips")
    for role, row in indexed.items():
        parent = nearest_mapped_parent_role(role, indexed)
        if parent is not None and not soma77_descends(
            str(row["joint_name"]), str(indexed[parent]["joint_name"])
        ):
            raise KimodoNpzMapError(
                "Kimodo NPZ role topology differs from humanoid-v1"
            )
    return indexed


def _contact(value: Any) -> str | None:
    contact = _object(value, "Kimodo NPZ map contact")
    if type(contact.get("enabled")) is not bool:
        raise KimodoNpzMapError("Kimodo NPZ contact enabled must be boolean")
    if not contact["enabled"]:
        _exact(contact, {"enabled", "mode", "interval"}, "Kimodo NPZ contact")
        if contact.get("mode") != "annotation_only" \
                or contact.get("interval") != "half_open":
            raise KimodoNpzMapError("Kimodo NPZ contact output is unsupported")
        return None
    _exact(contact, {
        "enabled", "source", "layout", "channels", "reduction_policy",
        "mode", "interval",
    }, "Kimodo NPZ contact")
    layout = contact.get("layout")
    if contact.get("source") != "foot_contacts" \
            or layout not in CONTACT_LAYOUTS \
            or contact.get("reduction_policy") != "any_true_per_limb" \
            or contact.get("mode") != "annotation_only" \
            or contact.get("interval") != "half_open":
        raise KimodoNpzMapError("Kimodo NPZ contact policy is unsupported")
    channels = _array(contact.get("channels"), "Kimodo NPZ contact channels")
    normalized = []
    for raw in channels:
        row = _object(raw, "Kimodo NPZ contact channel")
        _exact(row, {"index", "limb", "point"}, "Kimodo NPZ contact channel")
        normalized.append((row.get("index"), row.get("limb"), row.get("point")))
    if tuple(normalized) != _CONTACT_LAYOUT_ROWS[str(layout)]:
        raise KimodoNpzMapError(
            "Kimodo NPZ contact channel evidence differs from its layout"
        )
    return str(layout)


def _cross_source(source: Mapping[str, Any], contact_layout: str | None) -> None:
    try:
        require_kimodo_npz_source(source)
    except KimodoNpzSourceError as exc:
        raise KimodoNpzMapError("Kimodo NPZ map source is invalid") from exc
    declared = source["array_profile"]["contact_layout"]
    if contact_layout is not None and contact_layout != declared:
        raise KimodoNpzMapError("Kimodo NPZ map contact layout differs from source")


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise KimodoNpzMapError(f"Kimodo NPZ {label} is invalid")
    return value


def _joint(value: Any, label: str) -> str:
    if not isinstance(value, str) or value not in SOMA77_INDEX_BY_NAME:
        raise KimodoNpzMapError(f"Kimodo NPZ {label} is not in SOMA77")
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KimodoNpzMapError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise KimodoNpzMapError(f"{label} must be an array")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise KimodoNpzMapError(f"{label} fields are incomplete or unsupported")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
