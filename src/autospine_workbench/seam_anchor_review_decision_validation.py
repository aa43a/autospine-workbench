"""Strict detached and candidate-bound validation for P10.5b decisions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .resolved_project import canonical_sha256
from .seam_anchor_candidate_fields import SeamAnchorCandidateFieldError
from .seam_anchor_candidate_validation import (
    SeamAnchorCandidateValidationError,
    require_seam_anchor_candidates,
    seam_anchor_candidates_sha256,
)
from .seam_anchor_profile import SEAM_SOURCE_IDENTITY_FIELDS
from .seam_anchor_review_binding_validation import (
    SeamAnchorReviewBindingValidationError,
    require_materialized_seam_anchor_review_rows,
)
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)
from .seam_anchor_review_decision_rows import (
    require_seam_anchor_review_decision_rows,
)
from .seam_anchor_review_profile import (
    DECISION_SEMANTICS,
    MAX_REVIEW_JSON_DEPTH,
    MAX_REVIEW_JSON_NODES,
    MAX_REVIEW_NOTES_LENGTH,
    MAX_SEAM_ANCHOR_REVIEW_DOCUMENT_BYTES,
    MAX_SEAM_ANCHOR_REVIEW_REVISIONS,
    seam_anchor_review_release_gate,
)


FORMAT = "autospine-seam-anchor-review-decision"
FORMAT_VERSION = 1


class SeamAnchorReviewDecisionValidationError(ValueError):
    """Raised when a seam-review decision is incomplete or overclaims."""


def require_seam_anchor_review_decision(
    document: Mapping[str, Any], *,
    candidates: Mapping[str, Any] | None = None,
    rig: Mapping[str, Any] | None = None,
    previous_decision: Mapping[str, Any] | None = None,
) -> None:
    """Validate shape and optionally exact candidate/P3/history bindings."""

    try:
        if type(document) is not dict:
            raise SeamAnchorReviewDecisionValidationError(
                "Seam-review decision must be an exact object"
            )
        require_bounded_json_tree(
            document, max_nodes=MAX_REVIEW_JSON_NODES,
            max_depth=MAX_REVIEW_JSON_DEPTH,
        )
        _exact(document, _TOP, "Seam-review decision")
        if document.get("format") != FORMAT \
                or type(document.get("format_version")) is not int \
                or document["format_version"] != FORMAT_VERSION:
            raise SeamAnchorReviewDecisionValidationError(
                "Seam-review decision format is unsupported"
            )
        require_safe_token(document.get("project_id"), "Seam project id")
        _source(document.get("source"))
        _review(document.get("review"))
        counts = require_seam_anchor_review_decision_rows(
            document.get("decisions")
        )
        status = _status(counts)
        if document.get("status") != status \
                or document.get("semantics") != DECISION_SEMANTICS \
                or document.get("release_gate") \
                    != seam_anchor_review_release_gate(status) \
                or document.get("summary") != _summary(counts):
            raise SeamAnchorReviewDecisionValidationError(
                "Seam-review derived status fields are inconsistent"
            )
        if (candidates is None) != (rig is None):
            raise SeamAnchorReviewDecisionValidationError(
                "Candidate-bound seam validation also requires exact P3"
            )
        if candidates is not None:
            _candidate_binding(document, candidates, rig)
        if previous_decision is not None:
            if candidates is None:
                raise SeamAnchorReviewDecisionValidationError(
                    "Seam supersede validation requires candidate and P3"
                )
            _previous_binding(
                document, candidates, rig, previous_decision
            )
        if len(canonical_json_bytes(document)) \
                > MAX_SEAM_ANCHOR_REVIEW_DOCUMENT_BYTES:
            raise SeamAnchorReviewDecisionValidationError(
                "Seam-review decision exceeds its byte limit"
            )
    except SeamAnchorReviewDecisionValidationError:
        raise
    except (
        KeyError, LayerManifestError, OverflowError, RecursionError,
        SeamAnchorCandidateFieldError,
        SeamAnchorCandidateValidationError,
        SeamAnchorReviewBindingValidationError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise SeamAnchorReviewDecisionValidationError(
            f"Seam-review decision validation failed: {exc}"
        ) from exc


def seam_anchor_review_decision_sha256(
    document: Mapping[str, Any],
) -> str:
    require_seam_anchor_review_decision(document)
    return canonical_sha256(document)


def seam_anchor_review_decision_source(
    candidates: Mapping[str, Any],
) -> dict[str, str]:
    require_seam_anchor_candidates(candidates)
    return {
        "seam_anchor_candidate_sha256":
            seam_anchor_candidates_sha256(candidates),
        **dict(candidates["source"]),
    }


def _candidate_binding(root, candidates, rig) -> None:
    require_seam_anchor_candidates(candidates)
    if root["project_id"] != candidates["project_id"] \
            or root["source"] != seam_anchor_review_decision_source(candidates):
        raise SeamAnchorReviewDecisionValidationError(
            "Seam-review candidate source binding is stale"
        )
    require_materialized_seam_anchor_review_rows(
        candidates, rig, root["decisions"]
    )


def _previous_binding(root, candidates, rig, previous) -> None:
    require_seam_anchor_review_decision(
        previous, candidates=candidates, rig=rig
    )
    previous_sha = seam_anchor_review_decision_sha256(previous)
    review, prior = root["review"], previous["review"]
    if review["supersedes_decision_sha256"] != previous_sha \
            or review["revision"] != prior["revision"] + 1 \
            or root["source"] != previous["source"]:
        raise SeamAnchorReviewDecisionValidationError(
            "Seam-review supersede edge is stale or non-linear"
        )


def _source(value: Any) -> None:
    if type(value) is not dict:
        raise SeamAnchorReviewDecisionValidationError(
            "Seam-review source must be an object"
        )
    fields = {"seam_anchor_candidate_sha256", *SEAM_SOURCE_IDENTITY_FIELDS}
    _exact(value, fields, "Seam-review source")
    for field in fields:
        require_sha256(value.get(field), field)


def _review(value: Any) -> None:
    if type(value) is not dict:
        raise SeamAnchorReviewDecisionValidationError(
            "Seam-review metadata must be an object"
        )
    _exact(value, _REVIEW, "Seam-review metadata")
    require_safe_token(value.get("reviewer_id"), "Seam reviewer id")
    notes, revision = value.get("notes"), value.get("revision")
    supersedes = value.get("supersedes_decision_sha256")
    if value.get("method") != "human" or value.get("status") != "completed" \
            or type(notes) is not str or len(notes) > MAX_REVIEW_NOTES_LENGTH \
            or type(revision) is not int \
            or not 1 <= revision <= MAX_SEAM_ANCHOR_REVIEW_REVISIONS:
        raise SeamAnchorReviewDecisionValidationError(
            "Seam-review metadata is invalid"
        )
    if revision == 1:
        if supersedes is not None:
            raise SeamAnchorReviewDecisionValidationError(
                "Initial seam review cannot supersede another decision"
            )
    else:
        require_sha256(supersedes, "Superseded seam decision digest")


def _status(counts) -> str:
    return (
        "reviewed_anchor_set_ready_for_compile"
        if counts["accept"] + counts["adjust"] == counts["decision"]
        else "reviewed_anchor_set_blocked"
    )


def _summary(counts) -> dict[str, int]:
    return {
        "relationship_count": 6,
        "decision_count": counts["decision"],
        "accept_count": counts["accept"],
        "adjust_count": counts["adjust"],
        "reject_count": counts["reject"],
        "unobservable_count": counts["unobservable"],
        "anchor_pair_count": counts["anchors"],
    }


def _exact(value, fields, label) -> None:
    if len(value) != len(fields) or any(field not in value for field in fields):
        raise SeamAnchorReviewDecisionValidationError(
            f"{label} fields are unsupported"
        )


_TOP = {
    "format", "format_version", "project_id", "source", "review",
    "semantics", "decisions", "status", "release_gate", "summary",
}
_REVIEW = {
    "method", "status", "reviewer_id", "notes", "revision",
    "supersedes_decision_sha256",
}
