"""Build one exhaustive candidate/P3-bound P10.5b human decision."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .seam_anchor_candidate_validation import (
    SeamAnchorCandidateValidationError,
    require_seam_anchor_candidates,
    seam_anchor_candidates_sha256,
)
from .seam_anchor_review_binding_validation import (
    SeamAnchorReviewBindingValidationError,
    materialize_seam_anchor_review_rows,
)
from .seam_anchor_review_decision_validation import (
    FORMAT,
    FORMAT_VERSION,
    SeamAnchorReviewDecisionValidationError,
    require_seam_anchor_review_decision,
    seam_anchor_review_decision_sha256,
    seam_anchor_review_decision_source,
)
from .seam_anchor_review_json import canonical_json_bytes
from .seam_anchor_review_profile import (
    DECISION_SEMANTICS,
    seam_anchor_review_release_gate,
)
from .seam_anchor_review_submission import (
    SeamAnchorReviewSubmissionError,
    require_seam_anchor_review_submission,
)


class SeamAnchorReviewDecisionError(ValueError):
    """Raised when human inputs cannot form an exact seam decision."""


@dataclass(frozen=True, slots=True)
class SeamAnchorReviewDecision:
    """Frozen canonical decision with one explicit history edge."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def build_seam_anchor_review_decision(
    candidates: Mapping[str, Any],
    rig: Mapping[str, Any], *,
    review: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
    previous_decision: Mapping[str, Any] | None = None,
) -> SeamAnchorReviewDecision:
    """Bind exhaustive choices; never turn static review into release proof."""

    try:
        require_seam_anchor_candidates(candidates)
        candidate_sha = seam_anchor_candidates_sha256(candidates)
        if previous_decision is None:
            base, revision, supersedes = 0, 1, None
        else:
            require_seam_anchor_review_decision(
                previous_decision, candidates=candidates, rig=rig
            )
            base = previous_decision["review"]["revision"]
            revision = base + 1
            supersedes = seam_anchor_review_decision_sha256(
                previous_decision
            )
        submitted = require_seam_anchor_review_submission({
            "base_revision": base,
            "candidate_sha256": candidate_sha,
            "previous_decision_sha256": supersedes,
            "review": _copy(review),
            "decisions": _copy(decisions),
        })
        rows = list(materialize_seam_anchor_review_rows(
            candidates, rig, submitted.decisions
        ))
        counts = {
            action: sum(row["action"] == action for row in rows)
            for action in ("accept", "adjust", "reject", "unobservable")
        }
        status = (
            "reviewed_anchor_set_ready_for_compile"
            if counts["accept"] + counts["adjust"] == len(rows)
            else "reviewed_anchor_set_blocked"
        )
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": candidates["project_id"],
            "source": seam_anchor_review_decision_source(candidates),
            "review": {
                "method": "human", "status": "completed",
                "reviewer_id": submitted.review["reviewer_id"],
                "notes": submitted.review["notes"],
                "revision": revision,
                "supersedes_decision_sha256": supersedes,
            },
            "semantics": _copy(DECISION_SEMANTICS),
            "decisions": rows,
            "status": status,
            "release_gate": seam_anchor_review_release_gate(status),
            "summary": {
                "relationship_count": len(rows),
                "decision_count": len(rows),
                "accept_count": counts["accept"],
                "adjust_count": counts["adjust"],
                "reject_count": counts["reject"],
                "unobservable_count": counts["unobservable"],
                "anchor_pair_count": sum(
                    len(row["anchors"]) for row in rows
                ),
            },
        }
        require_seam_anchor_review_decision(
            document, candidates=candidates, rig=rig,
            previous_decision=previous_decision,
        )
        return SeamAnchorReviewDecision(
            canonical_json_bytes(document).decode("utf-8")
        )
    except SeamAnchorReviewDecisionError:
        raise
    except (
        KeyError, OverflowError, RecursionError,
        SeamAnchorCandidateValidationError,
        SeamAnchorReviewBindingValidationError,
        SeamAnchorReviewDecisionValidationError,
        SeamAnchorReviewSubmissionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise SeamAnchorReviewDecisionError(
            f"Seam-review decision build failed: {exc}"
        ) from exc


def _copy(value):
    return json.loads(canonical_json_bytes(value).decode("utf-8"))
