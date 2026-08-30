"""Build a pending depth-pair proposal from one exact P8/P5/P3 chain."""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
from typing import Any

from .depth_order_inputs import DepthOrderInputs
from .depth_pair_policy import (
    HYSTERESIS_UNIT,
    MAX_HOLD_FRAMES,
    MAX_THRESHOLD,
)


FORMAT = "autospine-depth-pair-policy-proposal"
FORMAT_VERSION = 1
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class DepthPairPolicyProposalError(ValueError):
    """Raised when exact evidence cannot form an unambiguous proposal."""


def compile_depth_pair_policy_proposal(
    inputs: DepthOrderInputs,
    *,
    motion_id: str,
    pair_id: str,
    first_slot_id: str,
    second_slot_id: str,
    enter_threshold: float = 0.05,
    exit_threshold: float = 0.02,
    minimum_hold_frames: int = 2,
) -> dict[str, Any]:
    """Return a pending proposal; never emit an approved policy."""

    try:
        if type(inputs) is not DepthOrderInputs:
            raise DepthPairPolicyProposalError(
                "Depth proposal inputs are not exact"
            )
        motion = _identifier(motion_id, "motion_id")
        pair = _identifier(pair_id, "pair_id")
        slot_ids = sorted({
            _identifier(first_slot_id, "first_slot_id"),
            _identifier(second_slot_id, "second_slot_id"),
        })
        if len(slot_ids) != 2:
            raise DepthPairPolicyProposalError(
                "Depth proposal slots must be distinct"
            )
        hysteresis = _hysteresis(
            enter_threshold, exit_threshold, minimum_hold_frames
        )
        rig_slots = {row["id"]: row for row in inputs.rig["slots"]}
        role_by_bone = {
            row["bone_id"]: row["role"] for row in inputs.target["bones"]
        }
        tracks = {
            row["role"]: row for row in inputs.projected["segment_tracks"]
        }
        slots = []
        bound = []
        for slot_id in slot_ids:
            slot = rig_slots.get(slot_id)
            if slot is None:
                raise DepthPairPolicyProposalError(
                    f"Depth proposal slot is absent from P3: {slot_id}"
                )
            role = role_by_bone.get(slot.get("bone"))
            track = tracks.get(role)
            if role is None or track is None:
                raise DepthPairPolicyProposalError(
                    f"Depth proposal slot has no projected role: {slot_id}"
                )
            if any(
                sample.get("projection_state") != "observable"
                for sample in track.get("samples", [])
            ):
                raise DepthPairPolicyProposalError(
                    f"Depth proposal role is not observable: {role}"
                )
            slots.append({"slot_id": slot_id, "depth_role": role})
            bound.append(slot)
        front = _setup_front(bound)
        policy_id = _identifier(f"{motion}.{pair}", "policy_id")
        return {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "policy_id": policy_id,
            "project_id": inputs.target["project_id"],
            "clip_id": inputs.projected["clip_id"],
            "source": inputs.identities,
            "review": {
                "status": "pending_human_review",
                "method": "human",
            },
            "hysteresis": hysteresis,
            "pairs": [{
                "pair_id": pair,
                "slots": slots,
                "setup_front_slot": front,
            }],
            "proposal": {
                "method": "exact-single-pair-operator-review-v1",
                "scope": f"{slot_ids[0]} versus {slot_ids[1]}",
                "rationale": (
                    "Slot roles and setup front are derived from the exact "
                    "P3/P5/P8 chain; the pair itself remains review scope."
                ),
                "limitations": [
                    "This proposal is not an approved depth policy.",
                    "Hysteresis values are unvalidated review starting points.",
                    "No Depth candidate or runtime draw-order is emitted.",
                ],
            },
        }
    except DepthPairPolicyProposalError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise DepthPairPolicyProposalError(
            f"Depth proposal compilation failed: {exc}"
        ) from exc


def _setup_front(slots: list[Mapping[str, Any]]) -> str:
    orders = [row.get("setup_draw_order") for row in slots]
    if any(type(value) is not int for value in orders) \
            or orders[0] == orders[1]:
        raise DepthPairPolicyProposalError(
            "Depth proposal setup order is missing or ambiguous"
        )
    return str(slots[0 if orders[0] > orders[1] else 1]["id"])


def _hysteresis(enter: Any, exit_: Any, hold: Any) -> dict[str, Any]:
    values = (enter, exit_)
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in values
    ) or not float(enter) > float(exit_) >= 0 \
            or any(abs(float(value)) > MAX_THRESHOLD for value in values):
        raise DepthPairPolicyProposalError(
            "Depth proposal hysteresis requires enter > exit >= 0"
        )
    if type(hold) is not int or not 1 <= hold <= MAX_HOLD_FRAMES:
        raise DepthPairPolicyProposalError(
            "Depth proposal minimum hold is invalid"
        )
    return {
        "unit": HYSTERESIS_UNIT,
        "enter_threshold": float(enter),
        "exit_threshold": float(exit_),
        "minimum_hold_frames": hold,
    }


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise DepthPairPolicyProposalError(
            f"Depth proposal {label} is invalid"
        )
    return value
