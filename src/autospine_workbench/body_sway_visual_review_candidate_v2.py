"""Pure candidate-only P10.3c v2 compiler from execution evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .body_sway_runtime_execution_reader import VerifiedBodySwayRuntimeExecution
from .body_sway_visual_review_candidate_validation_v2 import (
    FORMAT,
    FORMAT_VERSION,
    BodySwayVisualReviewCandidateV2ValidationError,
    require_body_sway_visual_review_candidate_v2,
)
from .body_sway_visual_review_candidate_source_v2 import (
    body_sway_visual_review_source_v2,
    visual_review_case_rows_v2,
)
from .body_sway_visual_review_profile_v2 import (
    CANDIDATE_GENERATOR,
    CANDIDATE_RELEASE_GATE,
    CANDIDATE_SEMANTICS,
)
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2


class BodySwayVisualReviewCandidateV2Error(ValueError):
    """Raised when current Preview v2 cannot form execution-bound candidates."""


@dataclass(frozen=True, slots=True)
class BodySwayVisualReviewCandidateV2:
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


def compile_body_sway_visual_review_candidate_v2(
    execution: VerifiedBodySwayRuntimeExecution,
    preview: TemporaryBodySwayPreviewV2,
) -> BodySwayVisualReviewCandidateV2:
    """Expose every official still without inventing a human decision."""

    try:
        source = body_sway_visual_review_source_v2(execution)
        cases = visual_review_case_rows_v2(execution)
        document = {
            "format": FORMAT, "format_version": FORMAT_VERSION,
            "project_id": execution.execution.document["project_id"],
            "clip_id": execution.execution.document["clip_id"],
            "source": source,
            "generator": _copy(CANDIDATE_GENERATOR),
            "semantics": _copy(CANDIDATE_SEMANTICS),
            "cases": cases,
            "status": "candidate_only",
            "release_gate": _copy(CANDIDATE_RELEASE_GATE),
            "summary": {
                "case_count": len(cases), "pending_count": len(cases),
                "status": "candidate_only",
            },
        }
        require_body_sway_visual_review_candidate_v2(
            document, execution=execution, preview=preview,
        )
        return BodySwayVisualReviewCandidateV2(_canonical(document))
    except BodySwayVisualReviewCandidateV2Error:
        raise
    except (
        BodySwayVisualReviewCandidateV2ValidationError, AttributeError,
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayVisualReviewCandidateV2Error(
            f"Visual review candidate v2 compilation failed: {exc}"
        ) from exc


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


__all__ = [
    "BodySwayVisualReviewCandidateV2",
    "BodySwayVisualReviewCandidateV2Error",
    "compile_body_sway_visual_review_candidate_v2",
]
