"""Field checks for the strict IdleBehaviorDecision v1 contract."""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
from typing import Any


MAX_CYCLES = 64
# Syntax-level review envelope only; safety remains unprobed per decision semantics.
MAX_REVIEW_AMPLITUDE_DEG = 10.0
MAX_REVISION = 2_147_483_647
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_CANDIDATE_ID = re.compile(r"^body-sway-[0-9a-f]{64}$")


class IdleBehaviorDecisionFieldError(ValueError):
    """Raised when one decision field is unsafe or non-canonical."""


def require_source(value: Any) -> None:
    source = object_value(value, "Idle behavior decision source")
    fields = {
        "idle_behavior_candidates_sha256", "target_profile_sha256",
        "motion_instance_v2_sha256", "reviewed_motion_bundle_sha256",
    }
    exact_fields(source, fields, "Idle behavior decision source")
    for field in fields:
        digest_value(source.get(field), field)


def require_timing(value: Any) -> None:
    timing = object_value(value, "Idle behavior decision timing")
    exact_fields(
        timing, {"ticks_per_second", "duration_ticks", "loop"},
        "Idle behavior decision timing",
    )
    duration = timing.get("duration_ticks")
    if type(timing.get("ticks_per_second")) is not int \
            or timing.get("ticks_per_second") != 1_000_000 \
            or type(duration) is not int or not 1 <= duration <= 600_000_000 \
            or type(timing.get("loop")) is not bool:
        raise IdleBehaviorDecisionFieldError(
            "Idle behavior decision timing is invalid"
        )


def require_review(value: Any) -> None:
    review = object_value(value, "Idle behavior decision review")
    exact_fields(review, {"method", "status", "revision"},
                 "Idle behavior decision review")
    revision = review.get("revision")
    if review.get("method") != "human" \
            or review.get("status") != "completed" \
            or type(revision) is not int \
            or not 1 <= revision <= MAX_REVISION:
        raise IdleBehaviorDecisionFieldError(
            "Idle behavior decision requires completed human review"
        )


def require_decisions(value: Any) -> dict[str, int]:
    rows = array_value(value, "Idle behavior decisions", maximum=4)
    counts = {
        "decision": len(rows), "adjust": 0, "reject": 0,
        "unobservable": 0, "pending_probe": 0,
    }
    previous = None
    for raw in rows:
        row = object_value(raw, "Idle behavior decision row")
        exact_fields(
            row,
            {
                "candidate_id", "feature_id", "action", "reason_code",
                "payload", "probe_status",
            },
            "Idle behavior decision row",
        )
        candidate_id = candidate_id_value(row.get("candidate_id"))
        if previous is not None and candidate_id <= previous:
            raise IdleBehaviorDecisionFieldError(
                "Idle behavior decisions must be sorted and unique"
            )
        previous = candidate_id
        if row.get("feature_id") != "body_sway":
            raise IdleBehaviorDecisionFieldError(
                "Only body_sway candidates can be decided"
            )
        identifier_value(row.get("reason_code"), "reason_code")
        action = row.get("action")
        if action not in {"adjust", "reject", "unobservable"}:
            raise IdleBehaviorDecisionFieldError(
                "Idle behavior decision action is unsupported"
            )
        counts[action] += 1
        _action_payload(row)
        if row["probe_status"] == "pending_probe":
            counts["pending_probe"] += 1
    return counts


def _action_payload(row: Mapping[str, Any]) -> None:
    action = row["action"]
    if action != "adjust":
        if row.get("payload") is not None \
                or row.get("probe_status") != "not_applicable":
            raise IdleBehaviorDecisionFieldError(
                "Rejected or unobservable decisions cannot carry a probe payload"
            )
        return
    if row.get("probe_status") != "pending_probe":
        raise IdleBehaviorDecisionFieldError(
            "Adjusted idle behavior must remain pending_probe"
        )
    payload = object_value(row.get("payload"), "Body-sway adjustment payload")
    exact_fields(
        payload,
        {"cycles", "per_bone_amplitude_deg", "per_bone_phase_fraction"},
        "Body-sway adjustment payload",
    )
    cycles = payload.get("cycles")
    if type(cycles) is not int or not 1 <= cycles <= MAX_CYCLES:
        raise IdleBehaviorDecisionFieldError(
            "Body-sway cycles must be a bounded positive integer"
        )
    amplitudes = _per_bone_values(
        payload.get("per_bone_amplitude_deg"), "amplitude", _amplitude,
    )
    phases = _per_bone_values(
        payload.get("per_bone_phase_fraction"), "phase", _phase,
    )
    if [row["bone_id"] for row in amplitudes] != [
        row["bone_id"] for row in phases
    ]:
        raise IdleBehaviorDecisionFieldError(
            "Body-sway per-bone parameter inventories differ"
        )
    if not any(float(row["value"]) > 0.0 for row in amplitudes):
        raise IdleBehaviorDecisionFieldError(
            "Body-sway adjustment requires a non-zero amplitude"
        )


def _per_bone_values(value: Any, label: str, validate) -> list[Mapping[str, Any]]:
    rows = array_value(value, f"Body-sway per-bone {label}", minimum=1,
                       maximum=64)
    result = []
    ids = []
    for raw in rows:
        row = object_value(raw, f"Body-sway per-bone {label} row")
        exact_fields(row, {"bone_id", "value"},
                     f"Body-sway per-bone {label} row")
        ids.append(identifier_value(row.get("bone_id"), "bone_id"))
        validate(row.get("value"))
        result.append(row)
    if len(ids) != len(set(ids)):
        raise IdleBehaviorDecisionFieldError(
            f"Body-sway per-bone {label} bone ids must be unique"
        )
    return result


def _amplitude(value: Any) -> None:
    number = finite_number(value, "amplitude")
    if not 0.0 <= number <= MAX_REVIEW_AMPLITUDE_DEG:
        raise IdleBehaviorDecisionFieldError(
            "Body-sway amplitude is outside the bounded review input envelope"
        )


def _phase(value: Any) -> None:
    number = finite_number(value, "phase fraction")
    if not 0.0 <= number < 1.0:
        raise IdleBehaviorDecisionFieldError(
            "Body-sway phase fraction must be in [0, 1)"
        )


def finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise IdleBehaviorDecisionFieldError(
            f"Idle behavior {label} must be finite"
        )
    return float(value)


def candidate_id_value(value: Any) -> str:
    if not isinstance(value, str) or not _CANDIDATE_ID.fullmatch(value):
        raise IdleBehaviorDecisionFieldError(
            "Idle behavior candidate_id is invalid"
        )
    return value


def digest_value(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise IdleBehaviorDecisionFieldError(
            f"Idle behavior {label} is not a SHA-256"
        )


def identifier_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise IdleBehaviorDecisionFieldError(
            f"Idle behavior {label} is invalid"
        )
    return value


def object_value(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise IdleBehaviorDecisionFieldError(f"{label} must be an object")
    return value


def array_value(
    value: Any, label: str, *, minimum: int = 0, maximum: int
) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise IdleBehaviorDecisionFieldError(
            f"{label} must contain {minimum}..{maximum} items"
        )
    return value


def exact_fields(
    value: Mapping[str, Any], fields: set[str], label: str
) -> None:
    if set(value) != fields:
        raise IdleBehaviorDecisionFieldError(f"{label} fields are unsupported")
