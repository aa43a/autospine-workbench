"""Lossless full-permutation encoding for Spine 4.2 draworder offsets."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


MAX_SLOTS = 4096


class Spine42DrawOrderOffsetError(ValueError):
    """Raised when a slot permutation or offset list is ambiguous."""


def encode_spine42_draw_order_offsets(
    setup_order: Sequence[str], target_order: Sequence[str]
) -> list[dict[str, Any]]:
    """Encode every setup slot, making any reviewed permutation lossless."""

    setup, target = _permutations(setup_order, target_order)
    if setup == target:
        return []
    target_index = {slot_id: index for index, slot_id in enumerate(target)}
    offsets = [
        {"slot": slot_id, "offset": target_index[slot_id] - setup_index}
        for setup_index, slot_id in enumerate(setup)
    ]
    if apply_spine42_draw_order_offsets(setup, offsets) != target:
        raise Spine42DrawOrderOffsetError(
            "Spine draw-order offset roundtrip is inconsistent"
        )
    return offsets


def apply_spine42_draw_order_offsets(
    setup_order: Sequence[str], offsets: Sequence[dict[str, Any]]
) -> tuple[str, ...]:
    """Replay the Spine JSON loader's unchanged-slot fill algorithm."""

    setup = _order(setup_order, "setup order")
    if not isinstance(offsets, Sequence) or isinstance(offsets, (str, bytes)):
        raise Spine42DrawOrderOffsetError("Spine draw-order offsets are invalid")
    if len(offsets) > len(setup):
        raise Spine42DrawOrderOffsetError("Spine draw-order offset limit exceeded")
    by_slot = {slot_id: index for index, slot_id in enumerate(setup)}
    draw_order: list[int | None] = [None] * len(setup)
    unchanged: list[int] = []
    original = 0
    for raw in offsets:
        if not isinstance(raw, dict) or set(raw) != {"slot", "offset"}:
            raise Spine42DrawOrderOffsetError(
                "Spine draw-order offset fields are invalid"
            )
        slot_index = by_slot.get(raw.get("slot"))
        offset = raw.get("offset")
        if slot_index is None or slot_index < original \
                or type(offset) is not int:
            raise Spine42DrawOrderOffsetError(
                "Spine draw-order offsets must follow setup slot order"
            )
        while original < slot_index:
            unchanged.append(original)
            original += 1
        destination = original + offset
        if not 0 <= destination < len(setup) \
                or draw_order[destination] is not None:
            raise Spine42DrawOrderOffsetError(
                "Spine draw-order offset destination is invalid"
            )
        draw_order[destination] = original
        original += 1
    while original < len(setup):
        unchanged.append(original)
        original += 1
    for index in range(len(draw_order) - 1, -1, -1):
        if draw_order[index] is None:
            if not unchanged:
                raise Spine42DrawOrderOffsetError(
                    "Spine draw-order unchanged inventory is inconsistent"
                )
            draw_order[index] = unchanged.pop()
    if unchanged or any(index is None for index in draw_order):
        raise Spine42DrawOrderOffsetError(
            "Spine draw-order offsets do not form a permutation"
        )
    return tuple(setup[int(index)] for index in draw_order)


def _permutations(setup_order, target_order):
    setup = _order(setup_order, "setup order")
    target = _order(target_order, "target order")
    if set(setup) != set(target):
        raise Spine42DrawOrderOffsetError(
            "Spine setup and target slot inventories differ"
        )
    return setup, target


def _order(value, label) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) \
            or not 1 <= len(value) <= MAX_SLOTS:
        raise Spine42DrawOrderOffsetError(f"Spine {label} is invalid")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result) \
            or len(set(result)) != len(result):
        raise Spine42DrawOrderOffsetError(f"Spine {label} is not unique")
    return result
