"""Deterministic Spine 4.2 timeline-semantic replay for adapter v2."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any

from .motion_roles import CANONICAL_BONE_ID_BY_ROLE
from .spine42_contract import canonical_spine42_json, spine42_json_sha256
from .spine42_draw_order_offsets import (
    Spine42DrawOrderOffsetError,
    apply_spine42_draw_order_offsets,
)


FORMAT = "autospine-spine42-v2-runtime-semantics-audit"
FORMAT_VERSION = 1
TICKS_PER_SECOND = 1_000_000
ROOT_BONE_ID = CANONICAL_BONE_ID_BY_ROLE["humanoid.root"]
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SEMANTICS = {
    "scope": "timeline-semantics-only",
    "draw_order": "spine-4.2-loader-offset-replay-stepped",
    "root_translation": "spine-local-xy-linear",
    "spine_y_axis": "up",
    "official_runtime_loaded": False,
    "raster_truth_claimed": False,
}


class Spine42V2RuntimeSemanticsError(ValueError):
    """Raised when adapter output cannot be replayed unambiguously."""


@dataclass(frozen=True, slots=True)
class Spine42V2RuntimeSemanticsAudit:
    """Frozen canonical timeline audit with isolated document access."""

    _canonical_json: str
    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)
    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")
    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def audit_spine42_v2_runtime_semantics(
    skeleton: Mapping[str, Any],
    clip_id: str,
    ticks: list[int],
    *,
    timing: Mapping[str, Any],
) -> Spine42V2RuntimeSemanticsAudit:
    """Replay draw order and root translation at explicit integer ticks."""

    try:
        canonical_spine42_json(skeleton)
        tick_rate, duration, loop = _timing(timing)
        query_ticks = _query_ticks(ticks, duration, loop)
        if not isinstance(clip_id, str) or not _ID.fullmatch(clip_id):
            raise Spine42V2RuntimeSemanticsError("Clip id is invalid")
        setup = _setup_slots(skeleton)
        animation = _animation(skeleton, clip_id)
        draw_keys = _draw_keys(animation, setup, tick_rate, duration)
        root_keys = _root_keys(animation, tick_rate, duration)
        _require_loop_boundary(draw_keys, root_keys, setup, duration, loop)
        samples = [
            _sample(tick, tick_rate, setup, draw_keys, root_keys)
            for tick in query_ticks
        ]
        wrap_sample = None
        if loop:
            first = samples[0]
            wrap_sample = {
                "cycle": 1,
                "tick": 0,
                "time": 0.0,
                "slot_ids": list(first["slot_ids"]),
                "root_xy": list(first["root_xy"]),
            }
            if wrap_sample["slot_ids"] != list(setup) \
                    or wrap_sample["root_xy"] != samples[0]["root_xy"]:
                raise Spine42V2RuntimeSemanticsError(
                    "Loop wrap differs from cycle-zero tick zero"
                )
        report = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "clip_id": clip_id,
            "source": {"skeleton_json_sha256": spine42_json_sha256(skeleton)},
            "timing": {
                "ticks_per_second": tick_rate,
                "duration_ticks": duration,
                "loop": loop,
            },
            "semantics": dict(SEMANTICS),
            "setup_slot_ids": list(setup),
            "samples": samples,
            "wrap_sample": wrap_sample,
        }
        return Spine42V2RuntimeSemanticsAudit(_canonical(report))
    except Spine42V2RuntimeSemanticsError:
        raise
    except (
        KeyError, OverflowError, Spine42DrawOrderOffsetError,
        TypeError, ValueError,
    ) as exc:
        raise Spine42V2RuntimeSemanticsError(
            f"Spine 4.2 v2 runtime-semantic audit failed: {exc}"
        ) from exc


def _timing(value: Any) -> tuple[int, int, bool]:
    row = _mapping(value, "timing")
    if set(row) != {"ticks_per_second", "duration_ticks", "loop"} \
            or row.get("ticks_per_second") != TICKS_PER_SECOND \
            or type(row.get("duration_ticks")) is not int \
            or not 1 <= row["duration_ticks"] <= 600 * TICKS_PER_SECOND \
            or type(row.get("loop")) is not bool:
        raise Spine42V2RuntimeSemanticsError("Timing is invalid")
    return TICKS_PER_SECOND, row["duration_ticks"], row["loop"]
def _query_ticks(value: Any, duration: int, loop: bool) -> list[int]:
    if not isinstance(value, list) or not 1 <= len(value) <= 4096 \
            or any(type(tick) is not int for tick in value) \
            or any(not 0 <= tick <= duration for tick in value) \
            or any(right <= left for left, right in zip(value, value[1:])):
        raise Spine42V2RuntimeSemanticsError(
            "Query ticks must be sorted, unique, and inside the clip"
        )
    if value[0] != 0 or (loop and value[-1] != duration):
        raise Spine42V2RuntimeSemanticsError(
            "Query ticks must include tick zero and loop duration"
        )
    return list(value)
def _setup_slots(skeleton: Mapping[str, Any]) -> tuple[str, ...]:
    rows = skeleton.get("slots")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 4096:
        raise Spine42V2RuntimeSemanticsError("Setup slots are invalid")
    result = tuple(
        _identifier(_mapping(row, "slot").get("name"), "slot name")
        for row in rows
    )
    if len(set(result)) != len(result):
        raise Spine42V2RuntimeSemanticsError("Setup slots must be unique")
    return result
def _animation(skeleton: Mapping[str, Any], clip_id: str) -> Mapping[str, Any]:
    animations = _mapping(skeleton.get("animations"), "animations")
    animation = _mapping(animations.get(clip_id), "animation")
    aliases = {
        key for key in animation
        if isinstance(key, str) and key.lower().replace("_", "") == "draworder"
    }
    if aliases != {"drawOrder"}:
        raise Spine42V2RuntimeSemanticsError(
            "Animation must use the Spine drawOrder camelCase timeline"
        )
    return animation
def _draw_keys(animation, setup, tick_rate, duration):
    rows = animation.get("drawOrder")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 4096:
        raise Spine42V2RuntimeSemanticsError("drawOrder timeline is invalid")
    result, previous = [], -1
    for raw in rows:
        row = _mapping(raw, "drawOrder key")
        if set(row) not in ({"time"}, {"time", "offsets"}):
            raise Spine42V2RuntimeSemanticsError(
                "drawOrder key fields are invalid"
            )
        tick = _frame_tick(row.get("time"), tick_rate, duration)
        if tick <= previous:
            raise Spine42V2RuntimeSemanticsError(
                "drawOrder keys must be strictly increasing"
            )
        offsets = row.get("offsets", [])
        if not isinstance(offsets, list):
            raise Spine42V2RuntimeSemanticsError(
                "drawOrder offsets must be a JSON array"
            )
        order = apply_spine42_draw_order_offsets(setup, offsets)
        result.append((tick, order))
        previous = tick
    if result[0] != (0, setup):
        raise Spine42V2RuntimeSemanticsError(
            "drawOrder must key setup order at tick zero"
        )
    return result
def _root_keys(animation, tick_rate, duration):
    bones = _mapping(animation.get("bones"), "animation bones")
    root = _mapping(bones.get(ROOT_BONE_ID), "root bone timeline")
    rows = root.get("translate")
    if not isinstance(rows, list) or not 2 <= len(rows) <= 4096:
        raise Spine42V2RuntimeSemanticsError("Root translate timeline is invalid")
    result, previous = [], -1
    for raw in rows:
        row = _mapping(raw, "root translate key")
        if set(row) != {"time", "x", "y"}:
            raise Spine42V2RuntimeSemanticsError(
                "Root translate key fields are invalid"
            )
        tick = _frame_tick(row.get("time"), tick_rate, duration)
        if tick <= previous:
            raise Spine42V2RuntimeSemanticsError(
                "Root translate keys must be strictly increasing"
            )
        result.append((tick, (_number(row["x"]), _number(row["y"]))))
        previous = tick
    if result[0][0] != 0 or result[-1][0] != duration:
        raise Spine42V2RuntimeSemanticsError(
            "Root translate must key tick zero and duration"
        )
    return result
def _require_loop_boundary(draw, root, setup, duration, loop):
    if not loop:
        return
    dynamic = any(order != setup for _tick, order in draw)
    duration_order = _sample_stepped(draw, duration)
    if duration_order != setup or (dynamic and draw[-1] != (duration, setup)):
        raise Spine42V2RuntimeSemanticsError(
            "Dynamic loop drawOrder must explicitly reset at duration"
        )
    if root[0][1] != root[-1][1]:
        raise Spine42V2RuntimeSemanticsError(
            "Loop root translate does not reset at duration"
        )
def _sample(tick, tick_rate, setup, draw, root):
    return {
        "tick": tick,
        "time": _clean(tick / tick_rate),
        "slot_ids": list(_sample_stepped(draw, tick) or setup),
        "root_xy": _sample_linear(root, tick),
    }
def _sample_stepped(keys, tick):
    value = None
    for key_tick, key_value in keys:
        if key_tick > tick:
            break
        value = key_value
    return value
def _sample_linear(keys, tick):
    for index, (right_tick, right) in enumerate(keys):
        if right_tick == tick:
            return [_clean(right[0]), _clean(right[1])]
        if right_tick > tick:
            left_tick, left = keys[index - 1]
            ratio = (tick - left_tick) / (right_tick - left_tick)
            return [
                _clean(left[0] + (right[0] - left[0]) * ratio),
                _clean(left[1] + (right[1] - left[1]) * ratio),
            ]
    raise Spine42V2RuntimeSemanticsError("Root sample is outside its key span")
def _frame_tick(value, tick_rate, duration):
    number = _number(value)
    scaled, tick = number * tick_rate, round(number * tick_rate)
    if abs(scaled - tick) > 1e-6 or not 0 <= tick <= duration:
        raise Spine42V2RuntimeSemanticsError(
            "Spine frame time is off the integer tick schedule"
        )
    return int(tick)
def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise Spine42V2RuntimeSemanticsError("Spine timeline number is invalid")
    return float(value)
def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise Spine42V2RuntimeSemanticsError(f"{label} is invalid")
    return value
def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Spine42V2RuntimeSemanticsError(f"{label} must be an object")
    return value
def _clean(value: float) -> float:
    result = round(float(value), 9)
    return 0.0 if result == 0 else result
def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
