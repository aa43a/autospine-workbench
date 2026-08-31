"""Strict browser-authored input for one P10.2b framing decision."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
from typing import Any

from .capture_framing_profile import (
    FORMAT_VERSION,
    INTENT,
    MAX_REQUEST_BYTES,
    MAX_REVISIONS,
    SUBMISSION_FORMAT,
)
from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)


class CaptureFramingSubmissionError(ValueError):
    """Raised when browser input is ambiguous, stale, or excessive."""


@dataclass(frozen=True, slots=True)
class CaptureFramingSubmission:
    package_id: str
    candidate_sha256: str
    p10_1_head: dict[str, Any]
    base_revision: int
    previous_decision_sha256: str | None
    action: str
    reason_code: str
    world_viewport: dict[str, float] | None


def require_capture_framing_submission(
    value: Mapping[str, Any],
) -> CaptureFramingSubmission:
    """Normalize one exact submission with an explicit confirmation bit."""

    try:
        if not isinstance(value, Mapping) or set(value) != _TOP_FIELDS:
            raise CaptureFramingSubmissionError(
                "Capture framing submission fields are unsupported"
            )
        payload = _copy(value)
        if len(_canonical(payload)) > MAX_REQUEST_BYTES:
            raise CaptureFramingSubmissionError(
                "Capture framing submission exceeds its byte limit"
            )
        if payload["format"] != SUBMISSION_FORMAT \
                or type(payload["format_version"]) is not int \
                or payload["format_version"] != FORMAT_VERSION \
                or payload["intent"] != INTENT \
                or payload["explicit_confirmation"] is not True:
            raise CaptureFramingSubmissionError(
                "Capture framing confirmation is incomplete"
            )
        package_id = require_sha256(
            payload["package_id"], "Capture framing package"
        )
        candidate_sha = require_sha256(
            payload["candidate_sha256"], "Capture framing candidate"
        )
        p10_head = _p10_head(payload["p10_1_head"])
        base = payload["base_revision"]
        if type(base) is not int or not 0 <= base < MAX_REVISIONS:
            raise CaptureFramingSubmissionError(
                "Capture framing base revision is invalid"
            )
        previous = payload["previous_decision_sha256"]
        if base == 0:
            if previous is not None:
                raise CaptureFramingSubmissionError(
                    "Initial framing predecessor must be null"
                )
        else:
            previous = require_sha256(previous, "Framing predecessor")
        action = payload["action"]
        if action not in _REASONS:
            raise CaptureFramingSubmissionError(
                "Capture framing action is unsupported"
            )
        reason = require_safe_token(payload["reason_code"], "Framing reason")
        if reason != _REASONS[action]:
            raise CaptureFramingSubmissionError(
                "Capture framing reason does not match its action"
            )
        viewport = _world_viewport(payload["world_viewport"], action)
        return CaptureFramingSubmission(
            package_id, candidate_sha, p10_head, base, previous,
            action, reason, viewport,
        )
    except CaptureFramingSubmissionError:
        raise
    except (
        KeyError, LayerManifestError, OverflowError, RecursionError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise CaptureFramingSubmissionError(
            "Capture framing submission is invalid"
        ) from exc


def _p10_head(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _HEAD_FIELDS:
        raise CaptureFramingSubmissionError("P10.1 head fields are unsupported")
    candidate = require_sha256(value["candidate_sha256"], "P10.0 candidate")
    decision = require_sha256(value["decision_sha256"], "P10.1 decision")
    revision = value["revision"]
    if type(revision) is not int or not 1 <= revision <= 10_000:
        raise CaptureFramingSubmissionError("P10.1 revision is invalid")
    return {
        "candidate_sha256": candidate,
        "decision_sha256": decision,
        "revision": revision,
    }


def _world_viewport(value: Any, action: str) -> dict[str, float] | None:
    if action in {"reject", "unobservable"}:
        if value is not None:
            raise CaptureFramingSubmissionError(
                "Unapproved framing cannot carry a viewport"
            )
        return None
    if action == "accept" and value is None:
        return None
    if type(value) is not dict or set(value) != _VIEWPORT_FIELDS:
        raise CaptureFramingSubmissionError(
            "Capture framing viewport fields are unsupported"
        )
    viewport = {field: _number(value[field]) for field in _VIEWPORT_FIELDS}
    if viewport["width"] <= 0 or viewport["height"] <= 0:
        raise CaptureFramingSubmissionError(
            "Capture framing viewport size is invalid"
        )
    return viewport


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)) or abs(float(value)) > 1e12:
        raise CaptureFramingSubmissionError(
            "Capture framing viewport number is invalid"
        )
    return float(value)


def _copy(value: Any) -> dict[str, Any]:
    return json.loads(_canonical(value).decode("utf-8"))


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


_TOP_FIELDS = {
    "format", "format_version", "intent", "explicit_confirmation",
    "package_id", "candidate_sha256", "p10_1_head", "base_revision",
    "previous_decision_sha256", "action", "reason_code", "world_viewport",
}
_HEAD_FIELDS = {"candidate_sha256", "decision_sha256", "revision"}
_VIEWPORT_FIELDS = {"x", "y", "width", "height"}
_REASONS = {
    "accept": "human-approved-automatic-capture-framing-v1",
    "adjust": "human-adjusted-capture-framing-v1",
    "reject": "human-rejected-capture-framing-v1",
    "unobservable": "human-marked-capture-framing-unobservable-v1",
}
