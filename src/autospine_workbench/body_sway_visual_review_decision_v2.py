"""Build one explicit exhaustive human P10.3c v2 visual decision."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .body_sway_visual_review_candidate_validation_v2 import (
    require_body_sway_visual_review_candidate_v2,
)
from .body_sway_visual_review_decision_validation_v2 import (
    FORMAT, FORMAT_VERSION,
    body_sway_visual_review_decision_sha256_v2,
    require_body_sway_visual_review_decision_v2,
    visual_review_decision_source_v2,
)
from .body_sway_visual_review_profile_v2 import (
    DECISION_SEMANTICS,
    body_sway_visual_review_release_gate_v2,
)


class BodySwayVisualReviewDecisionV2Error(ValueError):
    """Raised when explicit human inputs cannot form a v2 decision."""


@dataclass(frozen=True, slots=True)
class BodySwayVisualReviewDecisionV2:
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


def build_body_sway_visual_review_decision_v2(
    candidates: Mapping[str, Any], *, review: Mapping[str, Any],
    decisions: list[Mapping[str, Any]],
    previous_decision: Mapping[str, Any] | None = None,
) -> BodySwayVisualReviewDecisionV2:
    """Bind only supplied human choices; never synthesize approval defaults."""

    try:
        require_body_sway_visual_review_candidate_v2(candidates)
        review_input = _copy(review)
        if set(review_input) != {"reviewer_id", "notes"}:
            raise BodySwayVisualReviewDecisionV2Error(
                "Visual review v2 input fields are unsupported"
            )
        decision_rows = _copy(decisions)
        if not isinstance(decision_rows, list):
            raise BodySwayVisualReviewDecisionV2Error(
                "Visual review v2 choices must be an explicit list"
            )
        counts = {action: sum(
            isinstance(row, Mapping) and row.get("action") == action
            for row in decision_rows
        ) for action in ("approve", "reject", "unobservable")}
        status = "sampled_visual_approved" \
            if counts["approve"] == len(decision_rows) \
            else "sampled_visual_rejected"
        if previous_decision is None:
            revision, supersedes = 1, None
        else:
            require_body_sway_visual_review_decision_v2(
                previous_decision, candidates=candidates,
            )
            revision = previous_decision["review"]["revision"] + 1
            supersedes = body_sway_visual_review_decision_sha256_v2(
                previous_decision,
            )
        document = {
            "format": FORMAT, "format_version": FORMAT_VERSION,
            "project_id": candidates["project_id"],
            "clip_id": candidates["clip_id"],
            "source": visual_review_decision_source_v2(candidates),
            "review": {
                "method": "human", "status": "completed",
                "reviewer_id": review_input["reviewer_id"],
                "notes": review_input["notes"], "revision": revision,
                "supersedes_decision_sha256": supersedes,
            },
            "semantics": {
                **_copy(DECISION_SEMANTICS),
                "sampled_visual_approval_claimed":
                    status == "sampled_visual_approved",
            },
            "decisions": decision_rows, "status": status,
            "release_gate": body_sway_visual_review_release_gate_v2(status),
            "summary": {
                "case_count": len(decision_rows),
                "decision_count": len(decision_rows),
                "approve_count": counts["approve"],
                "reject_count": counts["reject"],
                "unobservable_count": counts["unobservable"],
            },
        }
        require_body_sway_visual_review_decision_v2(
            document, candidates=candidates,
            previous_decision=previous_decision,
        )
        return BodySwayVisualReviewDecisionV2(_canonical(document))
    except BodySwayVisualReviewDecisionV2Error:
        raise
    except (KeyError, OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise BodySwayVisualReviewDecisionV2Error(
            f"Visual review decision v2 build failed: {exc}"
        ) from exc


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


__all__ = [
    "BodySwayVisualReviewDecisionV2", "BodySwayVisualReviewDecisionV2Error",
    "build_body_sway_visual_review_decision_v2",
]
