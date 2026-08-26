"""Public immutable read model for P10.3c visual-review history."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .body_sway_runtime_capture_binding import reload_authoritative_runtime_capture
from .body_sway_runtime_capture_reader import VerifiedBodySwayRuntimeCapture
from .body_sway_visual_review_binding import (
    reload_authoritative_visual_review_candidate,
)
from .body_sway_visual_review_candidate import BodySwayVisualReviewCandidate
from .body_sway_visual_review_candidate_validation import (
    body_sway_visual_review_candidate_sha256,
    require_body_sway_visual_review_candidate,
)
from .body_sway_visual_review_history import (
    BodySwayVisualReviewHistoryError,
    load_visual_review_chain,
)
from .body_sway_visual_review_profile import DECISION_NAMESPACE
from .body_sway_visual_review_store_files import (
    exact_payload,
    exact_subdirectory,
    optional_existing_parent,
)


@dataclass(frozen=True, slots=True)
class BodySwayVisualReviewHistoryRow:
    revision: int
    decision_sha256: str
    status: str


@dataclass(frozen=True, slots=True)
class BodySwayVisualReviewHistorySnapshot:
    project_id: str
    candidate_sha256: str
    revision_count: int
    current_revision: int
    head_decision_sha256: str | None
    rows: tuple[BodySwayVisualReviewHistoryRow, ...]


def snapshot_visual_review_history(
    state_root: Path,
    candidates: BodySwayVisualReviewCandidate,
    capture: VerifiedBodySwayRuntimeCapture,
) -> BodySwayVisualReviewHistorySnapshot:
    """Return an authoritative immutable history view without creating state."""

    try:
        loaded_capture = reload_authoritative_runtime_capture(state_root, capture)
        document = candidates.document
        require_body_sway_visual_review_candidate(document, capture=loaded_capture)
        digest = body_sway_visual_review_candidate_sha256(document)
        exact_payload(candidates.canonical_bytes, document, digest)
        project = document["project_id"]
        parent = optional_existing_parent(
            state_root, project, DECISION_NAMESPACE, digest
        )
        if parent is None:
            return BodySwayVisualReviewHistorySnapshot(
                project, digest, 0, 0, None, ()
            )
        reload_authoritative_visual_review_candidate(
            state_root, candidates, capture
        )
        revisions = exact_subdirectory(parent, "revisions", create=False)
        chain = load_visual_review_chain(parent, revisions, candidates)
        rows = tuple(
            BodySwayVisualReviewHistoryRow(
                item.document["review"]["revision"],
                item.sha256,
                item.document["status"],
            )
            for item in chain
        )
        return BodySwayVisualReviewHistorySnapshot(
            project, digest, len(rows), len(rows),
            rows[-1].decision_sha256 if rows else None, rows,
        )
    except BodySwayVisualReviewHistoryError:
        raise
    except (AttributeError, KeyError, OSError, RuntimeError,
            TypeError, UnicodeError, ValueError) as exc:
        raise BodySwayVisualReviewHistoryError(
            f"Visual review history snapshot failed: {exc}"
        ) from exc
