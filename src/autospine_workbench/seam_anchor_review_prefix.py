"""Bounded prefix replay for one exact historical seam-review decision."""

from __future__ import annotations

from pathlib import Path

from .manifest_artifacts import require_sha256
from .safe_input_files import strict_json_object
from .seam_anchor_candidates import SeamAnchorCandidates
from .seam_anchor_review_address import ExactSeamAnchorReviewAddress
from .seam_anchor_review_candidate_store import (
    reload_authoritative_seam_anchor_review_candidate,
)
from .seam_anchor_review_decision import SeamAnchorReviewDecision
from .seam_anchor_review_decision_validation import (
    require_seam_anchor_review_decision,
    seam_anchor_review_decision_sha256,
)
from .seam_anchor_review_errors import SeamAnchorReviewHistoryError
from .seam_anchor_review_profile import (
    DECISION_NAMESPACE,
    MAX_SEAM_ANCHOR_REVIEW_REVISIONS,
)
from .seam_anchor_review_store_files import (
    exact_subdirectory,
    existing_parent,
    read_fixed_named_document,
)


def load_seam_anchor_review_decision_prefix(
    state_root: Path,
    address: ExactSeamAnchorReviewAddress,
    candidate_sha256: str,
    decision_sha256: str,
    revision: int, *,
    candidates: SeamAnchorCandidates,
    rig: dict,
) -> SeamAnchorReviewDecision:
    """Replay only fixed slots 1..revision and ignore every later sibling."""

    try:
        candidate_address = require_sha256(
            candidate_sha256, "Seam-review candidate digest"
        )
        decision_address = require_sha256(
            decision_sha256, "Seam-review decision digest"
        )
        if type(revision) is not int \
                or not 1 <= revision <= MAX_SEAM_ANCHOR_REVIEW_REVISIONS:
            raise SeamAnchorReviewHistoryError(
                "Seam-review revision is outside bounded history"
            )
        candidate = reload_authoritative_seam_anchor_review_candidate(
            state_root, address, candidates
        )
        if candidate.sha256 != candidate_address:
            raise SeamAnchorReviewHistoryError(
                "Seam decision address differs from exact candidate"
            )
        parent = existing_parent(
            state_root, address.project_id, DECISION_NAMESPACE,
            candidate_address,
        )
        revisions = exact_subdirectory(parent, "revisions", create=False)
        previous = None
        for number in range(1, revision + 1):
            payload = read_fixed_named_document(
                revisions, f"r{number:06d}.json"
            )
            document = strict_json_object(
                payload, f"Seam-review revision {number}"
            )
            if document.get("review", {}).get("revision") != number:
                raise SeamAnchorReviewHistoryError(
                    "Seam-review slot revision is inconsistent"
                )
            require_seam_anchor_review_decision(
                document, candidates=candidate.document, rig=rig,
                previous_decision=previous.document if previous else None,
            )
            digest = seam_anchor_review_decision_sha256(document)
            if read_fixed_named_document(
                parent, f"{digest}.json", digest=digest
            ) != payload:
                raise SeamAnchorReviewHistoryError(
                    "Seam revision differs from content-addressed decision"
                )
            previous = SeamAnchorReviewDecision(payload.decode("utf-8"))
        if previous is None or previous.sha256 != decision_address:
            raise SeamAnchorReviewHistoryError(
                "Seam decision differs from its declared revision slot"
            )
        return previous
    except SeamAnchorReviewHistoryError:
        raise
    except (AttributeError, KeyError, OSError, RuntimeError, TypeError,
            UnicodeError, ValueError) as exc:
        raise SeamAnchorReviewHistoryError(
            "Seam-review prefix load failed"
        ) from exc


__all__ = ["load_seam_anchor_review_decision_prefix"]
