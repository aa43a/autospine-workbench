"""Path-free application service for assisted P10.1 human review."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .idle_behavior_decision import build_idle_behavior_decision
from .idle_behavior_review_history import (
    IdleBehaviorReviewRevisionConflict,
)
from .idle_behavior_review_packages import (
    IdleBehaviorReviewPackageError,
    get_idle_behavior_review_address,
)
from .idle_behavior_review_profile import (
    FORMAT_VERSION,
    RECEIPT_FORMAT,
)
from .idle_behavior_review_http_models import (
    body_sway_feature,
    idle_behavior_review_entry,
)
from .idle_behavior_review_replay import (
    replay_idle_behavior_review_package,
)
from .idle_behavior_review_submission import (
    IdleBehaviorReviewSubmissionError,
    require_idle_behavior_review_submission,
)
from .idle_behavior_review_store import IdleBehaviorReviewStore


class IdleBehaviorReviewApplicationError(RuntimeError):
    """Raised when exact idle-review evidence cannot be served safely."""


class IdleBehaviorReviewApplicationNotFound(
    IdleBehaviorReviewApplicationError
):
    """Raised when a selected review package is no longer exact."""


class IdleBehaviorReviewApplicationInvalidSubmission(
    IdleBehaviorReviewApplicationError
):
    """Raised when user input does not bind to current exact evidence."""


class IdleBehaviorReviewApplicationUnavailable(
    IdleBehaviorReviewApplicationError
):
    """Raised when exact replay or publication cannot complete."""


class IdleBehaviorReviewApplication:
    """Prepare suggestions without authority and CAS explicit human choices."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)
        self._store = IdleBehaviorReviewStore(self.state_root)

    def prepare(
        self, package_id: str, *, project_ids: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Replay P3/P5/P9/P10.0 and return one read-only review entry."""

        try:
            address = get_idle_behavior_review_address(
                self.state_root, package_id, project_ids=project_ids,
            )
        except IdleBehaviorReviewPackageError as exc:
            raise IdleBehaviorReviewApplicationNotFound(
                "The exact idle behavior review package is unavailable"
            ) from exc
        try:
            evidence = replay_idle_behavior_review_package(
                self.state_root, address,
            )
            candidate = evidence.candidates.document
            history = self._store.snapshot(candidate)
            return idle_behavior_review_entry(evidence, history)
        except IdleBehaviorReviewApplicationError:
            raise
        except _APPLICATION_FAILURES as exc:
            raise IdleBehaviorReviewApplicationUnavailable(
                "Idle behavior review preparation failed"
            ) from exc

    def submit(
        self, package_id: str, payload: dict[str, Any], *,
        project_ids: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Recompile exact evidence, then append one confirmed human decision."""

        try:
            submission = require_idle_behavior_review_submission(payload)
            if submission.package_id != package_id:
                raise IdleBehaviorReviewApplicationInvalidSubmission(
                    "Review submission package identity is stale"
                )
            prepared = self.prepare(package_id, project_ids=project_ids)
            if submission.candidate_sha256 != prepared["candidate_sha256"]:
                raise IdleBehaviorReviewApplicationInvalidSubmission(
                    "Review submission candidate identity is stale"
                )
            candidate = prepared["candidate"]
            feature = body_sway_feature(candidate)
            if feature["availability"] != "candidate":
                raise IdleBehaviorReviewApplicationInvalidSubmission(
                    "Selected evidence has no observable body-sway candidate"
                )
            decision_row = {
                "candidate_id": feature["candidate_id"],
                "feature_id": "body_sway",
                "action": submission.action,
                "reason_code": _SERVER_REASON_CODES[submission.action],
                "payload": submission.parameters,
                "probe_status": (
                    "pending_probe" if submission.action == "adjust"
                    else "not_applicable"
                ),
            }
            decision = build_idle_behavior_decision(
                candidate,
                review={
                    "method": "human", "status": "completed",
                    "revision": submission.base_revision + 1,
                },
                decisions=[decision_row],
            )
            published = self._store.publish(
                decision, candidate,
                base_revision=submission.base_revision,
                previous_decision_sha256=(
                    submission.previous_decision_sha256
                ),
            )
            return {
                "format": RECEIPT_FORMAT,
                "format_version": FORMAT_VERSION,
                "status": "recorded",
                "package_id": package_id,
                "candidate_sha256": prepared["candidate_sha256"],
                "decision_sha256": published.sha256,
                "revision": published.revision,
                "action": decision_row["action"],
                "probe_status": decision_row["probe_status"],
                "reused": published.reused,
                "history": {
                    # This is the CAS linearization point.  A later writer may
                    # append another revision before the HTTP response leaves.
                    "current_revision": published.revision,
                    "head_decision_sha256": published.sha256,
                },
            }
        except IdleBehaviorReviewRevisionConflict:
            raise
        except (
            IdleBehaviorReviewApplicationInvalidSubmission,
            IdleBehaviorReviewApplicationNotFound,
            IdleBehaviorReviewApplicationUnavailable,
        ):
            raise
        except IdleBehaviorReviewSubmissionError as exc:
            raise IdleBehaviorReviewApplicationInvalidSubmission(
                "Idle behavior review submission is invalid"
            ) from exc
        except _APPLICATION_FAILURES as exc:
            raise IdleBehaviorReviewApplicationUnavailable(
                "Idle behavior review submission failed"
            ) from exc


_APPLICATION_FAILURES = (
    AttributeError, IndexError, KeyError, OSError, OverflowError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)
_SERVER_REASON_CODES = {
    "adjust": "human-approved-assisted-draft-v1",
    "reject": "human-declined-body-sway-v1",
    "unobservable": "human-marked-unobservable-v1",
}
