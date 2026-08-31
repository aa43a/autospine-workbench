"""Verified current head for one exact P10.3c v2 candidate chain."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .body_sway_runtime_execution_reader import VerifiedBodySwayRuntimeExecution
from .body_sway_visual_review_candidate_v2 import BodySwayVisualReviewCandidateV2
from .body_sway_visual_review_binding_v2 import (
    reload_authoritative_runtime_execution_v2,
)
from .body_sway_visual_review_decision_v2 import BodySwayVisualReviewDecisionV2
from .body_sway_visual_review_history_snapshot_v2 import (
    BodySwayVisualReviewHistorySnapshotV2,
)
from .body_sway_visual_review_store_v2 import BodySwayVisualReviewStoreV2
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2


@dataclass(frozen=True, slots=True)
class BodySwayVisualReviewVerifiedHeadV2:
    candidate: BodySwayVisualReviewCandidateV2
    execution: VerifiedBodySwayRuntimeExecution
    preview: TemporaryBodySwayPreviewV2
    snapshot: BodySwayVisualReviewHistorySnapshotV2
    decision: BodySwayVisualReviewDecisionV2 | None


def read_body_sway_visual_review_verified_head_v2(
    state_root: Path, candidate: BodySwayVisualReviewCandidateV2,
    execution: VerifiedBodySwayRuntimeExecution,
    preview: TemporaryBodySwayPreviewV2,
) -> BodySwayVisualReviewVerifiedHeadV2:
    store = BodySwayVisualReviewStoreV2(state_root)
    loaded_execution = reload_authoritative_runtime_execution_v2(
        state_root, execution,
    )
    loaded = store.load_candidate(
        candidate.document["project_id"], loaded_execution.bundle_sha256,
        candidate.sha256, execution=loaded_execution, preview=preview,
    )
    snapshot = store.snapshot_history(
        candidates=loaded, execution=loaded_execution, preview=preview,
    )
    decision = None
    if snapshot.head_decision_sha256 is not None:
        decision = store.load_decision(
            loaded.document["project_id"], loaded.sha256,
            snapshot.head_decision_sha256, candidates=loaded,
            execution=loaded_execution, preview=preview,
        )
    return BodySwayVisualReviewVerifiedHeadV2(
        loaded, loaded_execution, preview, snapshot, decision,
    )


__all__ = [
    "BodySwayVisualReviewVerifiedHeadV2",
    "read_body_sway_visual_review_verified_head_v2",
]
