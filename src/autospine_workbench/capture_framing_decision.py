"""Build and validate one explicit P10.2b human framing decision."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .capture_framing_candidate import CaptureFramingCandidate
from .capture_framing_profile import (
    DECISION_FORMAT,
    DECISION_SEMANTICS,
    FORMAT_VERSION,
    MAX_REVISIONS,
    capture_framing_decision_release_gate,
)
from .capture_framing_validation import (
    CaptureFramingValidationError,
    capture_framing_candidate_sha256,
    require_capture_framing_candidate,
    require_capture_world_viewport,
)
from .manifest_artifacts import require_safe_token, require_sha256


class CaptureFramingDecisionError(ValueError):
    """Raised when a decision is malformed or differs from its candidate."""


@dataclass(frozen=True, slots=True)
class CaptureFramingDecision:
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def build_capture_framing_decision(
    candidate: CaptureFramingCandidate,
    *, action: str,
    world_viewport: Mapping[str, Any] | None,
    reason_code: str,
    revision: int,
    supersedes_decision_sha256: str | None,
    previous_decision: CaptureFramingDecision | None = None,
) -> CaptureFramingDecision:
    """Create a candidate-bound revision; never infer the human action."""

    try:
        if type(candidate) is not CaptureFramingCandidate:
            raise CaptureFramingDecisionError(
                "Capture framing decision requires an exact candidate"
            )
        require_capture_framing_candidate(candidate.document)
        if action not in _ACTIONS:
            raise CaptureFramingDecisionError("Framing action is unsupported")
        if type(revision) is not int or not 1 <= revision <= MAX_REVISIONS:
            raise CaptureFramingDecisionError("Framing revision is invalid")
        previous = None if revision == 1 else require_sha256(
            supersedes_decision_sha256, "Framing predecessor"
        )
        if revision == 1 and supersedes_decision_sha256 is not None:
            raise CaptureFramingDecisionError(
                "Initial framing decision predecessor must be null"
            )
        if revision == 1 and previous_decision is not None \
                or revision > 1 \
                and type(previous_decision) is not CaptureFramingDecision:
            raise CaptureFramingDecisionError(
                "Framing predecessor document differs from the revision"
            )
        require_safe_token(reason_code, "Framing reason")
        if reason_code != _REASONS[action]:
            raise CaptureFramingDecisionError(
                "Framing reason does not match the action"
            )
        approved = action in {"accept", "adjust"}
        selected = _selected_viewport(candidate, action, world_viewport)
        document = {
            "format": DECISION_FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": candidate.document["project_id"],
            "clip_id": candidate.document["clip_id"],
            "source": {
                "capture_framing_candidate_sha256": candidate.sha256,
                **candidate.document["source"],
            },
            "review": {
                "method": "human", "status": "completed",
                "revision": revision,
                "supersedes_decision_sha256": previous,
            },
            "decision": {
                "action": action,
                "reason_code": reason_code,
                "world_viewport": selected,
            },
            "semantics": dict(DECISION_SEMANTICS),
            "status": (
                "ready_for_temporary_preview_v2"
                if approved else "capture_framing_not_approved"
            ),
            "release_gate": capture_framing_decision_release_gate(approved),
        }
        require_capture_framing_decision(
            document, candidate=candidate,
            previous_decision=(
                previous_decision.document
                if previous_decision is not None else None
            ),
        )
        return CaptureFramingDecision(_canonical(document))
    except CaptureFramingDecisionError:
        raise
    except (
        CaptureFramingValidationError, KeyError, OverflowError,
        RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise CaptureFramingDecisionError(
            f"Capture framing decision compilation failed: {exc}"
        ) from exc


def require_capture_framing_decision(
    value: Mapping[str, Any], *, candidate: CaptureFramingCandidate,
    previous_decision: Mapping[str, Any] | None = None,
) -> None:
    try:
        if type(candidate) is not CaptureFramingCandidate:
            raise CaptureFramingDecisionError("Framing candidate is invalid")
        require_capture_framing_candidate(candidate.document)
        _fields(value, {
            "format", "format_version", "project_id", "clip_id", "source",
            "review", "decision", "semantics", "status", "release_gate",
        }, "decision")
        if value["format"] != DECISION_FORMAT \
                or value["format_version"] != FORMAT_VERSION \
                or value["project_id"] != candidate.document["project_id"] \
                or value["clip_id"] != candidate.document["clip_id"]:
            raise CaptureFramingDecisionError("Decision identity differs")
        expected_source = {
            "capture_framing_candidate_sha256":
                capture_framing_candidate_sha256(candidate.document),
            **candidate.document["source"],
        }
        if value["source"] != expected_source \
                or value["semantics"] != DECISION_SEMANTICS:
            raise CaptureFramingDecisionError("Decision source differs")
        review = value["review"]
        _fields(review, {
            "method", "status", "revision", "supersedes_decision_sha256",
        }, "review")
        revision = review["revision"]
        expected_previous = None if previous_decision is None \
            else hashlib.sha256(
                _canonical(previous_decision).encode("utf-8")
            ).hexdigest()
        if review["method"] != "human" or review["status"] != "completed" \
                or type(revision) is not int \
                or not 1 <= revision <= MAX_REVISIONS \
                or review["supersedes_decision_sha256"] != expected_previous \
                or revision != (1 if previous_decision is None
                                else previous_decision["review"]["revision"] + 1):
            raise CaptureFramingDecisionError("Decision review chain differs")
        decision = value["decision"]
        _fields(decision, {"action", "reason_code", "world_viewport"}, "action")
        action = decision["action"]
        if action not in _ACTIONS or decision["reason_code"] != _REASONS[action]:
            raise CaptureFramingDecisionError("Decision action is invalid")
        selected = _selected_viewport(
            candidate, action, decision["world_viewport"]
        )
        if decision["world_viewport"] != selected:
            raise CaptureFramingDecisionError("Decision viewport differs")
        approved = action in {"accept", "adjust"}
        expected_status = "ready_for_temporary_preview_v2" \
            if approved else "capture_framing_not_approved"
        if value["status"] != expected_status \
                or value["release_gate"] \
                != capture_framing_decision_release_gate(approved):
            raise CaptureFramingDecisionError("Decision gate differs")
    except CaptureFramingDecisionError:
        raise
    except (
        CaptureFramingValidationError, KeyError, OverflowError,
        RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise CaptureFramingDecisionError(
            f"Capture framing decision validation failed: {exc}"
        ) from exc


def capture_framing_decision_sha256(
    value, *, candidate, previous_decision=None,
):
    require_capture_framing_decision(
        value, candidate=candidate, previous_decision=previous_decision,
    )
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _selected_viewport(candidate, action, value):
    if action in {"reject", "unobservable"}:
        if value is not None:
            raise CaptureFramingDecisionError(
                "Unapproved framing cannot carry a viewport"
            )
        return None
    proposal = candidate.document["proposed_world_viewport"]
    if action == "accept":
        if value is not None and dict(value) != proposal:
            raise CaptureFramingDecisionError(
                "Accepted framing must use the exact proposal"
            )
        return dict(proposal)
    return require_capture_world_viewport(
        value, union=candidate.document["union_envelope_runtime"],
        capture_viewport=candidate.document["capture_viewport"],
    )


def _fields(value, expected, label):
    if not isinstance(value, Mapping) or set(value) != set(expected):
        raise CaptureFramingDecisionError(f"Framing {label} fields are unsupported")


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


_ACTIONS = {"accept", "adjust", "reject", "unobservable"}
_REASONS = {
    "accept": "human-approved-automatic-capture-framing-v1",
    "adjust": "human-adjusted-capture-framing-v1",
    "reject": "human-rejected-capture-framing-v1",
    "unobservable": "human-marked-capture-framing-unobservable-v1",
}
