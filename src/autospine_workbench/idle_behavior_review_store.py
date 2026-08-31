"""Small authoritative-store facade for P10.1 decision history."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .idle_behavior_decision import IdleBehaviorDecision
from .idle_behavior_candidate_validation import (
    idle_behavior_candidates_sha256,
)
from .idle_behavior_review_history import (
    IdleBehaviorReviewHistorySnapshot,
    PublishedIdleBehaviorReviewDecision,
    publish_idle_behavior_review_decision,
    snapshot_idle_behavior_review_history,
)
from .idle_behavior_review_transaction import idle_behavior_review_transaction


class IdleBehaviorReviewStore:
    """Keep application code independent of filesystem layout and filenames."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def snapshot(
        self, candidates: Mapping[str, Any],
    ) -> IdleBehaviorReviewHistorySnapshot:
        return snapshot_idle_behavior_review_history(
            self.state_root, candidates,
        )

    def publish(
        self,
        decision: IdleBehaviorDecision,
        candidates: Mapping[str, Any],
        *,
        base_revision: int,
        previous_decision_sha256: str | None,
    ) -> PublishedIdleBehaviorReviewDecision:
        candidate_sha256 = idle_behavior_candidates_sha256(candidates)
        with idle_behavior_review_transaction(
            self.state_root, candidate_sha256,
        ):
            return publish_idle_behavior_review_decision(
                self.state_root, decision, candidates,
                base_revision=base_revision,
                previous_decision_sha256=previous_decision_sha256,
            )
