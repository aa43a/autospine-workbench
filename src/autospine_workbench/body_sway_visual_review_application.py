"""Shared application boundary for exact P10.3c human visual review."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .body_sway_runtime_capture_reader import (
    VerifiedBodySwayRuntimeCaptureReader,
    VerifiedBodySwayRuntimeCaptureReaderError,
)
from .body_sway_visual_review_address import ExactVisualReviewAddress
from .body_sway_visual_review_application_models import (
    BodySwayVisualReviewImage,
    ExactBodySwayVisualReviewDecision,
    PreparedBodySwayVisualReview,
    SubmittedBodySwayVisualReview,
)
from .body_sway_visual_review_application_support import (
    require_consistent_visual_review_history,
    require_visual_review_compare_and_swap,
    submitted_visual_review_result,
    visual_review_revision_conflict,
)
from .body_sway_visual_review_candidate import (
    BodySwayVisualReviewCandidateError,
    compile_body_sway_visual_review_candidate,
)
from .body_sway_visual_review_history import (
    BodySwayVisualReviewRevisionConflict,
)
from .body_sway_visual_review_decision import (
    BodySwayVisualReviewDecisionError,
    build_body_sway_visual_review_decision,
)
from .body_sway_visual_review_store import (
    BodySwayVisualReviewStore,
    BodySwayVisualReviewStoreError,
)
from .body_sway_visual_review_submission import (
    BodySwayVisualReviewSubmissionError,
    require_body_sway_visual_review_submission,
)
from .body_sway_visual_review_profile import MAX_VISUAL_REVIEW_REVISIONS
from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .png_rgba import RgbaPngError, decode_rgba_png


class BodySwayVisualReviewApplicationError(RuntimeError):
    """Raised when exact visual-review evidence cannot be served safely."""


class BodySwayVisualReviewApplicationNotFound(
    BodySwayVisualReviewApplicationError
):
    """Raised when an exact subordinate evidence address is absent."""


class BodySwayVisualReviewApplicationInvalidSubmission(
    BodySwayVisualReviewApplicationError
):
    """Raised when submitted identity does not match current candidates."""


class BodySwayVisualReviewApplication:
    """Share exact read/CAS behavior between CLI and future HTTP adapters."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)
        self._reader = VerifiedBodySwayRuntimeCaptureReader(self.state_root)
        self._store = BodySwayVisualReviewStore(self.state_root)

    def prepare(
        self, address: ExactVisualReviewAddress,
    ) -> PreparedBodySwayVisualReview:
        """Compile current candidates and inspect history without any writes."""

        try:
            capture, candidate = self._load_candidate(address)
            history = self._store.snapshot_history(
                candidates=candidate, capture=capture
            )
            require_consistent_visual_review_history(candidate, history)
            return PreparedBodySwayVisualReview(
                address, candidate.sha256,
                candidate.canonical_bytes.decode("utf-8"), history,
            )
        except BodySwayVisualReviewApplicationError:
            raise
        except _APPLICATION_ERRORS as exc:
            raise BodySwayVisualReviewApplicationError(
                "Visual review preparation failed"
            ) from exc

    def image_evidence(
        self,
        address: ExactVisualReviewAddress,
        *,
        candidate_sha256: str,
        case_id: str,
        png_sha256: str,
    ) -> BodySwayVisualReviewImage:
        """Return bytes only through authoritative candidate case metadata."""

        try:
            expected_candidate = require_sha256(
                candidate_sha256, "Visual review candidate digest"
            )
            expected_case = require_safe_token(case_id, "Visual review case id")
            expected_png = require_sha256(
                png_sha256, "Visual review PNG digest"
            )
            capture, candidate = self._load_candidate(address)
            if candidate.sha256 != expected_candidate:
                raise BodySwayVisualReviewApplicationNotFound(
                    "Visual review candidate address is stale"
                )
            rows = [
                row for row in candidate.document["cases"]
                if row["case_id"] == expected_case
            ]
            if len(rows) != 1 or rows[0]["image"]["png_sha256"] != expected_png:
                raise BodySwayVisualReviewApplicationNotFound(
                    "Visual review image identity is cross-wired"
                )
            row, image = rows[0], rows[0]["image"]
            raw = capture.capture.capture_bytes.get(image["path"])
            if type(raw) is not bytes:
                raise BodySwayVisualReviewApplicationError(
                    "Visual review image bytes are missing"
                )
            decoded = decode_rgba_png(raw, source_name="visual review evidence")
            actual = (hashlib.sha256(raw).hexdigest(), len(raw),
                      decoded.width, decoded.height)
            declared = (expected_png, image["size_bytes"],
                        image["width"], image["height"])
            if actual != declared or actual[2:] != (640, 640):
                raise BodySwayVisualReviewApplicationError(
                    "Visual review image bytes differ from candidate evidence"
                )
            return BodySwayVisualReviewImage(
                candidate.sha256, expected_case, row["evidence_sha256"],
                expected_png, len(raw), decoded.width, decoded.height, raw,
            )
        except BodySwayVisualReviewApplicationError:
            raise
        except _APPLICATION_ERRORS as exc:
            raise BodySwayVisualReviewApplicationError(
                "Visual review image load failed"
            ) from exc

    def exact_decision(
        self,
        address: ExactVisualReviewAddress,
        *,
        candidate_sha256: str,
        revision: int,
        decision_sha256: str,
    ) -> ExactBodySwayVisualReviewDecision:
        """Read one exact historical revision without latest-address fallback."""

        try:
            candidate_address = require_sha256(
                candidate_sha256, "Visual review candidate digest"
            )
            decision_address = require_sha256(
                decision_sha256, "Visual review decision digest"
            )
            if type(revision) is not int \
                    or not 1 <= revision <= MAX_VISUAL_REVIEW_REVISIONS:
                raise BodySwayVisualReviewApplicationError(
                    "Visual review revision address is invalid"
                )
            capture, candidate = self._load_candidate(address)
            if candidate.sha256 != candidate_address:
                raise BodySwayVisualReviewApplicationNotFound(
                    "Visual review candidate address is stale"
                )
            history = self._store.snapshot_history(
                candidates=candidate, capture=capture
            )
            require_consistent_visual_review_history(candidate, history)
            if revision > history.current_revision \
                    or history.rows[revision - 1].decision_sha256 \
                        != decision_address:
                raise BodySwayVisualReviewApplicationNotFound(
                    "Visual review decision address is not an exact revision"
                )
            decision = self._store.load_decision(
                address.project_id, candidate.sha256, decision_address,
                candidates=candidate, capture=capture,
            )
            if decision.document["review"]["revision"] != revision:
                raise BodySwayVisualReviewApplicationError(
                    "Visual review decision revision differs from its address"
                )
            return ExactBodySwayVisualReviewDecision(
                address, candidate.sha256, decision.sha256, revision,
                decision.canonical_bytes.decode("utf-8"),
            )
        except BodySwayVisualReviewApplicationError:
            raise
        except _APPLICATION_ERRORS as exc:
            raise BodySwayVisualReviewApplicationError(
                "Visual review decision load failed"
            ) from exc

    def submit(
        self,
        address: ExactVisualReviewAddress,
        payload: dict[str, Any],
    ) -> SubmittedBodySwayVisualReview:
        """CAS one exhaustive human decision into the immutable linear history."""

        try:
            submission = require_body_sway_visual_review_submission(payload)
            capture, candidate = self._load_candidate(address)
            if submission.candidate_sha256 != candidate.sha256:
                raise BodySwayVisualReviewApplicationInvalidSubmission(
                    "Visual review submission candidate is stale"
                )
            history = self._store.snapshot_history(
                candidates=candidate, capture=capture
            )
            require_consistent_visual_review_history(candidate, history)
            previous = self._previous_decision(
                submission, candidate, capture, history
            )
            decision = build_body_sway_visual_review_decision(
                candidate.document,
                review=submission.review,
                decisions=list(submission.decisions),
                previous_decision=(previous.document if previous else None),
            )
            require_visual_review_compare_and_swap(
                submission, decision.sha256, history
            )
            self._store.publish_candidate(candidate, capture)
            published = self._store.publish_decision(
                decision, candidates=candidate, capture=capture
            )
            loaded = self._store.load_decision(
                address.project_id, candidate.sha256, published.sha256,
                candidates=candidate, capture=capture,
            )
            if loaded.canonical_bytes != decision.canonical_bytes:
                raise BodySwayVisualReviewApplicationError(
                    "Visual review decision readback differs"
                )
            return submitted_visual_review_result(
                address, candidate, loaded.document, loaded.sha256,
                published.reused,
            )
        except BodySwayVisualReviewRevisionConflict:
            raise
        except BodySwayVisualReviewApplicationError:
            raise
        except _APPLICATION_ERRORS as exc:
            raise BodySwayVisualReviewApplicationError(
                "Visual review submission failed"
            ) from exc

    def _load_candidate(self, address):
        if type(address) is not ExactVisualReviewAddress:
            raise BodySwayVisualReviewApplicationError(
                "Visual review requires an exact address"
            )
        capture = self._reader.load(*address.reader_arguments)
        candidate = compile_body_sway_visual_review_candidate(capture)
        return capture, candidate

    def _previous_decision(self, submission, candidate, capture, history):
        base = submission.base_revision
        previous_sha = submission.previous_decision_sha256
        if base == 0:
            return None
        if base > history.current_revision \
                or history.rows[base - 1].decision_sha256 != previous_sha:
            raise visual_review_revision_conflict(submission, history)
        previous = self._store.load_decision(
            candidate.document["project_id"], candidate.sha256, previous_sha,
            candidates=candidate, capture=capture,
        )
        if previous.document["review"]["revision"] != base:
            raise visual_review_revision_conflict(submission, history)
        return previous


_APPLICATION_ERRORS = (
    AttributeError, BodySwayVisualReviewCandidateError,
    BodySwayVisualReviewDecisionError, BodySwayVisualReviewStoreError,
    BodySwayVisualReviewSubmissionError, KeyError, LayerManifestError,
    OSError, OverflowError, RecursionError, RgbaPngError, RuntimeError,
    TypeError, UnicodeError, ValueError,
    VerifiedBodySwayRuntimeCaptureReaderError,
)
