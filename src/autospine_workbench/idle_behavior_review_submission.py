"""Strict browser submission boundary for P10.1 body-sway review."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
from typing import Any

from .idle_behavior_review_profile import (
    FORMAT_VERSION,
    INTENT,
    MAX_REQUEST_BYTES,
    MAX_REVISIONS,
    SUBMISSION_FORMAT,
    TARGET_BONE_IDS,
)
from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)


class IdleBehaviorReviewSubmissionError(ValueError):
    """Raised when browser-authored review input is ambiguous or excessive."""


@dataclass(frozen=True, slots=True)
class IdleBehaviorReviewSubmission:
    """Normalized human input without any server-derived authority fields."""

    package_id: str
    candidate_sha256: str
    base_revision: int
    previous_decision_sha256: str | None
    action: str
    reason_code: str
    parameters: dict[str, Any] | None


def require_idle_behavior_review_submission(
    value: Mapping[str, Any],
) -> IdleBehaviorReviewSubmission:
    """Require the exact v1 payload and an explicit human confirmation bit."""

    try:
        if not isinstance(value, Mapping) or set(value) != _TOP_FIELDS:
            raise IdleBehaviorReviewSubmissionError(
                "Idle behavior review submission fields are unsupported"
            )
        payload = _copy(value)
        if len(_canonical(payload)) > MAX_REQUEST_BYTES:
            raise IdleBehaviorReviewSubmissionError(
                "Idle behavior review submission exceeds its byte limit"
            )
        if payload["format"] != SUBMISSION_FORMAT \
                or type(payload["format_version"]) is not int \
                or payload["format_version"] != FORMAT_VERSION \
                or payload["intent"] != INTENT \
                or payload["explicit_confirmation"] is not True:
            raise IdleBehaviorReviewSubmissionError(
                "Idle behavior review confirmation is incomplete"
            )
        package_id = require_sha256(payload["package_id"], "Review package")
        candidate_sha = require_sha256(
            payload["candidate_sha256"], "Idle behavior candidate"
        )
        base = payload["base_revision"]
        if type(base) is not int or not 0 <= base < MAX_REVISIONS:
            raise IdleBehaviorReviewSubmissionError(
                "Idle behavior review base revision is invalid"
            )
        previous = payload["previous_decision_sha256"]
        if base == 0:
            if previous is not None:
                raise IdleBehaviorReviewSubmissionError(
                    "Initial idle behavior review predecessor must be null"
                )
        else:
            previous = require_sha256(previous, "Review predecessor")
        action = payload["action"]
        if action not in _REASON_CODES:
            raise IdleBehaviorReviewSubmissionError(
                "Idle behavior review action is unsupported"
            )
        reason = require_safe_token(payload["reason_code"], "Review reason")
        if reason != _REASON_CODES[action]:
            raise IdleBehaviorReviewSubmissionError(
                "Idle behavior review reason does not match its action"
            )
        parameters = (
            _parameters(payload["parameters"])
            if action == "adjust" else None
        )
        if action != "adjust" and payload["parameters"] is not None:
            raise IdleBehaviorReviewSubmissionError(
                "Rejected or unobservable review cannot carry parameters"
            )
        return IdleBehaviorReviewSubmission(
            package_id, candidate_sha, base, previous,
            action, reason, parameters,
        )
    except IdleBehaviorReviewSubmissionError:
        raise
    except (
        KeyError, LayerManifestError, OverflowError, RecursionError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise IdleBehaviorReviewSubmissionError(
            "Idle behavior review submission is invalid"
        ) from exc


def _parameters(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _PARAMETER_FIELDS:
        raise IdleBehaviorReviewSubmissionError(
            "Body-sway parameter fields are unsupported"
        )
    cycles = value["cycles"]
    if type(cycles) is not int or not 1 <= cycles <= 64:
        raise IdleBehaviorReviewSubmissionError(
            "Body-sway cycle count is invalid"
        )
    amplitudes = _per_bone(
        value["per_bone_amplitude_deg"], maximum=10.0,
        exclusive_maximum=False,
    )
    phases = _per_bone(
        value["per_bone_phase_fraction"], maximum=1.0,
        exclusive_maximum=True,
    )
    if not any(row["value"] > 0 for row in amplitudes):
        raise IdleBehaviorReviewSubmissionError(
            "Body-sway adjustment requires a non-zero amplitude"
        )
    return {
        "cycles": cycles,
        "per_bone_amplitude_deg": amplitudes,
        "per_bone_phase_fraction": phases,
    }


def _per_bone(
    value: Any, *, maximum: float, exclusive_maximum: bool,
) -> list[dict[str, Any]]:
    if type(value) is not list or len(value) != len(TARGET_BONE_IDS):
        raise IdleBehaviorReviewSubmissionError(
            "Body-sway per-bone inventory is invalid"
        )
    result = []
    for bone_id, raw in zip(TARGET_BONE_IDS, value, strict=True):
        if type(raw) is not dict or set(raw) != {"bone_id", "value"} \
                or raw.get("bone_id") != bone_id:
            raise IdleBehaviorReviewSubmissionError(
                "Body-sway per-bone order is invalid"
            )
        number = raw.get("value")
        if isinstance(number, bool) or not isinstance(number, (int, float)) \
                or not math.isfinite(number) or number < 0 \
                or (number >= maximum if exclusive_maximum
                    else number > maximum):
            raise IdleBehaviorReviewSubmissionError(
                "Body-sway per-bone value is invalid"
            )
        result.append({"bone_id": bone_id, "value": number})
    return result


def _copy(value: Any) -> dict[str, Any]:
    return json.loads(_canonical(value).decode("utf-8"))


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


_TOP_FIELDS = {
    "format", "format_version", "intent", "explicit_confirmation",
    "package_id", "candidate_sha256", "base_revision",
    "previous_decision_sha256", "action", "reason_code", "parameters",
}
_PARAMETER_FIELDS = {
    "cycles", "per_bone_amplitude_deg", "per_bone_phase_fraction",
}
_REASON_CODES = {
    "adjust": "human-approved-assisted-draft-v1",
    "reject": "human-declined-body-sway-v1",
    "unobservable": "human-marked-unobservable-v1",
}
