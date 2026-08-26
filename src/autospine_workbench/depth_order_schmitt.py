"""Deterministic pairwise Schmitt hysteresis for review candidates."""

from __future__ import annotations

import math
from typing import Any


PRECISION_DECIMALS = 9


class DepthOrderSchmittError(ValueError):
    """Raised when score samples cannot form deterministic candidates."""


def evaluate_depth_pair(
    score_rows: list[dict[str, Any]],
    *,
    slot_ids: tuple[str, str],
    setup_front_slot: str,
    enter_threshold: float,
    exit_threshold: float,
    minimum_hold_frames: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return per-frame latch evidence and candidate switch events."""

    if setup_front_slot not in slot_ids or slot_ids[0] >= slot_ids[1]:
        raise DepthOrderSchmittError("Depth pair slot identity is invalid")
    current = setup_front_slot
    pending: str | None = None
    pending_start: int | None = None
    pending_frames = 0
    samples, events = [], []
    for index, row in enumerate(score_rows):
        scores = row.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(slot_ids):
            raise DepthOrderSchmittError("Depth pair score inventory is invalid")
        challenger = slot_ids[1] if current == slot_ids[0] else slot_ids[0]
        advantage = _q(float(scores[challenger]) - float(scores[current]))
        state = "hold"
        if pending is None:
            if advantage >= enter_threshold:
                pending, pending_start, pending_frames = challenger, index, 1
                state = "pending"
        elif pending != challenger or advantage <= exit_threshold:
            pending, pending_start, pending_frames = None, None, 0
        else:
            pending_frames += 1
            state = "pending"
        if pending is not None and pending_frames >= minimum_hold_frames:
            previous = current
            current = pending
            assert pending_start is not None
            events.append({
                "source_frame_index": row["source_frame_index"],
                "tick": row["tick"],
                "from_front_slot": previous,
                "to_front_slot": current,
                "evidence_window": {
                    "start_source_frame_index": score_rows[pending_start][
                        "source_frame_index"
                    ],
                    "end_source_frame_index": row["source_frame_index"],
                    "start_tick": score_rows[pending_start]["tick"],
                    "end_tick": row["tick"],
                    "sample_count": index - pending_start + 1,
                },
            })
            pending, pending_start, pending_frames = None, None, 0
            state = "switch_candidate"
        samples.append({
            "current_front_slot": current,
            "pending_front_slot": pending,
            "pending_frame_count": pending_frames,
            "state": state,
        })
    return samples, events


def quantize_depth_score(value: float) -> float:
    """Quantize one finite normalized depth score."""

    return _q(value)


def _q(value: float) -> float:
    if not math.isfinite(value):
        raise DepthOrderSchmittError("Depth score must be finite")
    result = round(float(value), PRECISION_DECIMALS)
    return 0.0 if result == 0 else result
