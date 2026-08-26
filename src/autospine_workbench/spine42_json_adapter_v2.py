"""Policy-aware MotionInstance v2 to Spine 4.2 JSON conversion."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .resolved_project import canonical_sha256
from .spine42_contract import Spine42ContractError, canonical_spine42_json
from .spine42_contract_v2 import (
    Spine42ContractV2Error,
    require_spine42_inputs_v2,
    spine42_target_profile_v2,
)
from .spine42_draw_order_offsets import (
    Spine42DrawOrderOffsetError,
    apply_spine42_draw_order_offsets,
    encode_spine42_draw_order_offsets,
)
from .spine42_json_adapter import build_spine42_json


def build_spine42_json_v2(
    rig: Mapping[str, Any],
    *,
    motion_instance: Mapping[str, Any],
    target_profile: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one deterministic policy-aware Spine 4.2 JSON document."""

    require_spine42_inputs_v2(
        rig,
        motion_instance=motion_instance,
        target_profile=target_profile,
    )
    try:
        document = build_spine42_json(rig)
    except Spine42ContractError as exc:
        raise Spine42ContractV2Error(
            f"Spine 4.2 adapter v2 setup projection failed: {exc}"
        ) from exc
    events, animation = _project_motion(motion_instance, document["slots"])
    document["events"] = events
    document["animations"] = {motion_instance["clip_id"]: animation}
    document["skeleton"]["hash"] = canonical_sha256({
        "adapter_profile": spine42_target_profile_v2(),
        "rig_sha256": canonical_sha256(rig),
        "motion_instance_v2_sha256": canonical_sha256(motion_instance),
        "target_profile_sha256": canonical_sha256(target_profile),
    })
    try:
        return json.loads(canonical_spine42_json(document))
    except (TypeError, ValueError) as exc:
        raise Spine42ContractV2Error(
            f"Projected Spine 4.2 adapter v2 document is invalid: {exc}"
        ) from exc


def build_spine42_json_bytes_v2(
    rig: Mapping[str, Any],
    *,
    motion_instance: Mapping[str, Any],
    target_profile: Mapping[str, Any],
) -> bytes:
    """Build and canonically serialize one adapter v2 result."""

    return canonical_spine42_json(build_spine42_json_v2(
        rig,
        motion_instance=motion_instance,
        target_profile=target_profile,
    ))


def _project_motion(
    instance: Mapping[str, Any],
    slots: list[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    ticks_per_second = instance["timing"]["ticks_per_second"]
    animation: dict[str, Any] = {
        "bones": _project_bones(instance, ticks_per_second),
    }
    event_names, event_frames = _project_events(instance, ticks_per_second)
    if event_frames:
        animation["events"] = event_frames
    animation["drawOrder"] = _project_draw_order(
        instance, slots, ticks_per_second
    )
    return ({name: {} for name in event_names}, animation)


def _project_bones(
    instance: Mapping[str, Any], ticks_per_second: int
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for track in instance["tracks"]:
        frames: list[dict[str, Any]] = []
        for key in track["keys"]:
            frame: dict[str, Any] = {
                "time": _clean(key["tick"] / ticks_per_second)
            }
            if track["property"] == "rotation":
                frame["value"] = _clean(-float(key["value"]))
            else:
                frame["x"] = _clean(key["value"][0])
                frame["y"] = _clean(-float(key["value"][1]))
            frames.append(frame)
        timeline = "rotate" if track["property"] == "rotation" else "translate"
        result.setdefault(track["bone_id"], {})[timeline] = frames
    return result


def _project_events(
    instance: Mapping[str, Any], ticks_per_second: int
) -> tuple[list[str], list[dict[str, Any]]]:
    names: set[str] = set()
    frames: list[dict[str, Any]] = []
    for marker in instance["markers"]:
        for boundary, tick in (
            ("start", marker["start_tick"]),
            ("end", marker["end_tick"]),
        ):
            name = f"contact.{marker['limb']}.{boundary}"
            names.add(name)
            frames.append({
                "time": _clean(tick / ticks_per_second),
                "name": name,
            })
    return sorted(names), sorted(
        frames, key=lambda item: (item["time"], item["name"])
    )


def _project_draw_order(
    instance: Mapping[str, Any],
    slots: list[Mapping[str, Any]],
    ticks_per_second: int,
) -> list[dict[str, Any]]:
    setup = tuple(slot["name"] for slot in slots)
    policy = instance["draw_order"]
    if tuple(policy["setup_slot_ids"]) != setup:
        raise Spine42ContractV2Error(
            "MotionInstance v2 setup slots differ from projected Spine slots"
        )
    frames: list[dict[str, Any]] = []
    try:
        for key in policy["keys"]:
            target = tuple(key["slot_ids"])
            offsets = encode_spine42_draw_order_offsets(setup, target)
            frame: dict[str, Any] = {
                "time": _clean(key["tick"] / ticks_per_second)
            }
            if offsets:
                frame["offsets"] = offsets
            if apply_spine42_draw_order_offsets(
                setup, frame.get("offsets", [])
            ) != target:
                raise Spine42ContractV2Error(
                    "Spine drawOrder frame failed exact replay"
                )
            frames.append(frame)
    except Spine42DrawOrderOffsetError as exc:
        raise Spine42ContractV2Error(
            f"MotionInstance v2 draw order is not representable: {exc}"
        ) from exc
    return frames


def _clean(value: Any) -> float:
    result = float(value)
    return 0.0 if abs(result) <= 1e-12 else result
