"""Path-free public values returned by the P10.3c v2 contract service."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from .body_sway_visual_review_address_v2 import ExactVisualReviewAddressV2
from .body_sway_visual_review_history_snapshot_v2 import (
    BodySwayVisualReviewHistorySnapshotV2,
)
from .body_sway_visual_review_public import public_visual_review_candidate


@dataclass(frozen=True, slots=True)
class PreparedBodySwayVisualReviewV2:
    address: ExactVisualReviewAddressV2
    candidate_sha256: str
    _candidate_json: str
    history: BodySwayVisualReviewHistorySnapshotV2

    @property
    def candidate_document(self) -> dict[str, Any]:
        return public_visual_review_candidate(json.loads(self._candidate_json))


@dataclass(frozen=True, slots=True)
class BodySwayVisualReviewImageV2:
    candidate_sha256: str
    case_id: str
    evidence_sha256: str
    png_sha256: str
    size_bytes: int
    width: int
    height: int
    png_bytes: bytes


@dataclass(frozen=True, slots=True)
class ExactBodySwayVisualReviewDecisionV2:
    address: ExactVisualReviewAddressV2
    candidate_sha256: str
    decision_sha256: str
    revision: int
    _decision_json: str

    @property
    def decision_document(self) -> dict[str, Any]:
        return json.loads(self._decision_json)


@dataclass(frozen=True, slots=True)
class SubmittedBodySwayVisualReviewV2:
    address: ExactVisualReviewAddressV2
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
