"""Immutable public read models for P10.5b seam-review history."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SeamAnchorReviewHistoryRow:
    revision: int
    decision_sha256: str
    status: str


@dataclass(frozen=True, slots=True)
class SeamAnchorReviewHistorySnapshot:
    project_id: str
    candidate_sha256: str
    revision_count: int
    current_revision: int
    head_decision_sha256: str | None
    rows: tuple[SeamAnchorReviewHistoryRow, ...]
