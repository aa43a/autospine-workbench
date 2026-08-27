"""Closed setup-output surface for the pinned MotionInstance v3 adapter."""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
from typing import Any

from .spine42_contract import Spine42ContractError
from .spine42_json_adapter import require_projected_spine42_document


_SKELETON_FIELDS = {"hash", "spine", "x", "y", "width", "height"}
_BONE_FIELDS = {
    "name", "x", "y", "rotation", "scaleX", "scaleY", "length",
}
_SLOT_FIELDS = {"name", "bone", "color", "blend"}
_REGION_FIELDS = {
    "type", "path", "x", "y", "rotation", "width", "height",
}
_MESH_FIELDS = {"type", "path", "uvs", "triangles", "vertices"}
_COLOR = re.compile(r"[0-9a-f]{8}")
_BLENDS = {"normal", "additive", "multiply", "screen"}
_MAX_SETUP_ITEMS = 4096


class Spine42V3SetupValidationError(ValueError):
    """Raised when setup JSON contains capabilities the adapter never emits."""


def require_spine42_v3_setup(
    document: Mapping[str, Any],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Validate the exact skeleton, bone, slot, skin, and attachment shapes."""

    try:
        value = _object(document, "document")
        _skeleton(value["skeleton"])
        bone_ids = _bones(value["bones"])
        slot_ids, setup_attachments = _slots(value["slots"], bone_ids)
        _skins(value["skins"], slot_ids, setup_attachments)
        require_projected_spine42_document(value)
        return bone_ids, slot_ids
    except Spine42V3SetupValidationError:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        Spine42ContractError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42V3SetupValidationError(
            f"Spine 4.2 v3 setup is invalid: {exc}"
        ) from exc


def _skeleton(value: Any) -> None:
    skeleton = _object(value, "skeleton")
    if set(skeleton) != _SKELETON_FIELDS \
            or type(skeleton["hash"]) is not str \
            or type(skeleton["spine"]) is not str:
        raise Spine42V3SetupValidationError(
            "Spine v3 skeleton metadata fields are invalid"
        )
    for field in ("x", "y", "width", "height"):
        number = _number(skeleton[field], f"skeleton {field}")
        if field in {"width", "height"} and number <= 0:
            raise Spine42V3SetupValidationError(
                "Spine v3 skeleton dimensions must be positive"
            )


def _bones(value: Any) -> tuple[str, ...]:
    bones = _array(value, "bones")
    if not 1 <= len(bones) <= _MAX_SETUP_ITEMS:
        raise Spine42V3SetupValidationError("Spine v3 bone count is invalid")
    names: list[str] = []
    seen: set[str] = set()
    for raw in bones:
        bone = _object(raw, "bone")
        fields = set(bone)
        if fields not in (_BONE_FIELDS, _BONE_FIELDS | {"parent"}):
            raise Spine42V3SetupValidationError(
                "Spine v3 bone fields exceed the adapter profile"
            )
        name = _name(bone["name"], "bone")
        if name in seen:
            raise Spine42V3SetupValidationError(
                "Spine v3 bone names are not unique"
            )
        if "parent" in bone and bone["parent"] not in seen:
            raise Spine42V3SetupValidationError(
                "Spine v3 bone parent must precede its child"
            )
        for field in _BONE_FIELDS - {"name"}:
            _number(bone[field], f"bone {field}")
        if bone["scaleX"] != 1.0 or bone["scaleY"] != 1.0 \
                or bone["length"] < 0:
            raise Spine42V3SetupValidationError(
                "Spine v3 bone setup differs from the adapter profile"
            )
        names.append(name)
        seen.add(name)
    return tuple(names)


def _slots(
    value: Any, bone_ids: tuple[str, ...],
) -> tuple[tuple[str, ...], dict[str, str]]:
    slots = _array(value, "slots")
    if not 1 <= len(slots) <= _MAX_SETUP_ITEMS:
        raise Spine42V3SetupValidationError("Spine v3 slot count is invalid")
    bone_set = set(bone_ids)
    names: list[str] = []
    seen: set[str] = set()
    setup: dict[str, str] = {}
    for raw in slots:
        slot = _object(raw, "slot")
        fields = set(slot)
        if fields not in (_SLOT_FIELDS, _SLOT_FIELDS | {"attachment"}):
            raise Spine42V3SetupValidationError(
                "Spine v3 slot fields exceed the adapter profile"
            )
        name = _name(slot["name"], "slot")
        if name in seen or slot["bone"] not in bone_set \
                or type(slot["color"]) is not str \
                or _COLOR.fullmatch(slot["color"]) is None \
                or slot["blend"] not in _BLENDS:
            raise Spine42V3SetupValidationError(
                "Spine v3 slot setup is invalid"
            )
        if "attachment" in slot:
            setup[name] = _name(slot["attachment"], "setup attachment")
        names.append(name)
        seen.add(name)
    return tuple(names), setup


def _skins(
    value: Any,
    slot_ids: tuple[str, ...],
    setup_attachments: Mapping[str, str],
) -> None:
    skins = _array(value, "skins")
    if not 1 <= len(skins) <= _MAX_SETUP_ITEMS:
        raise Spine42V3SetupValidationError("Spine v3 skin count is invalid")
    names: list[str] = []
    seen: set[str] = set()
    slot_set = set(slot_ids)
    default: dict[str, set[str]] | None = None
    for raw in skins:
        skin = _object(raw, "skin")
        if set(skin) != {"name", "attachments"}:
            raise Spine42V3SetupValidationError(
                "Spine v3 skin fields exceed the adapter profile"
            )
        name = _name(skin["name"], "skin")
        if name in seen:
            raise Spine42V3SetupValidationError(
                "Spine v3 skin names are not unique"
            )
        inventory = _skin_attachments(skin["attachments"], slot_set)
        if name == "default":
            default = inventory
        names.append(name)
        seen.add(name)
    if not names or names != ["default", *sorted(set(names) - {"default"})] \
            or default is None:
        raise Spine42V3SetupValidationError(
            "Spine v3 skin order differs from the adapter profile"
        )
    for slot, attachment in setup_attachments.items():
        if attachment not in default.get(slot, set()):
            raise Spine42V3SetupValidationError(
                "Spine v3 setup attachment is absent from the default skin"
            )


def _skin_attachments(
    value: Any, slot_ids: set[str],
) -> dict[str, set[str]]:
    slots = _object(value, "skin attachments")
    if not set(slots) <= slot_ids:
        raise Spine42V3SetupValidationError(
            "Spine v3 skin references an unknown slot"
        )
    result: dict[str, set[str]] = {}
    for slot, raw in slots.items():
        attachments = _object(raw, "slot attachments")
        result[slot] = set(attachments)
        for name, attachment in attachments.items():
            _attachment(_name(name, "attachment"), attachment)
    return result


def _attachment(name: str, value: Any) -> None:
    attachment = _object(value, "attachment")
    kind = attachment.get("type")
    expected = _REGION_FIELDS if kind == "region" else _MESH_FIELDS
    if kind not in {"region", "mesh"} or set(attachment) != expected \
            or attachment["path"] != name:
        raise Spine42V3SetupValidationError(
            "Spine v3 attachment fields exceed the adapter profile"
        )
    if kind == "region":
        for field in _REGION_FIELDS - {"type", "path"}:
            number = _number(attachment[field], f"region {field}")
            if field in {"width", "height"} and number <= 0:
                raise Spine42V3SetupValidationError(
                    "Spine v3 region dimensions must be positive"
                )
    else:
        for uv in _array(attachment["uvs"], "mesh uvs"):
            _number(uv, "mesh uv")
        _array(attachment["triangles"], "mesh triangles")
        _array(attachment["vertices"], "mesh vertices")


def _object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise Spine42V3SetupValidationError(f"Spine v3 {label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise Spine42V3SetupValidationError(f"Spine v3 {label} must be an array")
    return value


def _name(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise Spine42V3SetupValidationError(f"Spine v3 {label} name is invalid")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)):
        raise Spine42V3SetupValidationError(f"Spine v3 {label} is not finite")
    return float(value)


__all__ = [
    "Spine42V3SetupValidationError", "require_spine42_v3_setup",
]
