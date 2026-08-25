"""Pure deterministic RigIR/MotionInstance to Spine 4.2 JSON conversion."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
from typing import Any

from .resolved_project import canonical_sha256
from .spine42_contract import (
    SPINE_JSON_VERSION,
    Spine42ContractError,
    canonical_spine42_json,
    require_spine42_inputs,
    spine42_target_profile,
)
from .spine42_geometry import Spine42Setup, project_attachment, project_setup


def build_spine42_json(
    rig: Mapping[str, Any],
    *,
    motion_instance: Mapping[str, Any] | None = None,
    target_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the minimum pinned Spine 4.2 JSON document without file I/O."""

    require_spine42_inputs(
        rig, motion_instance=motion_instance, target_profile=target_profile
    )
    setup = project_setup(rig)
    slots = _project_slots(rig["slots"])
    skins = _project_skins(rig, setup)
    events, animations = _project_motion(motion_instance)
    source = {
        "adapter_profile": spine42_target_profile(),
        "rig_sha256": canonical_sha256(rig),
        "motion_instance_sha256": (
            canonical_sha256(motion_instance) if motion_instance is not None else None
        ),
        "target_profile_sha256": (
            canonical_sha256(target_profile) if target_profile is not None else None
        ),
    }
    document = {
        "skeleton": {
            "hash": canonical_sha256(source),
            "spine": SPINE_JSON_VERSION,
            "x": 0.0,
            "y": 0.0,
            "width": float(rig["canvas"]["width"]),
            "height": float(rig["canvas"]["height"]),
        },
        "bones": [dict(item) for item in setup.bones],
        "slots": slots,
        "skins": skins,
        "events": events,
        "animations": animations,
    }
    _require_projected_document(document)
    return json.loads(canonical_spine42_json(document))


def build_spine42_json_bytes(
    rig: Mapping[str, Any],
    *,
    motion_instance: Mapping[str, Any] | None = None,
    target_profile: Mapping[str, Any] | None = None,
) -> bytes:
    """Build and canonically serialize the pinned Spine JSON document."""

    return canonical_spine42_json(build_spine42_json(
        rig, motion_instance=motion_instance, target_profile=target_profile,
    ))


def _project_slots(raw_slots: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for slot in sorted(raw_slots, key=lambda item: (item["setup_draw_order"], item["id"])):
        projected = {
            "name": slot["id"],
            "bone": slot["bone"],
            "color": slot["color_rgba"].lower(),
            "blend": slot["blend"],
        }
        if slot["setup_attachment"] is not None:
            projected["attachment"] = slot["setup_attachment"]
        result.append(projected)
    return result


def _project_skins(rig: Mapping[str, Any], setup: Spine42Setup) -> list[dict[str, Any]]:
    attachments = {item["id"]: item for item in rig["attachments"]}
    slots = {item["id"]: item for item in rig["slots"]}
    membership: set[str] = set()
    result: list[dict[str, Any]] = []
    skin_names = ["default", *sorted(set(rig["skins"]) - {"default"})]
    for skin_name in skin_names:
        projected_slots: dict[str, Any] = {}
        slot_map = rig["skins"][skin_name]
        order = sorted(
            slot_map,
            key=lambda slot_id: (slots[slot_id]["setup_draw_order"], slot_id),
        )
        for slot_id in order:
            projected_attachments: dict[str, Any] = {}
            for attachment_id in sorted(slot_map[slot_id]):
                attachment = attachments[attachment_id]
                projected_attachments[attachment_id] = project_attachment(
                    attachment, slot_bone=slots[slot_id]["bone"], setup=setup,
                )
                membership.add(attachment_id)
            projected_slots[slot_id] = projected_attachments
        result.append({"name": skin_name, "attachments": projected_slots})
    if membership != set(attachments):
        raise Spine42ContractError("Every attachment must belong to a declared skin")
    default = rig["skins"]["default"]
    for slot in rig["slots"]:
        attachment = slot["setup_attachment"]
        if attachment is not None and attachment not in default.get(slot["id"], []):
            raise Spine42ContractError("Setup attachment must exist in the default skin")
    return result


def _project_motion(
    instance: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if instance is None:
        return {}, {}
    ticks_per_second = instance["timing"]["ticks_per_second"]
    bones: dict[str, dict[str, Any]] = {}
    for track in instance["tracks"]:
        frames: list[dict[str, Any]] = []
        for key in track["keys"]:
            frame: dict[str, Any] = {"time": _clean(key["tick"] / ticks_per_second)}
            if track["property"] == "rotation":
                frame["value"] = _clean(-float(key["value"]))
            else:
                frame["x"] = _clean(key["value"][0])
                frame["y"] = _clean(-float(key["value"][1]))
            frames.append(frame)
        timeline = "rotate" if track["property"] == "rotation" else "translate"
        bones.setdefault(track["bone_id"], {})[timeline] = frames
    event_names: set[str] = set()
    event_frames: list[dict[str, Any]] = []
    for marker in instance["markers"]:
        for boundary, tick in (
            ("start", marker["start_tick"]), ("end", marker["end_tick"]),
        ):
            name = f"contact.{marker['limb']}.{boundary}"
            event_names.add(name)
            event_frames.append({
                "time": _clean(tick / ticks_per_second), "name": name,
            })
    animation: dict[str, Any] = {"bones": bones}
    if event_frames:
        animation["events"] = sorted(
            event_frames, key=lambda item: (item["time"], item["name"])
        )
    return (
        {name: {} for name in sorted(event_names)},
        {instance["clip_id"]: animation},
    )


def _require_projected_document(document: Mapping[str, Any]) -> None:
    bones = document["bones"]
    ids: list[str] = []
    for bone in bones:
        parent = bone.get("parent")
        if parent is not None and parent not in ids:
            raise Spine42ContractError("Spine bone parent must precede its child")
        ids.append(bone["name"])
        _finite_values(bone)
    slot_ids = {slot["name"] for slot in document["slots"]}
    if any(slot["bone"] not in ids for slot in document["slots"]):
        raise Spine42ContractError("Spine slot references a missing bone")
    for skin in document["skins"]:
        for slot_id, attachments in skin["attachments"].items():
            if slot_id not in slot_ids:
                raise Spine42ContractError("Spine skin references a missing slot")
            for attachment in attachments.values():
                _require_projected_attachment(attachment, len(ids))
    canonical_spine42_json(document)


def _require_projected_attachment(attachment: Mapping[str, Any], bone_count: int) -> None:
    if attachment["type"] == "region":
        if attachment["width"] <= 0 or attachment["height"] <= 0:
            raise Spine42ContractError("Projected region size must be positive")
        _finite_values(attachment)
        return
    uvs, triangles, vertices = (
        attachment["uvs"], attachment["triangles"], attachment["vertices"]
    )
    if len(uvs) < 6 or len(uvs) % 2 or len(triangles) < 3 or len(triangles) % 3:
        raise Spine42ContractError("Projected mesh topology is invalid")
    vertex_count = len(uvs) // 2
    if any(type(index) is not int or not 0 <= index < vertex_count for index in triangles):
        raise Spine42ContractError("Projected triangle index is out of range")
    cursor = 0
    for _vertex in range(vertex_count):
        if cursor >= len(vertices) or type(vertices[cursor]) is not int:
            raise Spine42ContractError("Projected weighted vertex encoding is truncated")
        influence_count = vertices[cursor]
        cursor += 1
        if not 1 <= influence_count <= 4:
            raise Spine42ContractError("Projected influence count is invalid")
        total = 0.0
        for _influence in range(influence_count):
            if cursor + 3 >= len(vertices):
                raise Spine42ContractError("Projected weighted vertex encoding is truncated")
            bone, x, y, weight = vertices[cursor:cursor + 4]
            if type(bone) is not int or not 0 <= bone < bone_count \
                    or not all(_finite(value) for value in (x, y, weight)) \
                    or weight <= 0:
                raise Spine42ContractError("Projected mesh influence is invalid")
            total += float(weight)
            cursor += 4
        if not math.isclose(total, 1.0, abs_tol=1e-5):
            raise Spine42ContractError("Projected mesh weights do not sum to one")
    if cursor != len(vertices):
        raise Spine42ContractError("Projected weighted vertex encoding has trailing data")
    _finite_values(attachment)


def _finite_values(value: Any) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _finite_values(item)
    elif isinstance(value, list):
        for item in value:
            _finite_values(item)
    elif isinstance(value, (int, float)) and not isinstance(value, bool) and not _finite(value):
        raise Spine42ContractError("Projected Spine JSON contains a non-finite number")


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(float(value))


def _clean(value: Any) -> float:
    result = float(value)
    return 0.0 if abs(result) <= 1e-12 else result
