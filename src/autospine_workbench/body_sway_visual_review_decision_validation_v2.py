"""Strict exhaustive human-decision validation for P10.3c v2 evidence."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_visual_review_candidate_validation_v2 import (
    BodySwayVisualReviewCandidateV2ValidationError,
    body_sway_visual_review_candidate_sha256_v2,
    require_body_sway_visual_review_candidate_v2,
    require_body_sway_visual_review_source_v2,
)
from .body_sway_visual_review_profile_v2 import (
    DECISION_SEMANTICS,
    MAX_CASE_NOTES_LENGTH,
    MAX_REVIEW_NOTES_LENGTH,
    MAX_VISUAL_REVIEW_DOCUMENT_BYTES,
    MAX_VISUAL_REVIEW_REVISIONS,
    body_sway_visual_review_release_gate_v2,
)
from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .resolved_project import canonical_sha256


FORMAT = "autospine-body-sway-visual-review-decision"
FORMAT_VERSION = 2
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "review", "semantics", "decisions", "status", "release_gate", "summary",
}
_SOURCE = {
    "visual_review_candidate_v2_sha256", "runtime_execution_sha256",
    "runtime_execution_bundle_sha256", "runtime_capture_v2_sha256",
    "temporary_preview_v2_sha256", "preview_artifact_set_sha256",
    "capture_artifact_set_sha256", "runtime_session_set_v2_sha256",
    "capture_plan_v2_sha256", "capture_case_stream_sha256",
    "browser_profile_sha256", "capture_framing_candidate_sha256",
    "capture_framing_decision_sha256", "capture_framing_revision",
    "body_sway_probe_report_sha256", "current_p10_1_head", "world_viewport",
}
_REVIEW = {
    "method", "status", "reviewer_id", "notes", "revision",
    "supersedes_decision_sha256",
}
_DECISION = {"case_id", "evidence_sha256", "action", "notes"}


class BodySwayVisualReviewDecisionV2ValidationError(ValueError):
    """Raised when v2 human choices are incomplete, stale, or overclaim."""


def require_body_sway_visual_review_decision_v2(
    document: Mapping[str, Any], *,
    candidates: Mapping[str, Any] | None = None,
    previous_decision: Mapping[str, Any] | None = None,
) -> None:
    try:
        root = _object(document, "decision")
        _exact(root, _TOP, "decision")
        if root.get("format") != FORMAT \
                or root.get("format_version") != FORMAT_VERSION:
            raise BodySwayVisualReviewDecisionV2ValidationError(
                "Visual review decision v2 format is unsupported"
            )
        require_safe_token(root.get("project_id"), "Visual review v2 project")
        require_safe_token(root.get("clip_id"), "Visual review v2 clip")
        _source(root.get("source"))
        _review(root.get("review"))
        counts = _decisions(root.get("decisions"))
        status = "sampled_visual_approved" \
            if counts["approve"] == counts["decision"] \
            else "sampled_visual_rejected"
        if root.get("status") != status:
            raise BodySwayVisualReviewDecisionV2ValidationError(
                "Visual review decision v2 status is inconsistent"
            )
        semantics = {
            **DECISION_SEMANTICS,
            "sampled_visual_approval_claimed":
                status == "sampled_visual_approved",
        }
        if root.get("semantics") != semantics \
                or root.get("release_gate") \
                != body_sway_visual_review_release_gate_v2(status):
            raise BodySwayVisualReviewDecisionV2ValidationError(
                "Visual review decision v2 claims are inconsistent"
            )
        summary = {
            "case_count": counts["decision"],
            "decision_count": counts["decision"],
            "approve_count": counts["approve"],
            "reject_count": counts["reject"],
            "unobservable_count": counts["unobservable"],
        }
        if root.get("summary") != summary:
            raise BodySwayVisualReviewDecisionV2ValidationError(
                "Visual review decision v2 summary is inconsistent"
            )
        if candidates is not None:
            _candidate_binding(root, candidates)
        if previous_decision is not None:
            if candidates is None:
                raise BodySwayVisualReviewDecisionV2ValidationError(
                    "Visual review v2 supersede validation requires candidates"
                )
            _previous_binding(root, candidates, previous_decision)
        if len(_canonical(root)) > MAX_VISUAL_REVIEW_DOCUMENT_BYTES:
            raise BodySwayVisualReviewDecisionV2ValidationError(
                "Visual review decision v2 exceeds its byte limit"
            )
    except BodySwayVisualReviewDecisionV2ValidationError:
        raise
    except (
        BodySwayVisualReviewCandidateV2ValidationError, LayerManifestError,
        KeyError, OverflowError, RecursionError, TypeError, UnicodeError,
        ValueError,
    ) as exc:
        raise BodySwayVisualReviewDecisionV2ValidationError(
            f"Visual review decision v2 validation failed: {exc}"
        ) from exc


def body_sway_visual_review_decision_sha256_v2(document) -> str:
    require_body_sway_visual_review_decision_v2(document)
    return canonical_sha256(document)


def visual_review_decision_source_v2(candidates) -> dict[str, Any]:
    require_body_sway_visual_review_candidate_v2(candidates)
    return {
        "visual_review_candidate_v2_sha256":
            body_sway_visual_review_candidate_sha256_v2(candidates),
        **dict(candidates["source"]),
    }


def _candidate_binding(root, candidates) -> None:
    require_body_sway_visual_review_candidate_v2(candidates)
    if root["project_id"] != candidates["project_id"] \
            or root["clip_id"] != candidates["clip_id"] \
            or root["source"] != visual_review_decision_source_v2(candidates):
        raise BodySwayVisualReviewDecisionV2ValidationError(
            "Visual review decision v2 candidate binding is stale"
        )
    expected = [(row["case_id"], row["evidence_sha256"])
                for row in candidates["cases"]]
    actual = [(row["case_id"], row["evidence_sha256"])
              for row in root["decisions"]]
    if actual != expected:
        raise BodySwayVisualReviewDecisionV2ValidationError(
            "Visual review decision v2 must cover every candidate in order"
        )


def _previous_binding(root, candidates, previous) -> None:
    require_body_sway_visual_review_decision_v2(
        previous, candidates=candidates,
    )
    review = root["review"]
    if review["supersedes_decision_sha256"] \
            != body_sway_visual_review_decision_sha256_v2(previous) \
            or review["revision"] != previous["review"]["revision"] + 1 \
            or root["source"] != previous["source"]:
        raise BodySwayVisualReviewDecisionV2ValidationError(
            "Visual review decision v2 supersede edge is not linear"
        )


def _source(value) -> None:
    row = _object(value, "source")
    _exact(row, _SOURCE, "source")
    require_sha256(
        row.get("visual_review_candidate_v2_sha256"),
        "Visual review candidate v2",
    )
    require_body_sway_visual_review_source_v2({
        key: value for key, value in row.items()
        if key != "visual_review_candidate_v2_sha256"
    })


def _review(value) -> None:
    row = _object(value, "review")
    _exact(row, _REVIEW, "review")
    require_safe_token(row.get("reviewer_id"), "Visual reviewer v2")
    notes, revision = row.get("notes"), row.get("revision")
    supersedes = row.get("supersedes_decision_sha256")
    if row.get("method") != "human" or row.get("status") != "completed" \
            or type(notes) is not str or len(notes) > MAX_REVIEW_NOTES_LENGTH \
            or type(revision) is not int \
            or not 1 <= revision <= MAX_VISUAL_REVIEW_REVISIONS:
        raise BodySwayVisualReviewDecisionV2ValidationError(
            "Visual review decision v2 metadata is invalid"
        )
    if revision == 1 and supersedes is not None:
        raise BodySwayVisualReviewDecisionV2ValidationError(
            "Initial visual review v2 cannot supersede another decision"
        )
    if revision > 1:
        require_sha256(supersedes, "Superseded visual decision v2")


def _decisions(value) -> dict[str, int]:
    if not isinstance(value, list) or not 3 <= len(value) <= 55:
        raise BodySwayVisualReviewDecisionV2ValidationError(
            "Visual review decision v2 count is invalid"
        )
    counts = {name: 0 for name in ("approve", "reject", "unobservable")}
    ids = set()
    for raw in value:
        row = _object(raw, "case decision")
        _exact(row, _DECISION, "case decision")
        case_id = require_safe_token(row.get("case_id"), "Visual review v2 case")
        require_sha256(row.get("evidence_sha256"), "Visual evidence v2")
        action, notes = row.get("action"), row.get("notes")
        if action not in counts or type(notes) is not str \
                or len(notes) > MAX_CASE_NOTES_LENGTH \
                or action != "approve" and not notes.strip():
            raise BodySwayVisualReviewDecisionV2ValidationError(
                "Visual review decision v2 action or notes are invalid"
            )
        counts[action] += 1
        ids.add(case_id)
    if len(ids) != len(value):
        raise BodySwayVisualReviewDecisionV2ValidationError(
            "Visual review decision v2 case ids are duplicated"
        )
    counts["decision"] = len(value)
    return counts


def _object(value, label):
    if not isinstance(value, Mapping):
        raise BodySwayVisualReviewDecisionV2ValidationError(
            f"Visual review decision v2 {label} must be an object"
        )
    return value


def _exact(value, fields, label) -> None:
    if set(value) != fields:
        raise BodySwayVisualReviewDecisionV2ValidationError(
            f"Visual review decision v2 {label} fields are unsupported"
        )


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")
