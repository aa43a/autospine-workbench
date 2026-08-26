"""Path-free public values returned by the P10.3c application service."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from .body_sway_visual_review_address import ExactVisualReviewAddress
from .body_sway_visual_review_history_snapshot import (
    BodySwayVisualReviewHistorySnapshot,
)
from .body_sway_visual_review_public import public_visual_review_candidate


@dataclass(frozen=True, slots=True)
class PreparedBodySwayVisualReview:
    """Bounded candidate and authoritative linear-history snapshot."""

    address: ExactVisualReviewAddress
    candidate_sha256: str
    _candidate_json: str
    history: BodySwayVisualReviewHistorySnapshot

    @property
    def candidate_document(self) -> dict[str, Any]:
        return public_visual_review_candidate(json.loads(self._candidate_json))


@dataclass(frozen=True, slots=True)
class BodySwayVisualReviewImage:
    """One path-free, exact candidate image response."""

    candidate_sha256: str
    case_id: str
    evidence_sha256: str
    png_sha256: str
    size_bytes: int
    width: int
    height: int
    png_bytes: bytes


@dataclass(frozen=True, slots=True)
class ExactBodySwayVisualReviewDecision:
    """One exact path-free historical decision document."""

    address: ExactVisualReviewAddress
    candidate_sha256: str
    decision_sha256: str
    revision: int
    _decision_json: str

    @property
    def decision_document(self) -> dict[str, Any]:
        return json.loads(self._decision_json)


@dataclass(frozen=True, slots=True)
class SubmittedBodySwayVisualReview:
    """Public identity and status of one authoritative decision revision."""

    address: ExactVisualReviewAddress
    candidate_sha256: str
    decision_sha256: str
    revision: int
    status: str
    release_gate_status: str
    release_gate_reason_codes: tuple[str, ...]
    case_count: int
    approve_count: int
    reject_count: int
    unobservable_count: int
    reused: bool
