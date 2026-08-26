"""Deterministic reviewed slot-relation merge with setup-order tie breaks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


MAX_SLOTS = 4096
MAX_RELATIONS = 4096


class MotionPolicyDrawOrderError(ValueError):
    """Raised when reviewed pair relations cannot form one slot permutation."""


def merge_draw_order_relations(
    setup_order: Sequence[str], relations: Sequence[Mapping[str, Any]]
) -> tuple[str, ...]:
    """Topologically sort back→front edges using setup order as the tie-break."""

    setup = _setup(setup_order)
    if not isinstance(relations, Sequence) or isinstance(relations, (str, bytes)) \
            or len(relations) > MAX_RELATIONS:
        raise MotionPolicyDrawOrderError("Draw-order relation inventory is invalid")
    setup_index = {slot_id: index for index, slot_id in enumerate(setup)}
    outgoing = {slot_id: set() for slot_id in setup}
    indegree = {slot_id: 0 for slot_id in setup}
    seen: set[tuple[str, str]] = set()
    for raw in relations:
        if not isinstance(raw, Mapping) \
                or set(raw) != {"back_slot", "front_slot"}:
            raise MotionPolicyDrawOrderError("Draw-order relation fields are invalid")
        edge = raw.get("back_slot"), raw.get("front_slot")
        if edge[0] not in setup_index or edge[1] not in setup_index \
                or edge[0] == edge[1] or edge in seen:
            raise MotionPolicyDrawOrderError("Draw-order relation is invalid or duplicated")
        seen.add(edge)
        outgoing[str(edge[0])].add(str(edge[1]))
        indegree[str(edge[1])] += 1
    available = [slot for slot in setup if indegree[slot] == 0]
    result = []
    while available:
        available.sort(key=setup_index.__getitem__)
        slot = available.pop(0)
        result.append(slot)
        for front in sorted(outgoing[slot], key=setup_index.__getitem__):
            indegree[front] -= 1
            if indegree[front] == 0:
                available.append(front)
    if len(result) != len(setup):
        raise MotionPolicyDrawOrderError(
            "Reviewed draw-order relations contain a cycle"
        )
    return tuple(result)


def pair_relation(slot_ids: Sequence[str], front_slot: str) -> dict[str, str]:
    """Build one explicit back→front edge from a reviewed two-slot choice."""

    if not isinstance(slot_ids, Sequence) or isinstance(slot_ids, (str, bytes)) \
            or len(slot_ids) != 2 or len(set(slot_ids)) != 2 \
            or front_slot not in slot_ids:
        raise MotionPolicyDrawOrderError("Draw-order pair choice is invalid")
    back = slot_ids[1] if front_slot == slot_ids[0] else slot_ids[0]
    return {"back_slot": str(back), "front_slot": str(front_slot)}


def _setup(value) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) \
            or not 1 <= len(value) <= MAX_SLOTS:
        raise MotionPolicyDrawOrderError("Setup draw order is invalid")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result) \
            or len(set(result)) != len(result):
        raise MotionPolicyDrawOrderError("Setup draw order must be unique")
    return result
