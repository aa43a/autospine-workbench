"""Exact candidate/decision/P3 binding for ReviewedSeamAnchorSet v1."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .seam_anchor_candidate_validation import (
    SeamAnchorCandidateValidationError,
    require_seam_anchor_candidates,
    seam_anchor_candidates_sha256,
)
from .seam_anchor_review_decision_validation import (
    SeamAnchorReviewDecisionValidationError,
    require_seam_anchor_review_decision,
    seam_anchor_review_decision_sha256,
    seam_anchor_review_decision_source,
)
from .reviewed_seam_anchor_set_profile import REQUIRED_DECISION_STATUS
from .reviewed_seam_anchor_set_validation import (
    ReviewedSeamAnchorSetValidationError,
    require_reviewed_seam_anchor_set,
)


class ReviewedSeamAnchorSetBindingValidationError(ValueError):
    """Raised when a static set is not the exact reviewed projection."""


def reviewed_seam_anchor_set_source(
    candidates: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive the six source fields completing the seven-part address."""

    require_seam_anchor_candidates(candidates)
    require_seam_anchor_review_decision(decision)
    if decision["project_id"] != candidates["project_id"] \
            or decision["source"] \
                != seam_anchor_review_decision_source(candidates):
        raise ReviewedSeamAnchorSetBindingValidationError(
            "Reviewed seam decision differs from its candidate identity"
        )
    return {
        "layer_manifest_sha256": candidates["source"][
            "layer_manifest_sha256"
        ],
        "p3_rig_sha256": candidates["source"]["rig_sha256"],
        "p3_bundle_sha256": candidates["source"]["bundle_sha256"],
        "seam_anchor_candidate_sha256":
            seam_anchor_candidates_sha256(candidates),
        "review_revision": decision["review"]["revision"],
        "seam_anchor_review_decision_sha256":
            seam_anchor_review_decision_sha256(decision),
    }


def require_ready_seam_anchor_review(
    candidates: Mapping[str, Any],
    decision: Mapping[str, Any],
    rig: Mapping[str, Any],
) -> None:
    """Require one exact ready decision; never treat release as proven."""

    try:
        require_seam_anchor_candidates(candidates)
        require_seam_anchor_review_decision(
            decision, candidates=candidates, rig=rig
        )
        actions = tuple(row["action"] for row in decision["decisions"])
        if decision["status"] != REQUIRED_DECISION_STATUS \
                or any(action not in {"accept", "adjust"} for action in actions):
            raise ReviewedSeamAnchorSetBindingValidationError(
                "All six seam relationships need accepted or adjusted anchors"
            )
    except ReviewedSeamAnchorSetBindingValidationError:
        raise
    except (
        KeyError, SeamAnchorCandidateValidationError,
        SeamAnchorReviewDecisionValidationError, TypeError, ValueError,
    ) as exc:
        raise ReviewedSeamAnchorSetBindingValidationError(
            f"Reviewed seam readiness binding failed: {exc}"
        ) from exc


def require_bound_reviewed_seam_anchor_set(
    document: Mapping[str, Any],
    candidates: Mapping[str, Any],
    decision: Mapping[str, Any],
    rig: Mapping[str, Any],
) -> None:
    """Rebuild the authoritative projection and compare it exactly."""

    try:
        require_reviewed_seam_anchor_set(document)
        require_ready_seam_anchor_review(candidates, decision, rig)
        expected = expected_reviewed_seam_anchor_projection(
            candidates, decision
        )
        if document["project_id"] != candidates["project_id"] \
                or document["source"] != expected["source"] \
                or document["relationships"] != expected["relationships"]:
            raise ReviewedSeamAnchorSetBindingValidationError(
                "Reviewed seam anchor set differs from its exact inputs"
            )
    except ReviewedSeamAnchorSetBindingValidationError:
        raise
    except (
        KeyError, SeamAnchorCandidateValidationError,
        SeamAnchorReviewDecisionValidationError,
        ReviewedSeamAnchorSetValidationError, TypeError, ValueError,
    ) as exc:
        raise ReviewedSeamAnchorSetBindingValidationError(
            f"Reviewed seam anchor binding failed: {exc}"
        ) from exc


def expected_reviewed_seam_anchor_projection(candidates, decision):
    """Project only materialized static anchor rows; select no alternatives."""

    return {
        "source": reviewed_seam_anchor_set_source(candidates, decision),
        "relationships": [
            {
                "relationship_id": row["relationship_id"],
                "anchors": _copy(row["anchors"]),
            }
            for row in decision["decisions"]
        ],
    }


def _copy(value: Any) -> Any:
    from .seam_anchor_review_json import canonical_json_copy

    return canonical_json_copy(value)
