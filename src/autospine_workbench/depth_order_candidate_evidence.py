"""Pair/sample math for candidate-only depth-order evidence."""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
from typing import Any

from .depth_order_schmitt import evaluate_depth_pair, quantize_depth_score


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PAIR = {"pair_id", "slots", "setup_front_slot", "samples", "events"}
_SAMPLE = {
    "source_frame_index", "tick", "scores",
    "score_delta_first_minus_second", "current_front_slot",
    "pending_front_slot", "pending_frame_count", "state",
}
_SCORE = {
    "slot_id", "depth_role", "midpoint_depth_root_relative_normalized",
    "front_score",
}


class DepthOrderEvidenceError(ValueError):
    """Raised when derived pair evidence is structurally inconsistent."""


def validate_candidate_pairs(value, frames, sign, hysteresis):
    """Return pair/sample/event counts after recomputing all derived math."""

    pairs = _array(value, "Depth-order pairs")
    if not 1 <= len(pairs) <= 64:
        raise DepthOrderEvidenceError("Depth-order pair count is invalid")
    previous, samples_total, events_total = None, 0, 0
    for raw in pairs:
        pair = _object(raw, "Depth-order pair")
        _exact(pair, _PAIR, "Depth-order pair")
        pair_id = _identifier(pair.get("pair_id"), "pair_id")
        if previous is not None and pair_id <= previous:
            raise DepthOrderEvidenceError(
                "Depth-order pairs must be sorted and unique"
            )
        previous = pair_id
        slots = _slots(pair.get("slots"))
        setup = pair.get("setup_front_slot")
        slot_ids = slots[0]["slot_id"], slots[1]["slot_id"]
        if setup not in slot_ids:
            raise DepthOrderEvidenceError(
                "Depth-order setup front slot is invalid"
            )
        score_rows, states = _samples(
            pair.get("samples"), slots, frames, sign
        )
        expected_states, expected_events = evaluate_depth_pair(
            score_rows,
            slot_ids=slot_ids,
            setup_front_slot=setup,
            enter_threshold=hysteresis[0],
            exit_threshold=hysteresis[1],
            minimum_hold_frames=hysteresis[2],
        )
        if states != expected_states or pair.get("events") != expected_events:
            raise DepthOrderEvidenceError(
                "Depth-order Schmitt evidence is inconsistent"
            )
        samples_total += len(score_rows)
        events_total += len(expected_events)
    return len(pairs), samples_total, events_total


def _slots(value):
    rows = _array(value, "Depth-order pair slots")
    if len(rows) != 2:
        raise DepthOrderEvidenceError(
            "Depth-order pair must contain two slots"
        )
    for row in rows:
        _exact(
            _object(row, "Depth-order slot"),
            {"slot_id", "depth_role"},
            "Depth-order slot",
        )
        _identifier(row.get("slot_id"), "slot_id")
        _identifier(row.get("depth_role"), "depth_role")
    if rows[0]["slot_id"] >= rows[1]["slot_id"]:
        raise DepthOrderEvidenceError(
            "Depth-order slots must be sorted and distinct"
        )
    return rows


def _samples(value, slots, frames, sign):
    rows = _array(value, "Depth-order samples")
    if len(rows) != frames[0]:
        raise DepthOrderEvidenceError(
            "Depth-order sample count differs from timing"
        )
    score_rows, states, previous_tick = [], [], -1
    for index, raw in enumerate(rows):
        sample = _object(raw, "Depth-order sample")
        _exact(sample, _SAMPLE, "Depth-order sample")
        tick = sample.get("tick")
        if sample.get("source_frame_index") != index \
                or type(tick) is not int or tick <= previous_tick \
                or tick > frames[1]:
            raise DepthOrderEvidenceError(
                "Depth-order sample frame identity is invalid"
            )
        previous_tick = tick
        scores = _scores(sample.get("scores"), slots, sign)
        delta = quantize_depth_score(
            scores[slots[0]["slot_id"]] - scores[slots[1]["slot_id"]]
        )
        if sample.get("score_delta_first_minus_second") != delta:
            raise DepthOrderEvidenceError(
                "Depth-order pair score delta is inconsistent"
            )
        score_rows.append({
            "source_frame_index": index,
            "tick": tick,
            "scores": scores,
        })
        states.append({field: sample.get(field) for field in (
            "current_front_slot", "pending_front_slot",
            "pending_frame_count", "state",
        )})
    if rows[0]["tick"] != 0 or rows[-1]["tick"] != frames[1]:
        raise DepthOrderEvidenceError(
            "Depth-order samples must span the clip"
        )
    return score_rows, states


def _scores(value, slots, sign):
    rows = _array(value, "Depth-order scores")
    if len(rows) != 2:
        raise DepthOrderEvidenceError(
            "Depth-order score inventory is invalid"
        )
    result = {}
    for expected, score in zip(slots, rows):
        row = _object(score, "Depth-order score")
        _exact(row, _SCORE, "Depth-order score")
        if (row.get("slot_id"), row.get("depth_role")) != (
            expected["slot_id"], expected["depth_role"]
        ):
            raise DepthOrderEvidenceError(
                "Depth-order score binding is inconsistent"
            )
        midpoint = _number(
            row.get("midpoint_depth_root_relative_normalized"), "midpoint"
        )
        expected_score = quantize_depth_score(midpoint * sign)
        if row.get("front_score") != expected_score:
            raise DepthOrderEvidenceError(
                "Depth-order front score math is inconsistent"
            )
        result[row["slot_id"]] = expected_score
    return result


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or abs(float(value)) > 1024:
        raise DepthOrderEvidenceError(f"Depth-order {label} is invalid")
    return float(value)


def _identifier(value, label):
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise DepthOrderEvidenceError(f"Depth-order {label} is invalid")
    return value


def _object(value, label):
    if not isinstance(value, Mapping):
        raise DepthOrderEvidenceError(f"{label} must be an object")
    return value


def _array(value, label):
    if not isinstance(value, list):
        raise DepthOrderEvidenceError(f"{label} must be an array")
    return value


def _exact(value, fields, label):
    if set(value) != fields:
        raise DepthOrderEvidenceError(f"{label} fields are unsupported")
