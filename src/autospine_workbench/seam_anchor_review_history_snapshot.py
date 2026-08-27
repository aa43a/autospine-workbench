"""Read-only authoritative history snapshot for P10.5b seam review."""

from __future__ import annotations

from pathlib import Path

from .seam_anchor_candidates import SeamAnchorCandidates
from .seam_anchor_review_address import ExactSeamAnchorReviewAddress
from .seam_anchor_review_candidate_store import (
    reload_authoritative_seam_anchor_review_candidate,
)
from .seam_anchor_review_errors import SeamAnchorReviewHistoryError
from .seam_anchor_review_history import load_seam_anchor_review_chain
from .seam_anchor_review_history_models import (
    SeamAnchorReviewHistoryRow,
    SeamAnchorReviewHistorySnapshot,
)
from .seam_anchor_review_profile import DECISION_NAMESPACE
from .seam_anchor_review_store_files import (
    exact_subdirectory,
    optional_existing_parent,
)


def snapshot_seam_anchor_review_history(
    state_root: Path,
    address: ExactSeamAnchorReviewAddress,
    candidates: SeamAnchorCandidates,
    rig: dict,
) -> SeamAnchorReviewHistorySnapshot:
    """Inspect one candidate namespace without creating any filesystem state."""

    try:
        document = candidates.document
        digest = candidates.sha256
        parent = optional_existing_parent(
            state_root, address.project_id, DECISION_NAMESPACE, digest
        )
        if parent is None:
            return SeamAnchorReviewHistorySnapshot(
                address.project_id, digest, 0, 0, None, ()
            )
        candidate = reload_authoritative_seam_anchor_review_candidate(
            state_root, address, candidates
        )
        revisions = exact_subdirectory(parent, "revisions", create=False)
        chain = load_seam_anchor_review_chain(
            parent, revisions, candidate, rig
        )
        rows = tuple(SeamAnchorReviewHistoryRow(
            item.document["review"]["revision"],
            item.sha256, item.document["status"],
        ) for item in chain)
        return SeamAnchorReviewHistorySnapshot(
            document["project_id"], digest, len(rows), len(rows),
            rows[-1].decision_sha256 if rows else None, rows,
        )
    except SeamAnchorReviewHistoryError:
        raise
    except (
        AttributeError, KeyError, OSError, RuntimeError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise SeamAnchorReviewHistoryError(
            "Seam-review history snapshot failed"
        ) from exc
