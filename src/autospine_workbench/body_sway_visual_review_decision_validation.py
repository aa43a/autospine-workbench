"""Strict exhaustive human decision validation for P10.3c visual evidence."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_visual_review_candidate_validation import (
    BodySwayVisualReviewCandidateValidationError,
    body_sway_visual_review_candidate_sha256,
    require_body_sway_visual_review_candidate,
)
from .body_sway_visual_review_profile import (
    DECISION_SEMANTICS,
    MAX_CASE_NOTES_LENGTH,
    MAX_REVIEW_NOTES_LENGTH,
    MAX_VISUAL_REVIEW_REVISIONS,
    MAX_VISUAL_REVIEW_DOCUMENT_BYTES,
    body_sway_visual_review_release_gate,
)
from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .resolved_project import canonical_sha256


FORMAT = "autospine-body-sway-visual-review-decision"
FORMAT_VERSION = 1
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "review", "semantics", "decisions", "status", "release_gate", "summary",
}
_SOURCE = {
    "visual_review_candidate_sha256",
    "runtime_capture_manifest_sha256", "runtime_capture_bundle_sha256",
    "temporary_preview_sha256", "capture_artifact_set_sha256",
    "capture_case_stream_sha256", "browser_profile_sha256",
}
_REVIEW = {
    "method", "status", "reviewer_id", "notes", "revision",
    "supersedes_decision_sha256",
}
_DECISION = {"case_id", "evidence_sha256", "action", "notes"}


class BodySwayVisualReviewDecisionValidationError(ValueError):
    """Raised when sampled visual decisions are incomplete or overclaim."""


def require_body_sway_visual_review_decision(
    document: Mapping[str, Any], *,
    candidates: Mapping[str, Any] | None = None,
    previous_decision: Mapping[str, Any] | None = None,
) -> None:
    """Validate shape, exact candidate coverage, and a linear supersede edge."""

    try:
        root = _object(document, "Visual review decision")
        _exact(root, _TOP, "Visual review decision")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise BodySwayVisualReviewDecisionValidationError(
                "Visual review decision format is unsupported"
            )
        require_safe_token(root.get("project_id"), "Visual review project id")
        require_safe_token(root.get("clip_id"), "Visual review clip id")
        _source(root.get("source"))
        _review(root.get("review"))
        counts = _decisions(root.get("decisions"))
        status = (
            "sampled_visual_approved"
            if counts["approve"] == counts["decision"]
            else "sampled_visual_rejected"
        )
        if root.get("status") != status:
            raise BodySwayVisualReviewDecisionValidationError(
                "Visual review status differs from its case decisions"
            )
        expected_semantics = {
            **DECISION_SEMANTICS,
            "sampled_visual_approval_claimed":
                status == "sampled_visual_approved",
        }
        if root.get("semantics") != expected_semantics:
            raise BodySwayVisualReviewDecisionValidationError(
                "Visual review decision semantics are inconsistent"
            )
        if root.get("release_gate") != body_sway_visual_review_release_gate(status):
            raise BodySwayVisualReviewDecisionValidationError(
                "Visual review decision release gate is inconsistent"
            )
        expected_summary = {
            "case_count": counts["decision"],
            "decision_count": counts["decision"],
            "approve_count": counts["approve"],
            "reject_count": counts["reject"],
            "unobservable_count": counts["unobservable"],
        }
        if root.get("summary") != expected_summary:
            raise BodySwayVisualReviewDecisionValidationError(
                "Visual review decision summary is inconsistent"
            )
        if candidates is not None:
            _candidate_binding(root, candidates)
        if previous_decision is not None:
            if candidates is None:
                raise BodySwayVisualReviewDecisionValidationError(
                    "Supersede validation requires exact candidates"
                )
            _previous_binding(root, candidates, previous_decision)
        if len(_canonical(root)) > MAX_VISUAL_REVIEW_DOCUMENT_BYTES:
            raise BodySwayVisualReviewDecisionValidationError(
                "Visual review decision exceeds its byte limit"
            )
    except BodySwayVisualReviewDecisionValidationError:
        raise
    except (
        BodySwayVisualReviewCandidateValidationError,
        LayerManifestError,
        KeyError,
        OverflowError,
        RecursionError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise BodySwayVisualReviewDecisionValidationError(
            f"Visual review decision validation failed: {exc}"
        ) from exc


def body_sway_visual_review_decision_sha256(
    document: Mapping[str, Any],
) -> str:
    require_body_sway_visual_review_decision(document)
    return canonical_sha256(document)


def visual_review_decision_source(
    candidates: Mapping[str, Any],
) -> dict[str, str]:
    require_body_sway_visual_review_candidate(candidates)
    return {
        "visual_review_candidate_sha256":
            body_sway_visual_review_candidate_sha256(candidates),
        **dict(candidates["source"]),
    }


def _candidate_binding(root, candidates) -> None:
    require_body_sway_visual_review_candidate(candidates)
    if root["project_id"] != candidates["project_id"] \
            or root["clip_id"] != candidates["clip_id"] \
            or root["source"] != visual_review_decision_source(candidates):
        raise BodySwayVisualReviewDecisionValidationError(
            "Visual review decision candidate source binding is stale"
        )
    expected = [
        (row["case_id"], row["evidence_sha256"])
        for row in candidates["cases"]
    ]
    actual = [
        (row["case_id"], row["evidence_sha256"])
        for row in root["decisions"]
    ]
    if actual != expected:
        raise BodySwayVisualReviewDecisionValidationError(
            "Visual review decisions do not cover exactly every candidate case"
        )


def _previous_binding(root, candidates, previous) -> None:
    require_body_sway_visual_review_decision(previous, candidates=candidates)
    previous_sha = body_sway_visual_review_decision_sha256(previous)
    review = root["review"]
    previous_review = previous["review"]
    if review["supersedes_decision_sha256"] != previous_sha \
            or review["revision"] != previous_review["revision"] + 1 \
            or root["source"] != previous["source"]:
        raise BodySwayVisualReviewDecisionValidationError(
            "Visual review supersede edge is stale, cross-chain, or non-linear"
        )


def _source(value: Any) -> None:
    row = _object(value, "Visual review decision source")
    _exact(row, _SOURCE, "Visual review decision source")
    for field in _SOURCE:
        require_sha256(row.get(field), field)


def _review(value: Any) -> None:
    row = _object(value, "Visual review metadata")
    _exact(row, _REVIEW, "Visual review metadata")
    require_safe_token(row.get("reviewer_id"), "Visual reviewer id")
    notes = row.get("notes")
    revision = row.get("revision")
    supersedes = row.get("supersedes_decision_sha256")
    if row.get("method") != "human" or row.get("status") != "completed" \
            or type(notes) is not str or len(notes) > MAX_REVIEW_NOTES_LENGTH \
            or type(revision) is not int \
            or not 1 <= revision <= MAX_VISUAL_REVIEW_REVISIONS:
        raise BodySwayVisualReviewDecisionValidationError(
            "Visual review metadata is invalid"
        )
    if revision == 1:
        if supersedes is not None:
            raise BodySwayVisualReviewDecisionValidationError(
                "Initial visual review cannot supersede a decision"
            )
    else:
        require_sha256(supersedes, "Superseded visual decision digest")


def _decisions(value: Any) -> dict[str, int]:
    if not isinstance(value, list) or not 3 <= len(value) <= 55:
        raise BodySwayVisualReviewDecisionValidationError(
            "Visual review decision count is invalid"
        )
    counts = {name: 0 for name in ("approve", "reject", "unobservable")}
    case_ids = set()
    for raw in value:
        row = _object(raw, "Visual review case decision")
        _exact(row, _DECISION, "Visual review case decision")
        case_id = require_safe_token(row.get("case_id"), "Visual review case id")
        require_sha256(row.get("evidence_sha256"), "Case evidence digest")
        action = row.get("action")
        notes = row.get("notes")
        if action not in counts or type(notes) is not str \
                or len(notes) > MAX_CASE_NOTES_LENGTH \
                or action != "approve" and not notes.strip():
            raise BodySwayVisualReviewDecisionValidationError(
                "Visual review case action or notes are invalid"
            )
        counts[action] += 1
        case_ids.add(case_id)
    if len(case_ids) != len(value):
        raise BodySwayVisualReviewDecisionValidationError(
            "Visual review decision case ids must be unique"
        )
    counts["decision"] = len(value)
    return counts


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BodySwayVisualReviewDecisionValidationError(
            f"{label} must be an object"
        )
    return value


def _exact(value, fields, label) -> None:
    if set(value) != fields:
        raise BodySwayVisualReviewDecisionValidationError(
            f"{label} fields are unsupported"
        )


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
