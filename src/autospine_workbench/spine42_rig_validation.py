"""Strict JSON-shape and semantic validation for Spine 4.2 RigIR inputs."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
from typing import Any

from .rig_validation import RigSemanticValidationError, RigSemanticValidator


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_COLOR = re.compile(r"^[0-9a-fA-F]{8}$")
_TOP = {
    "format", "format_version", "source", "canvas", "capabilities",
    "unsupported_feature_policy", "bones", "slots", "attachments",
    "skins", "animations", "qa",
}
_CAPABILITIES = {"region_attachment", "mesh_attachment", "setup_draw_order"}


class Spine42RigValidationError(ValueError):
    """Raised when P3 RigIR exceeds the pinned adapter profile."""


def require_spine42_rig(rig: Mapping[str, Any]) -> None:
    """Validate exact JSON shape, finite values, references, and topology."""

    try:
        root = _mapping(rig, "P3 RigIR")
        if not _TOP.issubset(root) or not set(root) <= _TOP | {"retarget"}:
            raise Spine42RigValidationError("P3 RigIR fields are incomplete or unsupported")
        if root.get("format") != "autospine-rig-ir" or root.get("format_version") != 1:
            raise Spine42RigValidationError("P3 RigIR format is unsupported")
        if root.get("unsupported_feature_policy") != "fail":
            raise Spine42RigValidationError("P3 unsupported-feature policy must fail closed")
        if _mapping(root.get("qa"), "P3 QA").get("status") != "passed":
            raise Spine42RigValidationError("P3 RigIR QA must be passed")
        if root.get("animations") != []:
            raise Spine42RigValidationError("Embedded RigIR animations are outside this profile")
        _source(root.get("source"))
        _canvas(root.get("canvas"))
        capabilities = root.get("capabilities")
        if not isinstance(capabilities, list) or len(set(capabilities)) != len(capabilities) \
                or not set(capabilities) <= _CAPABILITIES:
            raise Spine42RigValidationError("P3 capabilities exceed the minimum Spine profile")
        _bones(root.get("bones"))
        _slots(root.get("slots"))
        _attachments(root.get("attachments"))
        _skins(root.get("skins"))
        json.dumps(root, allow_nan=False, sort_keys=True, separators=(",", ":"))
        RigSemanticValidator().raise_for_errors(root)
    except Spine42RigValidationError:
        raise
    except (RigSemanticValidationError, TypeError, ValueError) as exc:
        raise Spine42RigValidationError(f"P3 RigIR is invalid: {exc}") from exc


def _source(value: Any) -> None:
    source = _mapping(value, "P3 source")
    required = {"run_manifest_sha256", "layer_manifest_sha256"}
    allowed = required | {"override_patch_sha256"}
    if not required <= set(source) or not set(source) <= allowed or any(
        not isinstance(item, str) or not _SHA.fullmatch(item)
        for item in source.values()
    ):
        raise Spine42RigValidationError("P3 source identity is unsupported")


def _canvas(value: Any) -> None:
    canvas = _mapping(value, "P3 canvas")
    axes = {"origin": "top_left", "x_axis": "right", "y_axis": "down", "units": "pixel"}
    if set(canvas) != {"width", "height", *axes} or any(
        type(canvas.get(field)) is not int or canvas[field] < 1
        for field in ("width", "height")
    ) or any(canvas.get(field) != expected for field, expected in axes.items()):
        raise Spine42RigValidationError("P3 canvas coordinate system is unsupported")


def _bones(value: Any) -> None:
    bones = _array(value, "bones")
    if not bones:
        raise Spine42RigValidationError("P3 RigIR must contain bones")
    for bone in bones:
        bone = _mapping(bone, "bone")
        if set(bone) != {"id", "parent", "setup", "inference"}:
            raise Spine42RigValidationError("Bone fields are unsupported")
        _safe_id(bone.get("id"), "bone id")
        if bone.get("parent") is not None:
            _safe_id(bone.get("parent"), "bone parent")
        setup = _mapping(bone.get("setup"), "bone setup")
        if set(setup) != {"x", "y", "rotation_deg", "scale_x", "scale_y", "length"}:
            raise Spine42RigValidationError("Bone setup fields are unsupported")
        if setup.get("scale_x") != 1.0 or setup.get("scale_y") != 1.0:
            raise Spine42RigValidationError("Minimum Spine profile requires unit setup scale")
        if not _number(setup.get("length")) or float(setup["length"]) <= 0:
            raise Spine42RigValidationError("Bone length must be finite and positive")


def _slots(value: Any) -> None:
    fields = {"id", "bone", "setup_attachment", "setup_draw_order", "blend", "color_rgba"}
    for slot in _array(value, "slots"):
        slot = _mapping(slot, "slot")
        if set(slot) != fields:
            raise Spine42RigValidationError("Slot fields are unsupported")
        _safe_id(slot.get("id"), "slot id")
        _safe_id(slot.get("bone"), "slot bone")
        if slot.get("setup_attachment") is not None:
            _safe_id(slot.get("setup_attachment"), "setup attachment")
        if type(slot.get("setup_draw_order")) is not int:
            raise Spine42RigValidationError("Slot draw order must be an integer")
        if slot.get("blend") not in {"normal", "additive", "multiply", "screen"} \
                or not isinstance(slot.get("color_rgba"), str) \
                or not _COLOR.fullmatch(slot["color_rgba"]):
            raise Spine42RigValidationError("Slot blend or color is unsupported")


def _attachments(value: Any) -> None:
    common = {
        "id", "slot", "type", "image_path", "image_sha256", "source_layer_ids",
        "canvas_offset_xy", "pivot_xy",
    }
    for item in _array(value, "attachments"):
        item = _mapping(item, "attachment")
        kind = item.get("type")
        specific = {"size"} if kind == "region" else {
            "vertices", "uvs", "triangles", "weights",
        } if kind == "mesh" else set()
        if kind not in {"region", "mesh"} or set(item) != common | specific:
            raise Spine42RigValidationError("Attachment fields or type are unsupported")
        _attachment_base(item)
        if kind == "region":
            if any(number <= 0 for number in _point(item.get("size"), "region size")):
                raise Spine42RigValidationError("Region size must be positive")
        else:
            _mesh(item)


def _attachment_base(item: Mapping[str, Any]) -> None:
    _safe_id(item.get("id"), "attachment id")
    _safe_id(item.get("slot"), "attachment slot")
    path = item.get("image_path")
    if not isinstance(path, str) or not path or "\\" in path or path.startswith("/") \
            or re.match(r"^[A-Za-z]:", path) or ".." in path.split("/"):
        raise Spine42RigValidationError("Attachment image path is unsafe")
    if not isinstance(item.get("image_sha256"), str) or not _SHA.fullmatch(item["image_sha256"]):
        raise Spine42RigValidationError("Attachment image SHA-256 is invalid")
    layers = _array(item.get("source_layer_ids"), "source layer ids")
    if not layers or len(set(layers)) != len(layers):
        raise Spine42RigValidationError("Attachment source layers are invalid")
    for layer in layers:
        _safe_id(layer, "source layer id")
    _point(item.get("canvas_offset_xy"), "canvas offset")
    _point(item.get("pivot_xy"), "attachment pivot")


def _mesh(item: Mapping[str, Any]) -> None:
    for point in _array(item.get("vertices"), "mesh vertices"):
        _point(point, "mesh vertex")
    for point in _array(item.get("uvs"), "mesh UVs"):
        _point(point, "mesh UV")
    if any(type(index) is not int for index in _array(item.get("triangles"), "mesh triangles")):
        raise Spine42RigValidationError("Mesh triangle indices must be integers")
    for influences in _array(item.get("weights"), "mesh weights"):
        for influence in _array(influences, "mesh influences"):
            if set(_mapping(influence, "mesh influence")) != {"bone", "weight"}:
                raise Spine42RigValidationError("Mesh influence fields are unsupported")


def _skins(value: Any) -> None:
    skins = _mapping(value, "skins")
    if "default" not in skins:
        raise Spine42RigValidationError("Default skin is required")
    for skin, slot_map in skins.items():
        _safe_id(skin, "skin id")
        for slot, attachments in _mapping(slot_map, "skin slots").items():
            _safe_id(slot, "skin slot")
            for attachment in _array(attachments, "skin attachments"):
                _safe_id(attachment, "skin attachment")


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise Spine42RigValidationError(f"{label} is invalid")
    return value


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(float(value))


def _point(value: Any, label: str) -> tuple[float, float]:
    point = _array(value, label)
    if len(point) != 2 or not all(_number(item) for item in point):
        raise Spine42RigValidationError(f"{label} must contain two finite numbers")
    return float(point[0]), float(point[1])


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Spine42RigValidationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise Spine42RigValidationError(f"{label} must be an array")
    return value
