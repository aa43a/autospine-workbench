"""Race-aware, read-only replay of the current P10.2b framing head."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .capture_framing_candidate import CaptureFramingCandidate
from .capture_framing_decision import CaptureFramingDecision
from .capture_framing_history import (
    CaptureFramingHistoryError,
    CaptureFramingHistorySnapshot,
    load_capture_framing_head,
    snapshot_capture_framing_history,
)


class CaptureFramingVerifiedHeadError(RuntimeError):
    """Raised when the current framing history cannot be frozen exactly."""


@dataclass(frozen=True, slots=True)
class CaptureFramingVerifiedHead:
    """A stable history snapshot paired with its fully replayed head value."""

    candidate_sha256: str
    snapshot: CaptureFramingHistorySnapshot
    decision: CaptureFramingDecision | None

    @property
    def current_revision(self) -> int:
        return self.snapshot.current_revision

    @property
    def decision_sha256(self) -> str | None:
        return self.snapshot.head_decision_sha256


def read_capture_framing_verified_head(
    state_root: Path,
    candidate: CaptureFramingCandidate,
) -> CaptureFramingVerifiedHead:
    """Read, replay, and stabilize the candidate-bound current decision."""

    try:
        if type(candidate) is not CaptureFramingCandidate:
            raise CaptureFramingVerifiedHeadError(
                "Capture framing head requires an exact candidate"
            )
        before = snapshot_capture_framing_history(state_root, candidate)
        decision = load_capture_framing_head(state_root, candidate)
        after = snapshot_capture_framing_history(state_root, candidate)
        if before != after:
            raise CaptureFramingVerifiedHeadError(
                "Capture framing head changed while it was being read"
            )
        _require_pair(after, decision)
        return CaptureFramingVerifiedHead(
            candidate.sha256, after, decision,
        )
    except CaptureFramingVerifiedHeadError:
        raise
    except (
        AttributeError, CaptureFramingHistoryError, KeyError,
        OSError, OverflowError, RuntimeError, TypeError, ValueError,
    ) as exc:
        raise CaptureFramingVerifiedHeadError(
            "Capture framing head could not be replayed exactly"
        ) from exc


def same_capture_framing_verified_head(
    left: CaptureFramingVerifiedHead,
    right: CaptureFramingVerifiedHead,
) -> bool:
    """Compare every field that linearizes P10.2b downstream readers."""

    return type(left) is CaptureFramingVerifiedHead \
        and type(right) is CaptureFramingVerifiedHead \
        and left.candidate_sha256 == right.candidate_sha256 \
        and left.snapshot == right.snapshot \
        and _decision_bytes(left.decision) == _decision_bytes(right.decision)


def _require_pair(snapshot, decision) -> None:
    if snapshot.current_revision == 0:
        if decision is not None or any(value is not None for value in (
            snapshot.head_decision_sha256, snapshot.action, snapshot.status,
        )):
            raise CaptureFramingVerifiedHeadError(
                "Empty capture framing head is inconsistent"
            )
        return
    if type(decision) is not CaptureFramingDecision:
        raise CaptureFramingVerifiedHeadError(
            "Capture framing history head document is missing"
        )
    document = decision.document
    if snapshot.head_decision_sha256 != decision.sha256 \
            or snapshot.current_revision != document["review"]["revision"] \
            or snapshot.action != document["decision"]["action"] \
            or snapshot.status != document["status"]:
        raise CaptureFramingVerifiedHeadError(
            "Capture framing history metadata differs from its head document"
        )


def _decision_bytes(value):
    return None if value is None else value.canonical_bytes
