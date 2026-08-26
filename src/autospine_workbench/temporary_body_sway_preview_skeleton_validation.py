"""Strict fixed-profile setup and attachment validation for P10 previews."""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
from typing import Any

from .body_sway_preview_profile import (
    BASE_ANIMATION_NAME,
    COMBINED_ANIMATION_NAME,
    body_sway_preview_adapter_profile,
)
from .manifest_artifacts import LayerManifestError, require_safe_token
from .resolved_project import canonical_sha256
from .body_sway_preview_projection import body_sway_preview_setup_sha256


MAX_SKINS = 256
MAX_ATTACHMENT_INSTANCES = 16_384
_COLOR = re.compile(r"^[0-9a-f]{8}$")
_BLENDS = {"normal", "additive", "multiply", "screen"}


class TemporaryBodySwayPreviewSkeletonError(ValueError):
    """Raised when untrusted Spine setup differs from the fixed adapter."""


def require_temporary_body_sway_preview_skeleton(
    skeleton: Mapping[str, Any],
    capture_plan: Mapping[str, Any],
    source: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate exact setup shapes and return its bounded atlas inventory."""

    try:
        if set(skeleton) != {
            "skeleton", "bones", "slots", "skins", "events", "animations",
        }:
            raise TemporaryBodySwayPreviewSkeletonError(
                "Preview skeleton top-level fields are invalid"
            )
        metadata = _metadata(skeleton, capture_plan, source, projection)
        bones = _array(skeleton.get("bones"), "bones", 1, 4096)
        slots = _array(skeleton.get("slots"), "slots", 1, 4096)
        skins = _array(skeleton.get("skins"), "skins", 1, MAX_SKINS)
        animations = _object(skeleton.get("animations"), "animations")
        events = _object(skeleton.get("events"), "events")
        if set(animations) != {BASE_ANIMATION_NAME, COMBINED_ANIMATION_NAME} \
                or len(events) > 4096:
            raise TemporaryBodySwayPreviewSkeletonError(
                "Preview animation or event inventory is invalid"
            )
        bone_ids = _bones(bones)
        slot_ids, setup_attachments = _slots(slots, bone_ids)
        attachments, region_sizes = _skins(skins, slot_ids)
        _require_setup_attachments(setup_attachments, skins)
        if body_sway_preview_setup_sha256(dict(skeleton)) \
                != projection["setup_sha256"]:
            raise TemporaryBodySwayPreviewSkeletonError(
                "Preview setup differs from its exact projection identity"
            )
        return {
            "bone_count": len(bone_ids),
            "slot_count": len(slot_ids),
            "attachment_ids": set(attachments),
            "region_sizes": region_sizes,
            "region_attachment_count": sum(
                row["type"] == "region" for row in attachments.values()
            ),
            "mesh_attachment_count": sum(
                row["type"] == "mesh" for row in attachments.values()
            ),
            "metadata_width": metadata[0],
            "metadata_height": metadata[1],
        }
    except TemporaryBodySwayPreviewSkeletonError:
        raise
    except (KeyError, LayerManifestError, TypeError, ValueError) as exc:
        raise TemporaryBodySwayPreviewSkeletonError(
            f"Temporary preview skeleton validation failed: {exc}"
        ) from exc


def _metadata(skeleton, capture, source, projection):
    metadata = _object(skeleton.get("skeleton"), "skeleton metadata")
    if set(metadata) != {"hash", "spine", "x", "y", "width", "height"} \
            or metadata.get("spine") != "4.2":
        raise TemporaryBodySwayPreviewSkeletonError(
            "Preview skeleton metadata fields are invalid"
        )
    expected_hash = canonical_sha256({
        "adapter_profile": body_sway_preview_adapter_profile(),
        "rig_sha256": source["p3"]["rig_sha256"],
        "target_profile_sha256": source["p5"]["target_profile_sha256"],
        "motion_instance_v2_sha256": source["p9"]["motion_instance_v2_sha256"],
        "body_sway_probe_report_sha256": source["body_sway_probe_report_sha256"],
        "preview_projection_sha256": projection["projection_sha256"],
    })
    world = capture["world_viewport"]
    actual = tuple(_number(metadata[field], f"metadata {field}") for field in (
        "x", "y", "width", "height",
    ))
    expected = tuple(float(world[field]) for field in (
        "x", "y", "width", "height",
    ))
    if metadata["hash"] != expected_hash or actual != expected:
        raise TemporaryBodySwayPreviewSkeletonError(
            "Preview skeleton identity or bounds differ from exact sources"
        )
    return actual[2], actual[3]


def _bones(rows):
    result: list[str] = []
    for index, raw in enumerate(rows):
        row = _object(raw, "bone")
        fields = {"name", "x", "y", "rotation", "scaleX", "scaleY", "length"}
        if index:
            fields.add("parent")
        if set(row) != fields:
            raise TemporaryBodySwayPreviewSkeletonError(
                "Preview bone fields are invalid"
            )
        name = require_safe_token(row["name"], "Bone name")
        if name in result or index and row["parent"] not in result:
            raise TemporaryBodySwayPreviewSkeletonError(
                "Preview bone hierarchy is invalid"
            )
        for field in ("x", "y", "rotation", "scaleX", "scaleY", "length"):
            _number(row[field], f"bone {field}")
        if row["scaleX"] != 1.0 or row["scaleY"] != 1.0 or row["length"] < 0:
            raise TemporaryBodySwayPreviewSkeletonError(
                "Preview bone setup values are invalid"
            )
        result.append(name)
    return tuple(result)


def _slots(rows, bone_ids):
    names: list[str] = []
    setup: dict[str, str] = {}
    for raw in rows:
        row = _object(raw, "slot")
        if not {"name", "bone", "color", "blend"} <= set(row) \
                or not set(row) <= {"name", "bone", "color", "blend", "attachment"}:
            raise TemporaryBodySwayPreviewSkeletonError(
                "Preview slot fields are invalid"
            )
        name = require_safe_token(row["name"], "Slot name")
        if name in names or row["bone"] not in bone_ids \
                or not isinstance(row["color"], str) \
                or _COLOR.fullmatch(row["color"]) is None \
                or row["blend"] not in _BLENDS:
            raise TemporaryBodySwayPreviewSkeletonError(
                "Preview slot values are invalid"
            )
        if "attachment" in row:
            setup[name] = require_safe_token(
                row["attachment"], "Setup attachment"
            )
        names.append(name)
    return tuple(names), setup


def _skins(rows, slot_ids):
    names: list[str] = []
    attachments: dict[str, dict[str, Any]] = {}
    sizes: dict[str, tuple[int, int]] = {}
    instances = 0
    for raw in rows:
        skin = _object(raw, "skin")
        if set(skin) != {"name", "attachments"}:
            raise TemporaryBodySwayPreviewSkeletonError(
                "Preview skin fields are invalid"
            )
        name = require_safe_token(skin["name"], "Skin name")
        if name in names or any(name.casefold() == item.casefold() for item in names):
            raise TemporaryBodySwayPreviewSkeletonError(
                "Preview skin names are duplicated or aliased"
            )
        names.append(name)
        slot_map = _object(skin["attachments"], "skin attachments")
        for slot_id, raw_values in slot_map.items():
            if slot_id not in slot_ids:
                raise TemporaryBodySwayPreviewSkeletonError(
                    "Preview skin references a missing slot"
                )
            for key, raw_attachment in _object(raw_values, "slot attachments").items():
                instances += 1
                if instances > MAX_ATTACHMENT_INSTANCES:
                    raise TemporaryBodySwayPreviewSkeletonError(
                        "Preview attachment instance count is invalid"
                    )
                _attachment(key, raw_attachment, attachments, sizes)
    if names[0] != "default" or names[1:] != sorted(names[1:]) \
            or not attachments:
        raise TemporaryBodySwayPreviewSkeletonError(
            "Preview skin order or attachment count is invalid"
        )
    return attachments, sizes


def _attachment(key, raw, inventory, sizes):
    name = require_safe_token(key, "Attachment name")
    row = _object(raw, "attachment")
    kind = row.get("type")
    fields = (
        {"type", "path", "x", "y", "rotation", "width", "height"}
        if kind == "region" else
        {"type", "path", "uvs", "triangles", "vertices"}
    )
    if kind not in {"region", "mesh"} or set(row) != fields \
            or require_safe_token(row.get("path"), "Attachment path") != name:
        raise TemporaryBodySwayPreviewSkeletonError(
            "Preview attachment fields or path are invalid"
        )
    if kind == "region":
        for field in ("x", "y", "rotation", "width", "height"):
            _number(row[field], f"region {field}")
        size = (_positive_integer(row["width"]), _positive_integer(row["height"]))
        if sizes.setdefault(name, size) != size:
            raise TemporaryBodySwayPreviewSkeletonError(
                "Shared preview region sizes disagree"
            )
    else:
        uvs = row["uvs"]
        if not isinstance(uvs, list) or any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(float(value)) for value in uvs
        ):
            raise TemporaryBodySwayPreviewSkeletonError(
                "Preview mesh UV values are invalid"
            )
    identity = {"type": kind, "sha256": canonical_sha256(row)}
    if inventory.setdefault(name, identity) != identity:
        raise TemporaryBodySwayPreviewSkeletonError(
            "Shared preview attachment definitions disagree"
        )


def _require_setup_attachments(setup, skins):
    default = skins[0]["attachments"]
    for slot_id, attachment in setup.items():
        if attachment not in default.get(slot_id, {}):
            raise TemporaryBodySwayPreviewSkeletonError(
                "Preview setup attachment is absent from the default skin"
            )


def _object(value, label):
    if not isinstance(value, Mapping):
        raise TemporaryBodySwayPreviewSkeletonError(
            f"Preview {label} must be an object"
        )
    return value


def _array(value, label, minimum, maximum):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise TemporaryBodySwayPreviewSkeletonError(
            f"Preview {label} count is invalid"
        )
    return value


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)):
        raise TemporaryBodySwayPreviewSkeletonError(
            f"Preview {label} must be finite"
        )
    return float(value)


def _positive_integer(value):
    number = _number(value, "region dimension")
    if number < 1 or not number.is_integer():
        raise TemporaryBodySwayPreviewSkeletonError(
            "Preview region dimension must be a positive integer"
        )
    return int(number)
