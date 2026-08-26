"""Authoritative replay boundaries for P10.3c capture and candidate values."""

from __future__ import annotations

from pathlib import Path

from .body_sway_runtime_capture_binding import (
    BodySwayRuntimeCaptureBindingError,
    reload_authoritative_runtime_capture,
)
from .body_sway_runtime_capture_reader import (
    VerifiedBodySwayRuntimeCapture,
)
from .body_sway_visual_review_candidate import BodySwayVisualReviewCandidate
from .body_sway_visual_review_candidate_validation import (
    BodySwayVisualReviewCandidateValidationError,
    require_body_sway_visual_review_candidate,
)
from .body_sway_visual_review_profile import CANDIDATE_NAMESPACE
from .body_sway_visual_review_store_files import (
    BodySwayVisualReviewFilesError,
    exact_payload,
    read_document,
)


class BodySwayVisualReviewBindingError(RuntimeError):
    """Raised when detached values differ from authoritative store replay."""


def reload_authoritative_visual_review_candidate(
    state_root: Path,
    supplied: BodySwayVisualReviewCandidate,
    capture: VerifiedBodySwayRuntimeCapture,
) -> tuple[BodySwayVisualReviewCandidate, VerifiedBodySwayRuntimeCapture]:
    """Reload published capture and candidate before accepting human decisions."""

    try:
        if type(supplied) is not BodySwayVisualReviewCandidate:
            raise BodySwayVisualReviewBindingError(
                "Visual review candidate value has the wrong representation"
            )
        loaded_capture = reload_authoritative_runtime_capture(state_root, capture)
        document = supplied.document
        require_body_sway_visual_review_candidate(
            document, capture=loaded_capture
        )
        digest = supplied.sha256
        expected = exact_payload(supplied.canonical_bytes, document, digest)
        actual = read_document(
            state_root,
            document["project_id"],
            CANDIDATE_NAMESPACE,
            loaded_capture.bundle_sha256,
            digest,
        )
        if actual != expected:
            raise BodySwayVisualReviewBindingError(
                "Supplied candidate differs from authoritative store replay"
            )
        return BodySwayVisualReviewCandidate(actual.decode("utf-8")), loaded_capture
    except BodySwayVisualReviewBindingError:
        raise
    except (
        BodySwayVisualReviewCandidateValidationError,
        BodySwayVisualReviewFilesError,
        BodySwayRuntimeCaptureBindingError,
        AttributeError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise BodySwayVisualReviewBindingError(
            f"Authoritative visual candidate replay failed: {exc}"
        ) from exc
