"""Strict user-authored payload boundary for P10.3c visual review."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any

from .body_sway_visual_review_profile import (
    MAX_CASE_NOTES_LENGTH,
    MAX_REVIEW_NOTES_LENGTH,
    MAX_VISUAL_REVIEW_DOCUMENT_BYTES,
    MAX_VISUAL_REVIEW_REVISIONS,
)
from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)


class BodySwayVisualReviewSubmissionError(ValueError):
    """Raised when a user payload is ambiguous, excessive, or unsupported."""


@dataclass(frozen=True, slots=True)
class BodySwayVisualReviewSubmission:
    """Normalized user fields; derived revision and authority fields are absent."""

    base_revision: int
    candidate_sha256: str
    previous_decision_sha256: str | None
    review: dict[str, str]
    decisions: tuple[dict[str, str], ...]


def require_body_sway_visual_review_submission(
    value: Mapping[str, Any],
) -> BodySwayVisualReviewSubmission:
    """Validate and copy the only fields a human review client may provide."""

    try:
        if not isinstance(value, Mapping) or set(value) != _TOP_FIELDS:
            raise BodySwayVisualReviewSubmissionError(
                "Visual review submission fields are unsupported"
            )
        payload = _json_copy(value)
        if len(_canonical(payload)) > MAX_VISUAL_REVIEW_DOCUMENT_BYTES:
            raise BodySwayVisualReviewSubmissionError(
                "Visual review submission exceeds its byte limit"
            )
        base = payload["base_revision"]
        if type(base) is not int \
                or not 0 <= base < MAX_VISUAL_REVIEW_REVISIONS:
            raise BodySwayVisualReviewSubmissionError(
                "Visual review base revision is invalid"
            )
        candidate_sha = require_sha256(
            payload["candidate_sha256"], "Visual review candidate digest"
        )
        previous_sha = payload["previous_decision_sha256"]
        if base == 0:
            if previous_sha is not None:
                raise BodySwayVisualReviewSubmissionError(
                    "Initial visual review predecessor must be null"
                )
        else:
            previous_sha = require_sha256(
                previous_sha, "Visual review predecessor digest"
            )
        review = _review(payload["review"])
        decisions = _decisions(payload["decisions"])
        return BodySwayVisualReviewSubmission(
            base, candidate_sha, previous_sha, review, decisions
        )
    except BodySwayVisualReviewSubmissionError:
        raise
    except (
        KeyError, LayerManifestError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayVisualReviewSubmissionError(
            "Visual review submission is invalid"
        ) from exc


def _review(value: Any) -> dict[str, str]:
    if type(value) is not dict or set(value) != {"reviewer_id", "notes"}:
        raise BodySwayVisualReviewSubmissionError(
            "Visual review metadata fields are unsupported"
        )
    reviewer = require_safe_token(value["reviewer_id"], "Visual reviewer id")
    notes = value["notes"]
    if type(notes) is not str or len(notes) > MAX_REVIEW_NOTES_LENGTH:
        raise BodySwayVisualReviewSubmissionError(
            "Visual review notes are invalid"
        )
    return {"reviewer_id": reviewer, "notes": notes}


def _decisions(value: Any) -> tuple[dict[str, str], ...]:
    if type(value) is not list or not 3 <= len(value) <= 55:
        raise BodySwayVisualReviewSubmissionError(
            "Visual review decision count is invalid"
        )
    rows = []
    case_ids = set()
    for value_row in value:
        if type(value_row) is not dict or set(value_row) != _DECISION_FIELDS:
            raise BodySwayVisualReviewSubmissionError(
                "Visual review decision fields are unsupported"
            )
        case_id = require_safe_token(
            value_row["case_id"], "Visual review case id"
        )
        evidence_sha = require_sha256(
            value_row["evidence_sha256"], "Visual review evidence digest"
        )
        action, notes = value_row["action"], value_row["notes"]
        if action not in {"approve", "reject", "unobservable"} \
                or type(notes) is not str \
                or len(notes) > MAX_CASE_NOTES_LENGTH \
                or action != "approve" and not notes.strip():
            raise BodySwayVisualReviewSubmissionError(
                "Visual review action or notes are invalid"
            )
        if case_id in case_ids:
            raise BodySwayVisualReviewSubmissionError(
                "Visual review case ids must be unique"
            )
        case_ids.add(case_id)
        rows.append({
            "case_id": case_id,
            "evidence_sha256": evidence_sha,
            "action": action,
            "notes": notes,
        })
    return tuple(rows)


def _json_copy(value: Any) -> dict[str, Any]:
    return json.loads(_canonical(value).decode("utf-8"))


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


_TOP_FIELDS = {
    "base_revision", "candidate_sha256", "previous_decision_sha256",
    "review", "decisions",
}
_DECISION_FIELDS = {"case_id", "evidence_sha256", "action", "notes"}
