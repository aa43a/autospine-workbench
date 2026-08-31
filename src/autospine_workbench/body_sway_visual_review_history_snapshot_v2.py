"""Immutable read model for the P10.3c v2 decision history."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .body_sway_runtime_execution_reader import VerifiedBodySwayRuntimeExecution
from .body_sway_visual_review_binding_v2 import (
    reload_authoritative_runtime_execution_v2,
    reload_authoritative_visual_review_candidate_v2,
)
from .body_sway_visual_review_candidate_validation_v2 import (
    require_body_sway_visual_review_candidate_v2,
)
from .body_sway_visual_review_candidate_v2 import BodySwayVisualReviewCandidateV2
from .body_sway_visual_review_errors_v2 import BodySwayVisualReviewHistoryV2Error
from .body_sway_visual_review_history_v2 import load_visual_review_chain_v2
from .body_sway_visual_review_profile_v2 import DECISION_NAMESPACE
from .body_sway_visual_review_store_files import (
    exact_subdirectory, optional_existing_parent,
)
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2


@dataclass(frozen=True, slots=True)
class BodySwayVisualReviewHistoryRowV2:
    revision: int
    decision_sha256: str
    status: str


@dataclass(frozen=True, slots=True)
class BodySwayVisualReviewHistorySnapshotV2:
    project_id: str
    candidate_sha256: str
    revision_count: int
    current_revision: int
    head_decision_sha256: str | None
    rows: tuple[BodySwayVisualReviewHistoryRowV2, ...]


def snapshot_visual_review_history_v2(
    state_root: Path, candidates: BodySwayVisualReviewCandidateV2,
    execution: VerifiedBodySwayRuntimeExecution,
    preview: TemporaryBodySwayPreviewV2,
) -> BodySwayVisualReviewHistorySnapshotV2:
    """Replay current execution/preview and return the exact linear head."""

    try:
        loaded_execution = reload_authoritative_runtime_execution_v2(
            state_root, execution,
        )
        require_body_sway_visual_review_candidate_v2(
            candidates.document, execution=loaded_execution, preview=preview,
        )
        project, digest = candidates.document["project_id"], candidates.sha256
        parent = optional_existing_parent(
            state_root, project, DECISION_NAMESPACE, digest,
        )
        if parent is None:
            return BodySwayVisualReviewHistorySnapshotV2(
                project, digest, 0, 0, None, (),
            )
        candidate, _execution = reload_authoritative_visual_review_candidate_v2(
            state_root, candidates, loaded_execution, preview,
        )
        revisions = exact_subdirectory(parent, "revisions", create=False)
        chain = load_visual_review_chain_v2(parent, revisions, candidate)
        rows = tuple(BodySwayVisualReviewHistoryRowV2(
            item.document["review"]["revision"], item.sha256,
            item.document["status"],
        ) for item in chain)
        return BodySwayVisualReviewHistorySnapshotV2(
            project, digest, len(rows), len(rows),
            rows[-1].decision_sha256 if rows else None, rows,
        )
    except BodySwayVisualReviewHistoryV2Error:
        raise
    except (AttributeError, KeyError, OSError, RuntimeError,
            TypeError, UnicodeError, ValueError) as exc:
        raise BodySwayVisualReviewHistoryV2Error(
            f"Visual review v2 history snapshot failed: {exc}"
        ) from exc
