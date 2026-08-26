"""Project reviewed foot-lock decisions into canonical root-correction keys."""

from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

from .motion_policy_candidate_inventory import (
    MotionPolicyCandidateInventoryError,
    derive_motion_policy_candidates,
)
from .motion_policy_decision_validation import (
    MotionPolicyDecisionValidationError,
    require_motion_policy_decision,
)


DECIMALS = 9


class ReviewedRootCorrectionError(ValueError):
    """Raised when reviewed decisions cannot form an exact correction track."""


def compile_reviewed_root_correction(
    decision: Mapping[str, Any],
    foot_candidates: Mapping[str, Any],
    depth_candidates: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return one reviewed correction key for every P9 foot sample tick."""

    try:
        require_motion_policy_decision(
            decision,
            foot_candidates=foot_candidates,
            depth_candidates=depth_candidates,
        )
        inventory = derive_motion_policy_candidates(
            foot_candidates, depth_candidates
        )
        samples_by_id = _foot_samples_by_candidate_id(
            inventory.candidates, foot_candidates["samples"]
        )
        decisions_by_id = {
            row["candidate_id"]: row for row in decision["decisions"]
        }
        releases_by_tick = {
            row["tick"]: row for row in decision["root_release_keys"]
        }
        candidate_id_by_tick = {
            sample["tick"]: candidate_id
            for candidate_id, sample in samples_by_id.items()
        }
        keys = []
        for sample in foot_candidates["samples"]:
            tick = sample["tick"]
            if sample["state"] == "unconstrained":
                keys.append(_release_key(tick, releases_by_tick.get(tick)))
                continue
            candidate_id = candidate_id_by_tick[tick]
            keys.append(_decision_key(
                tick, sample, decisions_by_id[candidate_id]
            ))
        _require_complete_schedule(keys, foot_candidates["samples"])
        if depth_candidates["timing"]["loop"]:
            _require_loop_endpoints(
                keys, depth_candidates["timing"]["duration_ticks"]
            )
        return keys
    except ReviewedRootCorrectionError:
        raise
    except (
        MotionPolicyCandidateInventoryError,
        MotionPolicyDecisionValidationError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise ReviewedRootCorrectionError(
            f"Reviewed root-correction projection failed: {exc}"
        ) from exc


def _foot_samples_by_candidate_id(candidates, samples):
    constrained_by_tick = {
        row["tick"]: row for row in samples
        if row["state"] != "unconstrained"
    }
    foot_rows = [row for row in candidates if row.kind == "foot_lock"]
    if len(constrained_by_tick) != len(foot_rows):
        raise ReviewedRootCorrectionError(
            "Foot-lock candidate IDs do not cover constrained samples"
        )
    result = {}
    for candidate in foot_rows:
        sample = constrained_by_tick.get(candidate.tick)
        if sample is None or sample["state"] != candidate.foot_state:
            raise ReviewedRootCorrectionError(
                "Foot-lock candidate identity differs from its sample"
            )
        result[candidate.candidate_id] = sample
    if len(result) != len(foot_rows):
        raise ReviewedRootCorrectionError(
            "Foot-lock candidate IDs are not unique"
        )
    return result


def _decision_key(tick: int, sample, decision) -> dict[str, Any]:
    action = decision["action"]
    if action == "accept":
        correction = sample["correction_candidate_px"]
    elif action == "adjust":
        correction = decision["payload"]["final_correction_xy_px"]
    else:
        correction = [0.0, 0.0]
    return _key(tick, correction, "linear")


def _release_key(tick: int, release) -> dict[str, Any]:
    if release is None:
        return _key(tick, [0.0, 0.0], "linear")
    if release["incoming_interpolation"] != "linear":
        raise ReviewedRootCorrectionError(
            "Reviewed root-correction v1 only supports linear release keys"
        )
    return _key(
        tick,
        release["correction_xy_px"],
        "linear",
    )


def _key(tick: int, correction, interpolation: str) -> dict[str, Any]:
    return {
        "tick": tick,
        "correction_xy_px": [_q(value) for value in correction],
        "incoming_interpolation": interpolation,
    }


def _require_complete_schedule(keys, samples) -> None:
    ticks = [row["tick"] for row in keys]
    expected = [row["tick"] for row in samples]
    if ticks != expected or any(
        current <= previous for previous, current in zip(ticks, ticks[1:])
    ):
        raise ReviewedRootCorrectionError(
            "Root-correction keys must exactly cover the foot sample schedule"
        )


def _require_loop_endpoints(keys, duration_ticks: int) -> None:
    by_tick = {row["tick"]: row for row in keys}
    expected = {
        "correction_xy_px": [0.0, 0.0],
        "incoming_interpolation": "linear",
    }
    for tick in (0, duration_ticks):
        row = by_tick.get(tick)
        if row is None or any(row[field] != value for field, value in expected.items()):
            raise ReviewedRootCorrectionError(
                "Loop root correction must be zero and linear at both endpoints"
            )


def _q(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise ReviewedRootCorrectionError(
            "Root-correction value must be finite"
        )
    result = round(float(value), DECIMALS)
    return 0.0 if result == 0 else result
