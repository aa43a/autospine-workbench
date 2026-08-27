"""Strict user-authored payload boundary for P10.5b seam review."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .seam_anchor_review_profile import (
    MAX_RELATIONSHIP_NOTES_LENGTH,
    MAX_REVIEW_JSON_DEPTH,
    MAX_REVIEW_JSON_NODES,
    MAX_REVIEW_NOTES_LENGTH,
    MAX_SEAM_ANCHOR_REVIEW_DOCUMENT_BYTES,
    MAX_SEAM_ANCHOR_REVIEW_REVISIONS,
)
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)


class SeamAnchorReviewSubmissionError(ValueError):
    """Raised when a human seam-review payload is unsafe or ambiguous."""


@dataclass(frozen=True, slots=True)
class SeamAnchorReviewSubmission:
    base_revision: int
    candidate_sha256: str
    previous_decision_sha256: str | None
    review: dict[str, str]
    decisions: tuple[dict[str, Any], ...]


def require_seam_anchor_review_submission(
    value: Any,
) -> SeamAnchorReviewSubmission:
    """Copy only explicit human fields; reject derived authority fields."""

    try:
        if type(value) is not dict or len(value) != len(_TOP) \
                or any(field not in value for field in _TOP):
            raise SeamAnchorReviewSubmissionError(
                "Seam-review submission fields are unsupported"
            )
        require_bounded_json_tree(
            value, max_nodes=MAX_REVIEW_JSON_NODES,
            max_depth=MAX_REVIEW_JSON_DEPTH,
        )
        encoded = canonical_json_bytes(value)
        if len(encoded) > MAX_SEAM_ANCHOR_REVIEW_DOCUMENT_BYTES:
            raise SeamAnchorReviewSubmissionError(
                "Seam-review submission exceeds its byte limit"
            )
        payload = json.loads(encoded.decode("utf-8"))
        base = payload["base_revision"]
        if type(base) is not int \
                or not 0 <= base < MAX_SEAM_ANCHOR_REVIEW_REVISIONS:
            raise SeamAnchorReviewSubmissionError(
                "Seam-review base revision is invalid"
            )
        candidate_sha = require_sha256(
            payload["candidate_sha256"], "Seam candidate digest"
        )
        previous = payload["previous_decision_sha256"]
        if base == 0:
            if previous is not None:
                raise SeamAnchorReviewSubmissionError(
                    "Initial seam review predecessor must be null"
                )
        else:
            previous = require_sha256(
                previous, "Seam-review predecessor digest"
            )
        return SeamAnchorReviewSubmission(
            base, candidate_sha, previous,
            _review(payload["review"]),
            _decisions(payload["decisions"]),
        )
    except SeamAnchorReviewSubmissionError:
        raise
    except (
        KeyError, LayerManifestError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise SeamAnchorReviewSubmissionError(
            "Seam-review submission is invalid"
        ) from exc


def _review(value: Any) -> dict[str, str]:
    if type(value) is not dict or set(value) != {"reviewer_id", "notes"}:
        raise SeamAnchorReviewSubmissionError(
            "Seam-review metadata fields are unsupported"
        )
    reviewer = require_safe_token(value["reviewer_id"], "Seam reviewer id")
    notes = value["notes"]
    if type(notes) is not str or len(notes) > MAX_REVIEW_NOTES_LENGTH:
        raise SeamAnchorReviewSubmissionError(
            "Seam-review notes are invalid"
        )
    return {"reviewer_id": reviewer, "notes": notes}


def _decisions(value: Any) -> tuple[dict[str, Any], ...]:
    if type(value) is not list or len(value) != 6:
        raise SeamAnchorReviewSubmissionError(
            "Seam review must cover the fixed six relationships"
        )
    rows, identifiers = [], set()
    for raw in value:
        if type(raw) is not dict:
            raise SeamAnchorReviewSubmissionError(
                "Seam relationship decision must be an object"
            )
        action = raw.get("action")
        expected = _ROW | ({"final_anchors"} if action == "adjust" else set())
        if len(raw) != len(expected) or any(key not in raw for key in expected):
            raise SeamAnchorReviewSubmissionError(
                "Seam relationship decision fields are unsupported"
            )
        identifier = require_safe_token(
            raw["relationship_id"], "Seam relationship id"
        )
        evidence = require_sha256(
            raw["relationship_evidence_sha256"],
            "Seam relationship evidence digest",
        )
        if action not in {"accept", "adjust", "reject", "unobservable"}:
            raise SeamAnchorReviewSubmissionError(
                "Seam relationship action is unsupported"
            )
        option_id, option_sha = raw["option_id"], raw["option_evidence_sha256"]
        if (option_id is None) != (option_sha is None):
            raise SeamAnchorReviewSubmissionError(
                "Seam option identity must be complete or null"
            )
        if option_id is not None:
            option_id = require_safe_token(option_id, "Seam option id")
            option_sha = require_sha256(option_sha, "Seam option evidence digest")
        notes = raw["notes"]
        if type(notes) is not str or len(notes) > MAX_RELATIONSHIP_NOTES_LENGTH \
                or action != "accept" and not notes.strip():
            raise SeamAnchorReviewSubmissionError(
                "Seam relationship decision notes are invalid"
            )
        if identifier in identifiers:
            raise SeamAnchorReviewSubmissionError(
                "Seam relationship decisions must be unique"
            )
        identifiers.add(identifier)
        row = {
            "relationship_id": identifier,
            "relationship_evidence_sha256": evidence,
            "action": action,
            "option_id": option_id,
            "option_evidence_sha256": option_sha,
            "notes": notes,
        }
        if action == "adjust":
            anchors = raw["final_anchors"]
            if type(anchors) is not list or not 2 <= len(anchors) <= 8:
                raise SeamAnchorReviewSubmissionError(
                    "Adjusted seam anchors must contain two to eight pairs"
                )
            row["final_anchors"] = anchors
        rows.append(row)
    return tuple(rows)


_TOP = {
    "base_revision", "candidate_sha256", "previous_decision_sha256",
    "review", "decisions",
}
_ROW = {
    "relationship_id", "relationship_evidence_sha256", "action",
    "option_id", "option_evidence_sha256", "notes",
}
