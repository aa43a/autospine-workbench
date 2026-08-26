"""Pure, contract-neutral timeline projection into Spine 4.2 JSON fields."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .spine42_draw_order_offsets import (
    Spine42DrawOrderOffsetError,
    apply_spine42_draw_order_offsets,
    encode_spine42_draw_order_offsets,
)


class Spine42TimelineProjectionError(ValueError):
    """Raised when an admitted timeline is not representable in Spine 4.2."""


def project_spine42_motion(
    instance: Mapping[str, Any],
    slots: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Project already-admitted motion without assigning it a public contract."""

    ticks_per_second = instance["timing"]["ticks_per_second"]
    animation: dict[str, Any] = {
        "bones": project_spine42_bones(
            instance["tracks"], ticks_per_second=ticks_per_second
        ),
    }
    event_names, event_frames = project_spine42_events(
        instance["markers"], ticks_per_second=ticks_per_second
    )
    if event_frames:
        animation["events"] = event_frames
    animation["drawOrder"] = project_spine42_draw_order(
        instance["draw_order"], slots, ticks_per_second=ticks_per_second
    )
    return ({name: {} for name in event_names}, animation)


def project_spine42_bones(
    tracks: Sequence[Mapping[str, Any]], *, ticks_per_second: int,
) -> dict[str, dict[str, Any]]:
    """Project admitted rotation and translation tracks."""

    result: dict[str, dict[str, Any]] = {}
    for track in tracks:
        frames: list[dict[str, Any]] = []
        for key in track["keys"]:
            frame: dict[str, Any] = {
                "time": clean_spine42_number(key["tick"] / ticks_per_second)
            }
            if track["property"] == "rotation":
                frame["value"] = clean_spine42_number(-float(key["value"]))
            else:
                frame["x"] = clean_spine42_number(key["value"][0])
                frame["y"] = clean_spine42_number(-float(key["value"][1]))
            frames.append(frame)
        timeline = "rotate" if track["property"] == "rotation" else "translate"
        result.setdefault(track["bone_id"], {})[timeline] = frames
    return result


def project_spine42_events(
    markers: Sequence[Mapping[str, Any]], *, ticks_per_second: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Project admitted contact marker boundaries."""

    names: set[str] = set()
    frames: list[dict[str, Any]] = []
    for marker in markers:
        for boundary, tick in (
            ("start", marker["start_tick"]),
            ("end", marker["end_tick"]),
        ):
            name = f"contact.{marker['limb']}.{boundary}"
            names.add(name)
            frames.append({
                "time": clean_spine42_number(tick / ticks_per_second),
                "name": name,
            })
    return sorted(names), sorted(
        frames, key=lambda item: (item["time"], item["name"])
    )


def project_spine42_draw_order(
    policy: Mapping[str, Any],
    slots: Sequence[Mapping[str, Any]],
    *,
    ticks_per_second: int,
) -> list[dict[str, Any]]:
    """Project full slot orders and prove every offset frame replays exactly."""

    setup = tuple(slot["name"] for slot in slots)
    if tuple(policy["setup_slot_ids"]) != setup:
        raise Spine42TimelineProjectionError(
            "Motion setup slots differ from projected Spine slots"
        )
    frames: list[dict[str, Any]] = []
    try:
        for key in policy["keys"]:
            target = tuple(key["slot_ids"])
            offsets = encode_spine42_draw_order_offsets(setup, target)
            frame: dict[str, Any] = {
                "time": clean_spine42_number(key["tick"] / ticks_per_second)
            }
            if offsets:
                frame["offsets"] = offsets
            if apply_spine42_draw_order_offsets(
                setup, frame.get("offsets", [])
            ) != target:
                raise Spine42TimelineProjectionError(
                    "Spine drawOrder frame failed exact replay"
                )
            frames.append(frame)
    except Spine42DrawOrderOffsetError as exc:
        raise Spine42TimelineProjectionError(
            f"Motion draw order is not representable: {exc}"
        ) from exc
    return frames


def clean_spine42_number(value: Any) -> float:
    """Normalize negative zero while retaining the historical adapter values."""

    result = float(value)
    return 0.0 if abs(result) <= 1e-12 else result
