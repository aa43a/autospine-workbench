"""Pure compiler for candidate-only P10.3c sampled visual evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .body_sway_runtime_capture_reader import VerifiedBodySwayRuntimeCapture
from .body_sway_runtime_capture_binding import (
    BodySwayRuntimeCaptureBindingError,
    require_internally_valid_runtime_capture,
)
from .body_sway_visual_review_candidate_validation import (
    FORMAT,
    FORMAT_VERSION,
    BodySwayVisualReviewCandidateValidationError,
    body_sway_visual_review_source,
    require_body_sway_visual_review_candidate,
    visual_review_case_rows,
)
from .body_sway_visual_review_profile import (
    CANDIDATE_GENERATOR,
    CANDIDATE_RELEASE_GATE,
    CANDIDATE_SEMANTICS,
)


class BodySwayVisualReviewCandidateError(ValueError):
    """Raised when an exact capture cannot form review candidates."""


@dataclass(frozen=True, slots=True)
class BodySwayVisualReviewCandidate:
    """Frozen canonical candidate value with no human decisions."""

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


def compile_body_sway_visual_review_candidate(
    capture: VerifiedBodySwayRuntimeCapture,
) -> BodySwayVisualReviewCandidate:
    """Expose all stills for review without inferring any human decision."""

    try:
        require_internally_valid_runtime_capture(capture)
        capture_document = capture.capture.document
        cases = visual_review_case_rows(capture)
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": capture_document["project_id"],
            "clip_id": capture_document["clip_id"],
            "source": body_sway_visual_review_source(capture),
            "generator": _copy(CANDIDATE_GENERATOR),
            "semantics": _copy(CANDIDATE_SEMANTICS),
            "cases": cases,
            "status": "candidate_only",
            "release_gate": _copy(CANDIDATE_RELEASE_GATE),
            "summary": {
                "case_count": len(cases),
                "pending_count": len(cases),
                "status": "candidate_only",
            },
        }
        require_body_sway_visual_review_candidate(document, capture=capture)
        return BodySwayVisualReviewCandidate(_canonical(document))
    except BodySwayVisualReviewCandidateError:
        raise
    except (
        BodySwayVisualReviewCandidateValidationError,
        BodySwayRuntimeCaptureBindingError,
        KeyError,
        OverflowError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise BodySwayVisualReviewCandidateError(
            f"Visual review candidate compilation failed: {exc}"
        ) from exc


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
