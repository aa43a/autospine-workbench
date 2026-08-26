"""Project reviewed depth decisions into deterministic full slot permutations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .motion_policy_candidate_inventory import (
    MotionPolicyCandidateInventoryError,
    derive_motion_policy_candidates,
)
from .motion_policy_decision_validation import (
    MotionPolicyDecisionValidationError,
    require_motion_policy_decision,
)
from .motion_policy_draw_order import (
    MotionPolicyDrawOrderError,
    merge_draw_order_relations,
    pair_relation,
)


class ReviewedDrawOrderError(ValueError):
    """Raised when reviewed depth choices cannot form one safe timeline."""


def compile_reviewed_slot_order(
    decision: Mapping[str, Any],
    foot_candidates: Mapping[str, Any],
    depth_candidates: Mapping[str, Any],
    setup_slot_ids: Sequence[str],
) -> dict[str, Any]:
    """Compile reviewed pair choices without inferring missing authority."""

    try:
        require_motion_policy_decision(
            decision,
            foot_candidates=foot_candidates,
            depth_candidates=depth_candidates,
        )
        inventory = derive_motion_policy_candidates(
            foot_candidates, depth_candidates
        )
        return _compile(decision, depth_candidates, inventory, setup_slot_ids)
    except ReviewedDrawOrderError:
        raise
    except (
        MotionPolicyCandidateInventoryError,
        MotionPolicyDecisionValidationError,
        MotionPolicyDrawOrderError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise ReviewedDrawOrderError(
            f"Reviewed draw-order projection failed: {exc}"
        ) from exc


def _compile(decision, depth, inventory, setup_slot_ids):
    setup = merge_draw_order_relations(setup_slot_ids, ())
    decisions = {row["candidate_id"]: row for row in decision["decisions"]}
    candidates = _depth_candidates(inventory)
    relations: dict[str, dict[str, str]] = {}
    events_by_tick: dict[int, list[tuple[str, str]]] = defaultdict(list)
    consumed: set[str] = set()
    seen_pair_ticks: set[tuple[str, int]] = set()
    for pair in depth["pairs"]:
        pair_id = pair["pair_id"]
        slots = tuple(row["slot_id"] for row in pair["slots"])
        relations[pair_id] = pair_relation(slots, pair["setup_front_slot"])
        for event_index, event in enumerate(pair["events"]):
            tick = event["tick"]
            identity = pair_id, tick
            if identity in seen_pair_ticks:
                raise ReviewedDrawOrderError(
                    "A depth pair has repeated events at one tick"
                )
            seen_pair_ticks.add(identity)
            candidate = candidates.get((pair_id, event_index))
            if candidate is None or candidate.candidate_id in consumed \
                    or candidate.tick != tick \
                    or candidate.depth_slots != slots \
                    or candidate.depth_to_front_slot != event["to_front_slot"]:
                raise ReviewedDrawOrderError(
                    "Depth event does not map to one unique candidate"
                )
            consumed.add(candidate.candidate_id)
            row = decisions[candidate.candidate_id]
            front = _reviewed_front(row, event, slots)
            events_by_tick[tick].append((pair_id, front))
    if consumed != {row.candidate_id for row in candidates.values()}:
        raise ReviewedDrawOrderError(
            "Depth candidate inventory does not match its events"
        )
    initial = merge_draw_order_relations(setup, _ordered(relations))
    if initial != setup:
        raise ReviewedDrawOrderError(
            "Reviewed pair setup relations differ from setup slot order"
        )
    keys = [{"tick": 0, "slot_ids": list(setup)}]
    current = initial
    for tick in sorted(events_by_tick):
        for pair_id, front in sorted(events_by_tick[tick]):
            if front:
                slots = _relation_slots(relations[pair_id])
                relations[pair_id] = pair_relation(slots, front)
        projected = merge_draw_order_relations(setup, _ordered(relations))
        if projected != current:
            if tick == 0:
                raise ReviewedDrawOrderError(
                    "Reviewed draw order cannot replace setup at tick zero"
                )
            keys.append({"tick": tick, "slot_ids": list(projected)})
            current = projected
    _append_loop_reset(decision, depth, setup, current, events_by_tick, keys)
    return {"setup_slot_ids": list(setup), "keys": keys}


def _depth_candidates(inventory):
    result = {}
    for candidate in inventory.candidates:
        if candidate.kind != "depth_order":
            continue
        key = candidate.depth_pair_id, candidate.depth_event_index
        if key in result:
            raise ReviewedDrawOrderError(
                "Depth candidate event mapping is ambiguous"
            )
        result[key] = candidate
    return result


def _reviewed_front(row, event, slots):
    action = row["action"]
    if action == "accept":
        return event["to_front_slot"]
    if action == "adjust":
        return row["payload"]["final_front_slot"]
    if action in {"reject", "unobservable"}:
        return ""
    raise ReviewedDrawOrderError("Depth decision action is unsupported")


def _relation_slots(relation):
    return relation["back_slot"], relation["front_slot"]


def _ordered(relations):
    return [relations[pair_id] for pair_id in sorted(relations)]


def _append_loop_reset(
    decision, depth, setup, current, events_by_tick, keys
) -> None:
    if not depth["timing"]["loop"] or current == setup:
        return
    if not decision["draw_order_loop_reset"]["approved"]:
        raise ReviewedDrawOrderError(
            "A non-setup loop end requires explicit draw-order reset approval"
        )
    duration = depth["timing"]["duration_ticks"]
    if any(front for _pair_id, front in events_by_tick.get(duration, ())):
        raise ReviewedDrawOrderError(
            "A draw-order event conflicts with the approved loop reset tick"
        )
    keys.append({"tick": duration, "slot_ids": list(setup)})
