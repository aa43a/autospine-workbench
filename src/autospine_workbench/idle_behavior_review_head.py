"""Exact, read-only access to the current P10.1 decision head."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .body_sway_visual_review_store_files import (
    BodySwayVisualReviewFilesError,
    optional_existing_parent,
    read_named_document,
)
from .idle_behavior_candidate_validation import (
    idle_behavior_candidates_sha256,
)
from .idle_behavior_decision import IdleBehaviorDecision
from .idle_behavior_decision_validation import (
    idle_behavior_decision_sha256,
    require_idle_behavior_decision,
)
from .idle_behavior_review_history import (
    IdleBehaviorReviewHistoryError,
    IdleBehaviorReviewHistorySnapshot,
    snapshot_idle_behavior_review_history,
)
from .idle_behavior_review_profile import DECISION_NAMESPACE
from .safe_input_files import strict_json_object


class IdleBehaviorReviewHeadError(RuntimeError):
    """Raised when the exact current decision cannot be read safely."""


@dataclass(frozen=True, slots=True)
class IdleBehaviorReviewHead:
    """One exact history snapshot and its canonical current decision."""

    snapshot: IdleBehaviorReviewHistorySnapshot
    decision: IdleBehaviorDecision | None

    @property
    def current_revision(self) -> int:
        return self.snapshot.current_revision

    @property
    def decision_sha256(self) -> str | None:
        return self.snapshot.head_decision_sha256


def read_idle_behavior_review_head(
    state_root: Path,
    candidates: Mapping[str, Any],
) -> IdleBehaviorReviewHead:
    """Read the current candidate-bound decision without creating state."""

    try:
        snapshot = snapshot_idle_behavior_review_history(
            state_root, candidates,
        )
        digest = snapshot.head_decision_sha256
        if digest is None:
            if snapshot.current_revision != 0 or snapshot.rows:
                raise IdleBehaviorReviewHeadError(
                    "Idle behavior empty head is inconsistent"
                )
            return IdleBehaviorReviewHead(snapshot, None)
        candidate_sha = idle_behavior_candidates_sha256(candidates)
        parent = optional_existing_parent(
            state_root, candidates["project_id"],
            DECISION_NAMESPACE, candidate_sha,
        )
        if parent is None:
            raise IdleBehaviorReviewHeadError(
                "Idle behavior current head disappeared"
            )
        payload = read_named_document(
            parent, f"{digest}.json", digest=digest,
        )
        document = strict_json_object(payload, "Idle behavior current head")
        require_idle_behavior_decision(document, candidates=candidates)
        if idle_behavior_decision_sha256(document) != digest \
                or document["review"]["revision"] \
                != snapshot.current_revision:
            raise IdleBehaviorReviewHeadError(
                "Idle behavior current head identity is inconsistent"
            )
        value = IdleBehaviorDecision(payload.decode("utf-8"))
        if value.sha256 != digest:
            raise IdleBehaviorReviewHeadError(
                "Idle behavior current head bytes are inconsistent"
            )
        return IdleBehaviorReviewHead(snapshot, value)
    except IdleBehaviorReviewHeadError:
        raise
    except (
        AttributeError, BodySwayVisualReviewFilesError, KeyError,
        IdleBehaviorReviewHistoryError, OSError, OverflowError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise IdleBehaviorReviewHeadError(
            "Idle behavior current head could not be read exactly"
        ) from exc


def same_idle_behavior_review_head(
    left: IdleBehaviorReviewHead,
    right: IdleBehaviorReviewHead,
) -> bool:
    """Compare only the linearization fields used by downstream readers."""

    return type(left) is IdleBehaviorReviewHead \
        and type(right) is IdleBehaviorReviewHead \
        and left.current_revision == right.current_revision \
        and left.decision_sha256 == right.decision_sha256
