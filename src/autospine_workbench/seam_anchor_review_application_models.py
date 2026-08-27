"""Path-free public values returned by the P10.5b application service."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from .seam_anchor_review_address import ExactSeamAnchorReviewAddress
from .seam_anchor_review_history_models import SeamAnchorReviewHistorySnapshot


@dataclass(frozen=True, slots=True)
class PreparedSeamAnchorReview:
    address: ExactSeamAnchorReviewAddress
    candidate_sha256: str
    _candidate_json: str
    history: SeamAnchorReviewHistorySnapshot

    @property
    def candidate_document(self) -> dict[str, Any]:
        return json.loads(self._candidate_json)


@dataclass(frozen=True, slots=True)
class ExactSeamAnchorReviewDecision:
    address: ExactSeamAnchorReviewAddress
    candidate_sha256: str
    decision_sha256: str
    revision: int
    _decision_json: str

    @property
    def decision_document(self) -> dict[str, Any]:
        return json.loads(self._decision_json)


@dataclass(frozen=True, slots=True)
class SubmittedSeamAnchorReview:
    address: ExactSeamAnchorReviewAddress
    candidate_sha256: str
    decision_sha256: str
    revision: int
    status: str
    release_gate_status: str
    release_gate_reason_codes: tuple[str, ...]
    relationship_count: int
    accept_count: int
    adjust_count: int
    reject_count: int
    unobservable_count: int
    anchor_pair_count: int
    reused: bool
