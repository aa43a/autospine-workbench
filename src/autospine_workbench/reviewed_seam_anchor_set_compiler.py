"""Pure compiler for one exact P10.5c ReviewedSeamAnchorSet v1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .seam_anchor_candidate_validation import SeamAnchorCandidateValidationError
from .seam_anchor_review_decision_validation import (
    SeamAnchorReviewDecisionValidationError,
)
from .seam_anchor_review_json import canonical_json_bytes, canonical_json_copy
from .reviewed_seam_anchor_set_binding_validation import (
    ReviewedSeamAnchorSetBindingValidationError,
    expected_reviewed_seam_anchor_projection,
    require_bound_reviewed_seam_anchor_set,
    require_ready_seam_anchor_review,
)
from .reviewed_seam_anchor_set_profile import (
    CLAIMS,
    FORMAT,
    FORMAT_VERSION,
    RELEASE_GATE,
    SEMANTICS,
    reviewed_seam_anchor_set_compiler_profile,
)
from .reviewed_seam_anchor_set_validation import (
    ReviewedSeamAnchorSetValidationError,
    reviewed_seam_anchor_set_sha256,
)


class ReviewedSeamAnchorSetCompilerError(ValueError):
    """Raised when exact reviewed inputs cannot form one static set."""


@dataclass(frozen=True, slots=True)
class ReviewedSeamAnchorSet:
    """Frozen canonical artifact with isolated document access."""

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


def compile_reviewed_seam_anchor_set(
    candidates: Mapping[str, Any],
    decision: Mapping[str, Any],
    rig: Mapping[str, Any],
) -> ReviewedSeamAnchorSet:
    """Compile only six reviewed materialized rows; infer no fallback."""

    try:
        require_ready_seam_anchor_review(candidates, decision, rig)
        projection = expected_reviewed_seam_anchor_projection(
            candidates, decision
        )
        anchor_count = sum(
            len(row["anchors"]) for row in projection["relationships"]
        )
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": candidates["project_id"],
            "source": projection["source"],
            "compiler": reviewed_seam_anchor_set_compiler_profile(),
            "semantics": canonical_json_copy(SEMANTICS),
            "relationships": projection["relationships"],
            "status": "reviewed_static_anchor_set_compiled",
            "claims": canonical_json_copy(CLAIMS),
            "release_gate": canonical_json_copy(RELEASE_GATE),
            "summary": {
                "relationship_count": len(projection["relationships"]),
                "anchor_pair_count": anchor_count,
            },
        }
        require_bound_reviewed_seam_anchor_set(
            document, candidates, decision, rig
        )
        result = ReviewedSeamAnchorSet(
            canonical_json_bytes(document).decode("utf-8")
        )
        if result.sha256 != reviewed_seam_anchor_set_sha256(result.document):
            raise ReviewedSeamAnchorSetCompilerError(
                "Reviewed seam anchor set identity is inconsistent"
            )
        return result
    except ReviewedSeamAnchorSetCompilerError:
        raise
    except (
        KeyError, OverflowError, RecursionError,
        SeamAnchorCandidateValidationError,
        SeamAnchorReviewDecisionValidationError,
        ReviewedSeamAnchorSetBindingValidationError,
        ReviewedSeamAnchorSetValidationError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise ReviewedSeamAnchorSetCompilerError(
            f"Reviewed seam anchor set compilation failed: {exc}"
        ) from exc
