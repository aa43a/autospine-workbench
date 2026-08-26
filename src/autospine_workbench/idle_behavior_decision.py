"""Build one explicit human IdleBehaviorDecision v1 value object."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .idle_behavior_candidate_validation import (
    IdleBehaviorCandidateValidationError,
    require_idle_behavior_candidates,
)
from .idle_behavior_decision_validation import (
    FORMAT,
    FORMAT_VERSION,
    SEMANTICS,
    IdleBehaviorDecisionValidationError,
    idle_behavior_decision_sha256,
    require_idle_behavior_decision,
    source_from_candidates,
)


class IdleBehaviorDecisionError(ValueError):
    """Raised when review input cannot form a strict decision contract."""


@dataclass(frozen=True, slots=True)
class IdleBehaviorDecision:
    """Frozen canonical decision value; accessors return isolated values."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_json(self) -> str:
        return self._canonical_json

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def build_idle_behavior_decision(
    candidates: Mapping[str, Any], *,
    review: Mapping[str, Any],
    decisions: list[Mapping[str, Any]],
) -> IdleBehaviorDecision:
    """Bind exhaustive human choices; never approve safety or emit timelines."""

    try:
        require_idle_behavior_candidates(candidates)
        decision_rows = _snapshot(decisions)
        counts = _action_counts(decision_rows)
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": candidates["project_id"],
            "clip_id": candidates["clip_id"],
            "source": source_from_candidates(candidates),
            "timing": _snapshot(candidates["timing"]),
            "review": _snapshot(review),
            "semantics": _snapshot(SEMANTICS),
            "decisions": decision_rows,
            "summary": {
                "candidate_count": len(decision_rows),
                "decision_count": len(decision_rows),
                "adjust_count": counts["adjust"],
                "reject_count": counts["reject"],
                "unobservable_count": counts["unobservable"],
                "pending_probe_count": counts["adjust"],
            },
        }
        require_idle_behavior_decision(document, candidates=candidates)
        value = IdleBehaviorDecision(_canonical(document))
        if value.sha256 != idle_behavior_decision_sha256(value.document):
            raise IdleBehaviorDecisionError(
                "Idle behavior decision canonical identity is inconsistent"
            )
        return value
    except IdleBehaviorDecisionError:
        raise
    except (
        IdleBehaviorCandidateValidationError,
        IdleBehaviorDecisionValidationError,
        KeyError,
        OverflowError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise IdleBehaviorDecisionError(
            f"Idle behavior decision build failed: {exc}"
        ) from exc


def _snapshot(value: Any) -> Any:
    return json.loads(_canonical(value))


def _action_counts(value: Any) -> dict[str, int]:
    rows = value if isinstance(value, list) else []
    return {
        action: sum(
            isinstance(row, Mapping) and row.get("action") == action
            for row in rows
        )
        for action in ("adjust", "reject", "unobservable")
    }


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
