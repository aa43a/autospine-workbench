"""4.3.26 document and cross-file checks, without relabeling data as 4.2."""
from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import math
import re

from ...spine42_json_adapter import require_projected_spine42_document
from ...spine42_export_validation import (
    MAX_SKELETON_JSON_BYTES, _attachment_inventory, _source_inventory,
    _validate_png, require_spine42_atlas_inventory,
)
from .contract import SPINE_JSON_VERSION, Spine43ContractError, canonical_spine43_json

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class Spine43ExportValidationError(ValueError):
    def __init__(self, reason_code="spine43_export_invalid"):
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True, slots=True)
class ValidatedSpine43Export:
    skeleton_json_bytes: bytes = field(repr=False)
    atlas_bytes: bytes = field(repr=False)
    png_bytes: bytes = field(repr=False)
    source_images: tuple[tuple[str, str], ...]
    attachment_paths: tuple[str, ...]
    atlas_width: int
    atlas_height: int
    bone_count: int
    slot_count: int
    attachment_count: int
    animation_count: int
    event_count: int


def _fields(value, required, optional=()):
    if not isinstance(value, Mapping) or not set(required) <= set(value) <= set(required) | set(optional):
        raise Spine43ContractError("spine43_document_invalid")


def _identifier(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise Spine43ContractError("spine43_identifier_invalid")
    return value


def _number(value, *, positive=False):
    if type(value) not in {int, float} or not math.isfinite(value) or (positive and value <= 0):
        raise Spine43ContractError("spine43_number_invalid")


def _array(value, *, minimum=0, maximum=4096):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        raise Spine43ContractError("spine43_collection_invalid")
    return value


def require_projected_spine43_document(document):
    try:
        _require_document(document)
    except Spine43ContractError:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError, RecursionError, OverflowError) as exc:
        raise Spine43ContractError("spine43_document_invalid") from exc


def _require_document(document):
    _fields(document, {"skeleton", "bones", "slots", "skins", "constraints", "events", "animations"})
    skeleton = document["skeleton"]
    _fields(skeleton, {"hash", "spine", "x", "y", "width", "height"})
    if skeleton["spine"] != SPINE_JSON_VERSION or document["constraints"] != []:
        raise Spine43ContractError("spine43_target_or_constraints_unsupported")
    if not isinstance(skeleton["hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", skeleton["hash"]):
        raise Spine43ContractError("spine43_source_hash_invalid")
    for key in ("x", "y", "width", "height"):
        _number(skeleton[key], positive=key in {"width", "height"})
    bones = {}
    for bone in _array(document["bones"], minimum=1):
        _fields(bone, {"name", "x", "y", "rotation", "scaleX", "scaleY", "length"}, {"parent"})
        name = _identifier(bone["name"])
        if name in bones or ("parent" in bone and bone["parent"] not in bones):
            raise Spine43ContractError("spine43_bone_order_invalid")
        for key in ("x", "y", "rotation", "scaleX", "scaleY", "length"):
            _number(bone[key], positive=key in {"scaleX", "scaleY", "length"})
        bones[name] = bone
    slots = {}
    for slot in _array(document["slots"], minimum=1):
        _fields(slot, {"name", "bone", "color", "blend"}, {"attachment"})
        name = _identifier(slot["name"])
        if name in slots or slot["bone"] not in bones:
            raise Spine43ContractError("spine43_slot_reference_invalid")
        if slot["blend"] not in {"normal", "additive", "multiply", "screen"} \
                or not isinstance(slot["color"], str) or not re.fullmatch(r"[0-9a-f]{8}", slot["color"]):
            raise Spine43ContractError("spine43_slot_style_invalid")
        if "attachment" in slot:
            _identifier(slot["attachment"])
        slots[name] = slot
    skins = {}
    for skin in _array(document["skins"], minimum=1):
        _fields(skin, {"name", "attachments"})
        name = _identifier(skin["name"])
        if name in skins or not isinstance(skin["attachments"], dict):
            raise Spine43ContractError("spine43_skin_invalid")
        skins[name] = skin["attachments"]
        for slot_id, attachments in skin["attachments"].items():
            if slot_id not in slots or not isinstance(attachments, dict):
                raise Spine43ContractError("spine43_attachment_reference_invalid")
            for attachment_id, attachment in attachments.items():
                _identifier(attachment_id)
                _attachment(attachment)
    if "default" not in skins:
        raise Spine43ContractError("spine43_default_skin_missing")
    for name, slot in slots.items():
        if "attachment" in slot and slot["attachment"] not in skins["default"].get(name, {}):
            raise Spine43ContractError("spine43_setup_attachment_missing")
    _animations(document, bones)
    # The existing helper is version-neutral geometry only: it does not check or
    # replace the header. Preserve both the input and returned 4.3.26 bytes.
    require_projected_spine42_document(document)
    canonical_spine43_json(document)


def _attachment(attachment):
    if not isinstance(attachment, dict):
        raise Spine43ContractError("spine43_attachment_invalid")
    kind = attachment.get("type")
    if kind == "region":
        _fields(attachment, {"type", "path", "x", "y", "rotation", "width", "height"})
        for field in ("x", "y", "rotation", "width", "height"):
            _number(attachment[field], positive=field in {"width", "height"})
    elif kind == "mesh":
        _fields(attachment, {"type", "path", "uvs", "triangles", "vertices"})
        for value in _array(attachment["uvs"], maximum=1000000):
            _number(value)
            if not 0 <= value <= 1:
                raise Spine43ContractError("spine43_mesh_uv_invalid")
        for value in _array(attachment["vertices"], maximum=1000000):
            _number(value)
        for value in _array(attachment["triangles"], maximum=1000000):
            if type(value) is not int:
                raise Spine43ContractError("spine43_mesh_triangle_invalid")
    else:
        raise Spine43ContractError("spine43_attachment_unsupported")
    _identifier(attachment["path"])


def _animations(document, bones):
    events, animations = document["events"], document["animations"]
    if type(events) is not dict or len(events) > 4096 or type(animations) is not dict or len(animations) > 1:
        raise Spine43ContractError("spine43_animation_unsupported")
    for name, event in events.items():
        _identifier(name)
        if event != {}:
            raise Spine43ContractError("spine43_event_unsupported")
    for name, animation in animations.items():
        _identifier(name)
        _fields(animation, {"bones"}, {"events"})
        if type(animation["bones"]) is not dict:
            raise Spine43ContractError("spine43_animation_unsupported")
        for bone_id, tracks in animation["bones"].items():
            if bone_id not in bones or type(tracks) is not dict or not set(tracks) <= {"rotate", "translate"}:
                raise Spine43ContractError("spine43_timeline_unsupported")
            for kind, keys in tracks.items():
                previous = -1.0
                for key in _array(keys, minimum=1, maximum=100000):
                    _fields(key, {"time", "value"} if kind == "rotate" else {"time", "x", "y"})
                    for value in key.values():
                        _number(value)
                    if key["time"] < 0 or key["time"] <= previous:
                        raise Spine43ContractError("spine43_timeline_time_invalid")
                    previous = key["time"]
        previous = -1.0
        for event in _array(animation.get("events", []), maximum=100000):
            _fields(event, {"time", "name"})
            _number(event["time"])
            if event["name"] not in events or event["time"] < 0 or event["time"] < previous:
                raise Spine43ContractError("spine43_event_invalid")
            previous = event["time"]


def validate_spine43_export(skeleton_json, atlas_bytes, png_bytes, source_image_sha256s,
                            *, expected_skeleton_hash, clip_id):
    """Reuse audited atlas/PNG inventories directly, without a header downgrade."""
    try:
        # Reject non-JSON arrays before serialization could turn tuples into lists.
        require_projected_spine43_document(skeleton_json)
        raw = canonical_spine43_json(skeleton_json)
        if len(raw) > MAX_SKELETON_JSON_BYTES:
            raise Spine43ExportValidationError()
        document = json.loads(raw)
        require_projected_spine43_document(document)
        if document["skeleton"]["hash"] != expected_skeleton_hash:
            raise Spine43ExportValidationError("spine43_source_hash_mismatch")
        expected_clips = set() if clip_id is None else {_identifier(clip_id)}
        if set(document["animations"]) != expected_clips:
            raise Spine43ExportValidationError("spine43_motion_mode_mismatch")
        paths, sizes, count = _attachment_inventory(document)
        if count > 16384:
            raise Spine43ExportValidationError()
        sources = _source_inventory(source_image_sha256s, paths)
        width, height, regions = require_spine42_atlas_inventory(atlas_bytes)
        if set(regions) != set(paths) or any(regions[path][2:] != size for path, size in sizes.items()):
            raise Spine43ExportValidationError("spine43_atlas_inventory_mismatch")
        _validate_png(png_bytes, width, height)
        return ValidatedSpine43Export(raw, atlas_bytes, png_bytes, sources, paths,
                                     width, height, len(document["bones"]), len(document["slots"]),
                                     count, len(document["animations"]), len(document["events"]))
    except Spine43ExportValidationError:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError, OverflowError) as exc:
        raise Spine43ExportValidationError() from exc
