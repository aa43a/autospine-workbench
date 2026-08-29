"""Exact read/CAS application boundary for P10.5b seam review."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .manifest_artifacts import LayerManifestError, require_sha256
from .seam_anchor_review_address import ExactSeamAnchorReviewAddress
from .seam_anchor_review_application_models import (
    ExactSeamAnchorReviewDecision,
    PreparedSeamAnchorReview,
    SubmittedSeamAnchorReview,
)
from .seam_anchor_review_application_support import (
    require_consistent_seam_anchor_review_history,
    require_seam_anchor_review_compare_and_swap,
    seam_anchor_review_revision_conflict,
    submitted_seam_anchor_review_result,
)
from .seam_anchor_review_candidate_binding import (
    SeamAnchorReviewCandidateBindingError,
    load_bound_seam_anchor_review_candidate,
)
from .seam_anchor_review_candidate_store import (
    publish_seam_anchor_review_candidate,
)
from .seam_anchor_review_decision import (
    SeamAnchorReviewDecisionError,
    build_seam_anchor_review_decision,
)
from .seam_anchor_review_errors import (
    SeamAnchorReviewHistoryError,
    SeamAnchorReviewRevisionConflict,
    SeamAnchorReviewStoreError,
)
from .seam_anchor_review_history import (
    load_seam_anchor_review_decision,
    publish_seam_anchor_review_decision,
)
from .seam_anchor_review_history_snapshot import (
    snapshot_seam_anchor_review_history,
)
from .seam_anchor_review_profile import MAX_SEAM_ANCHOR_REVIEW_REVISIONS
from .seam_anchor_review_replay_cache import SeamAnchorReviewReplayCache
from .seam_anchor_review_submission import (
    SeamAnchorReviewSubmissionError,
    require_seam_anchor_review_submission,
)


class SeamAnchorReviewApplicationError(RuntimeError):
    """Raised when exact seam-review evidence cannot be served safely."""


class SeamAnchorReviewApplicationNotFound(SeamAnchorReviewApplicationError):
    """Raised when an exact subordinate decision address is absent."""


class SeamAnchorReviewApplicationInvalidSubmission(
    SeamAnchorReviewApplicationError
):
    """Raised when submitted identity differs from current candidates."""


class SeamAnchorReviewApplication:
    """Compile exact candidates and manage their immutable decision chain."""

    def __init__(
        self, state_root: Path, *,
        replay_cache: SeamAnchorReviewReplayCache | None = None,
    ) -> None:
        self.state_root = Path(state_root)
        if replay_cache is not None and (
            type(replay_cache) is not SeamAnchorReviewReplayCache
            or not replay_cache.owns_state_root(self.state_root)
        ):
            raise SeamAnchorReviewApplicationError(
                "Seam-review replay cache state root differs"
            )
        self.replay_cache = replay_cache

    def prepare(
        self, address: ExactSeamAnchorReviewAddress,
    ) -> PreparedSeamAnchorReview:
        """Compile candidates and inspect history without writes."""

        try:
            bound = self._load(address)
            candidate, rig = bound.candidates, bound.rig
            history = snapshot_seam_anchor_review_history(
                self.state_root, address, candidate, rig
            )
            require_consistent_seam_anchor_review_history(candidate, history)
            canvas = rig.get("canvas")
            if type(canvas) is not dict \
                    or type(canvas.get("width")) is not int \
                    or type(canvas.get("height")) is not int \
                    or canvas["width"] < 1 or canvas["height"] < 1:
                raise SeamAnchorReviewApplicationError(
                    "Seam-review canvas is invalid"
                )
            return PreparedSeamAnchorReview(
                address, candidate.sha256,
                candidate.canonical_bytes.decode("utf-8"), history,
                canvas["width"], canvas["height"],
            )
        except SeamAnchorReviewApplicationError:
            raise
        except _APPLICATION_ERRORS as exc:
            raise SeamAnchorReviewApplicationError(
                "Seam-review preparation failed"
            ) from exc

    def exact_decision(
        self,
        address: ExactSeamAnchorReviewAddress, *,
        candidate_sha256: str,
        revision: int,
        decision_sha256: str,
    ) -> ExactSeamAnchorReviewDecision:
        """Read one exact historical revision; never use a latest alias."""

        try:
            candidate_address = require_sha256(
                candidate_sha256, "Seam-review candidate digest"
            )
            decision_address = require_sha256(
                decision_sha256, "Seam-review decision digest"
            )
            if type(revision) is not int \
                    or not 1 <= revision <= MAX_SEAM_ANCHOR_REVIEW_REVISIONS:
                raise SeamAnchorReviewApplicationError(
                    "Seam-review revision address is invalid"
                )
            bound = self._load(address)
            candidate, rig = bound.candidates, bound.rig
            if candidate.sha256 != candidate_address:
                raise SeamAnchorReviewApplicationNotFound(
                    "Seam-review candidate address is stale"
                )
            history = snapshot_seam_anchor_review_history(
                self.state_root, address, candidate, rig
            )
            require_consistent_seam_anchor_review_history(candidate, history)
            if revision > history.current_revision \
                    or history.rows[revision - 1].decision_sha256 \
                        != decision_address:
                raise SeamAnchorReviewApplicationNotFound(
                    "Seam decision address is not an exact revision"
                )
            decision = load_seam_anchor_review_decision(
                self.state_root, address, candidate.sha256, decision_address,
                candidates=candidate, rig=rig,
            )
            if decision.document["review"]["revision"] != revision:
                raise SeamAnchorReviewApplicationError(
                    "Seam decision revision differs from its address"
                )
            return ExactSeamAnchorReviewDecision(
                address, candidate.sha256, decision.sha256, revision,
                decision.canonical_bytes.decode("utf-8"),
            )
        except SeamAnchorReviewApplicationError:
            raise
        except _APPLICATION_ERRORS as exc:
            raise SeamAnchorReviewApplicationError(
                "Seam-review decision load failed"
            ) from exc

    def submit(
        self,
        address: ExactSeamAnchorReviewAddress,
        payload: dict[str, Any],
    ) -> SubmittedSeamAnchorReview:
        """CAS one exhaustive human decision into immutable history."""

        try:
            submission = require_seam_anchor_review_submission(payload)
            bound = self._load(address)
            candidate, rig = bound.candidates, bound.rig
            if submission.candidate_sha256 != candidate.sha256:
                raise SeamAnchorReviewApplicationInvalidSubmission(
                    "Seam-review submission candidate is stale"
                )
            history = snapshot_seam_anchor_review_history(
                self.state_root, address, candidate, rig
            )
            require_consistent_seam_anchor_review_history(candidate, history)
            previous = self._previous(
                submission, address, candidate, rig, history
            )
            decision = build_seam_anchor_review_decision(
                candidate.document, rig,
                review=submission.review,
                decisions=submission.decisions,
                previous_decision=previous.document if previous else None,
            )
            require_seam_anchor_review_compare_and_swap(
                submission, decision.sha256, history
            )
            publish_seam_anchor_review_candidate(
                self.state_root, address, candidate
            )
            published = publish_seam_anchor_review_decision(
                self.state_root, address, decision, candidate, rig
            )
            loaded = load_seam_anchor_review_decision(
                self.state_root, address, candidate.sha256, published.sha256,
                candidates=candidate, rig=rig,
            )
            if loaded.canonical_bytes != decision.canonical_bytes:
                raise SeamAnchorReviewApplicationError(
                    "Seam-review decision readback differs"
                )
            return submitted_seam_anchor_review_result(
                address, candidate, loaded.document, loaded.sha256,
                published.reused,
            )
        except SeamAnchorReviewRevisionConflict:
            raise
        except SeamAnchorReviewApplicationError:
            raise
        except _APPLICATION_ERRORS as exc:
            raise SeamAnchorReviewApplicationError(
                "Seam-review submission failed"
            ) from exc

    def _load(self, address):
        if type(address) is not ExactSeamAnchorReviewAddress:
            raise SeamAnchorReviewApplicationError(
                "Seam review requires an exact address"
            )
        if self.replay_cache is not None:
            return self.replay_cache.load_candidate(address)
        return load_bound_seam_anchor_review_candidate(self.state_root, address)

    def _previous(self, submission, address, candidate, rig, history):
        base, previous_sha = (
            submission.base_revision, submission.previous_decision_sha256
        )
        if base == 0:
            return None
        if base > history.current_revision \
                or history.rows[base - 1].decision_sha256 != previous_sha:
            raise seam_anchor_review_revision_conflict(submission, history)
        previous = load_seam_anchor_review_decision(
            self.state_root, address, candidate.sha256, previous_sha,
            candidates=candidate, rig=rig,
        )
        if previous.document["review"]["revision"] != base:
            raise seam_anchor_review_revision_conflict(submission, history)
        return previous


_APPLICATION_ERRORS = (
    AttributeError, KeyError, LayerManifestError, OSError, OverflowError,
    RecursionError, RuntimeError, SeamAnchorReviewCandidateBindingError,
    SeamAnchorReviewDecisionError, SeamAnchorReviewHistoryError,
    SeamAnchorReviewStoreError, SeamAnchorReviewSubmissionError,
    TypeError, UnicodeError, ValueError,
)
