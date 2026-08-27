"""Strict validation for sampled P10.7b raster-review documents."""
from __future__ import annotations
from collections.abc import Mapping
import json
from typing import Any

from .spine42_v3_raster_review_values import (
    Spine42V3RasterReviewError,
    canonical_json,
    canonical_sha256,
    domain_sha256,
    object_value,
    require_candidate_attachments,
    require_candidate_cases,
    require_review_source,
    rows_value,
    self_hash,
    sha_value,
    text_value,
    token_value,
)

CANDIDATE_FORMAT = "autospine-spine42-v3-raster-review-candidate"
DECISION_FORMAT = "autospine-spine42-v3-raster-review-decision"
FORMAT_VERSION = 1
CANDIDATE_SEMANTICS = {
    "scope": "bounded-discrete-samples-only", "candidate_only": True,
    "human_review_claimed": False,
    "sampled_raster_visual_quality_claimed": False,
    "continuous_time_safety_claimed": False, "release_authority": False,
}
CANDIDATE_AUTHORITY = {
    "human_review_authority": False,
    "continuous_runtime_raster_safety_authority": False,
    "persistent_current_head_authority": False,
    "publish_authority": False, "release_authority": False,
}
CANDIDATE_RELEASE_GATE = {
    "status": "blocked", "reason_codes": ["human_raster_review_required"]}
DECISION_SEMANTICS = {
    "scope": "bounded-discrete-samples-only",
    "review_method": "explicit-exhaustive-human-rows",
    "continuous_time_safety_claimed": False, "release_authority": False,
}
DECISION_AUTHORITY = {
    "human_decision_recorded": True,
    "continuous_runtime_raster_safety_authority": False,
    "persistent_current_head_authority": False,
    "publish_authority": False, "release_authority": False,
}
DECISION_RELEASE_GATE = {"status": "blocked", "reason_codes": [
    "continuous_runtime_raster_safety_unproven",
    "persistent_current_head_authority_not_granted",
    "publishable_spine_timeline_not_granted", "release_authority_not_granted",
]}


def require_spine42_v3_raster_review_candidate(value) -> None:
    row = object_value(value, "raster review candidate")
    fields = {
        "format", "format_version", "project_id", "clip_id", "source",
        "metrics_status", "cases", "attachments", "semantics", "authority",
        "status", "release_gate", "candidate_sha256",
    }
    invalid = set(row) != fields or row.get("format") != CANDIDATE_FORMAT \
        or row.get("format_version") != FORMAT_VERSION \
        or row.get("status") != "candidate_only" \
        or row.get("candidate_sha256") != self_hash(
            row, "candidate_sha256", _candidate_domain()) \
        or row.get("semantics") != CANDIDATE_SEMANTICS \
        or row.get("authority") != CANDIDATE_AUTHORITY \
        or row.get("release_gate") != CANDIDATE_RELEASE_GATE
    if invalid:
        raise Spine42V3RasterReviewError("Raster review candidate is invalid")
    token_value(row.get("project_id"), "project id")
    token_value(row.get("clip_id"), "clip id")
    require_review_source(row.get("source"), False)
    cases = require_candidate_cases(row.get("cases"))
    attachments = require_candidate_attachments(row.get("attachments"), cases)
    if row.get("metrics_status") not in {"passed", "rejected"} \
            or (row["metrics_status"] == "passed") != all(
                case["metrics_passed"] for case in cases):
        raise Spine42V3RasterReviewError("Candidate metrics status is invalid")
    isolates = [f["artifact_id"] for item in attachments for f in item["frames"]]
    composites = [item["composite"]["artifact_id"] for item in cases]
    if len(set(isolates)) != len(isolates) \
            or len(set(composites)) != len(composites) \
            or set(isolates) & set(composites):
        raise Spine42V3RasterReviewError("Candidate artifacts are not unique")


def require_spine42_v3_raster_review_decision(
    value, *, candidate: Mapping[str, Any],
    previous_decision: Mapping[str, Any] | None = None,
) -> None:
    require_spine42_v3_raster_review_candidate(candidate)
    row = object_value(value, "raster review decision")
    fields = {
        "format", "format_version", "project_id", "clip_id", "source",
        "review", "case_decisions", "attachment_decisions", "claims",
        "semantics", "authority", "status", "release_gate", "decision_sha256",
    }
    invalid = set(row) != fields or row.get("format") != DECISION_FORMAT \
        or row.get("format_version") != FORMAT_VERSION \
        or row.get("decision_sha256") != self_hash(
            row, "decision_sha256", _decision_domain()) \
        or (row.get("project_id"), row.get("clip_id")) != (
            candidate["project_id"], candidate["clip_id"]) \
        or row.get("semantics") != DECISION_SEMANTICS \
        or row.get("authority") != DECISION_AUTHORITY \
        or row.get("release_gate") != DECISION_RELEASE_GATE
    if invalid:
        raise Spine42V3RasterReviewError("Raster review decision is invalid")
    require_review_source(row.get("source"), True)
    if row["source"] != {
        "candidate_sha256": candidate["candidate_sha256"], **candidate["source"]}:
        raise Spine42V3RasterReviewError("Decision source is inconsistent")
    case_map = {item["case_id"]: item for item in candidate["cases"]}
    attachment_map = {
        item["attachment_key"]: item for item in candidate["attachments"]}
    require_decision_rows(row.get("case_decisions"), case_map, "case_id")
    require_decision_rows(
        row.get("attachment_decisions"), attachment_map, "attachment_key")
    _review(row.get("review"), previous_decision, candidate)
    approved = candidate["metrics_status"] == "passed" and all(
        item["action"] == "approve"
        for item in (*row["case_decisions"], *row["attachment_decisions"]))
    claims = {
        "human_reviewed": True, "sampled_raster_visual_quality": approved,
        "sampled_complete_attachment_inventory_reviewed": approved,
        "continuous_runtime_raster_safety": False,
        "persistent_current_head_authority": False,
        "publishable_spine_timeline": False, "release_authority": False,
    }
    status = "sampled_raster_approved" if approved else "sampled_raster_rejected"
    if row.get("claims") != claims or row.get("status") != status:
        raise Spine42V3RasterReviewError("Decision claims are inconsistent")


def normalized_decision_rows(expected, supplied, key) -> list[dict[str, Any]]:
    rows, expected_map = [dict(item) for item in supplied], {
        row[key]: row for row in expected}
    require_decision_rows(rows, expected_map, key, require_order=False)
    supplied_map = {row[key]: row for row in rows}
    return [supplied_map[identifier] for identifier in expected_map]


def require_decision_rows(rows, expected, key, *, require_order=True) -> None:
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise Spine42V3RasterReviewError("Review decisions are not exhaustive")
    seen = set()
    for row in rows:
        fields = {key, "evidence_sha256", "action", "notes"}
        invalid = not isinstance(row, Mapping) or set(row) != fields \
            or row.get(key) not in expected or row[key] in seen \
            or row.get("evidence_sha256") != expected[row[key]]["evidence_sha256"] \
            or row.get("action") not in {"approve", "reject", "unobservable"}
        if invalid:
            raise Spine42V3RasterReviewError("Review decision row is invalid")
        notes = text_value(row.get("notes"), "decision notes", allow_empty=True)
        if row["action"] != "approve" and not notes.strip():
            raise Spine42V3RasterReviewError(
                "Rejected or unobservable rows require notes")
        seen.add(row[key])
    if require_order and [row[key] for row in rows] != list(expected):
        raise Spine42V3RasterReviewError("Review decision order is invalid")


def capture_shape(root) -> None:
    required = {"project_id", "clip_id", "source", "plan", "artifacts"}
    if not required <= set(root) or root.get("status") != "captured_unreviewed":
        raise Spine42V3RasterReviewError("Capture manifest shape is invalid")
    token_value(root["project_id"], "project id")
    token_value(root["clip_id"], "clip id")


def _review(value, previous, candidate):
    review = object_value(value, "review")
    fields = {"method", "status", "reviewer_id", "notes", "revision",
              "supersedes_decision_sha256"}
    invalid = set(review) != fields or review.get("method") != "human" \
        or review.get("status") != "completed" \
        or type(review.get("revision")) is not int \
        or not 1 <= review["revision"] <= 64
    if invalid:
        raise Spine42V3RasterReviewError("Human review metadata is invalid")
    token_value(review.get("reviewer_id"), "reviewer id")
    text_value(review.get("notes"), "review notes", allow_empty=True)
    if previous is None:
        if review["revision"] != 1 or review["supersedes_decision_sha256"] is not None:
            raise Spine42V3RasterReviewError("Initial review revision is invalid")
        return
    _previous(previous, candidate)
    if review["revision"] != previous["review"]["revision"] + 1 \
            or review["supersedes_decision_sha256"] != previous["decision_sha256"]:
        raise Spine42V3RasterReviewError("Review supersession is invalid")


def _previous(value, candidate):
    previous = object_value(value, "previous decision")
    review = object_value(previous.get("review"), "previous review")
    revision, supersedes = review.get("revision"), review.get(
        "supersedes_decision_sha256")
    patched = json.loads(canonical_json(previous))
    patched["review"].update(revision=1, supersedes_decision_sha256=None)
    patched["decision_sha256"] = self_hash(
        patched, "decision_sha256", _decision_domain())
    require_spine42_v3_raster_review_decision(patched, candidate=candidate)
    invalid = type(revision) is not int or not 1 <= revision <= 64 \
        or (revision == 1 and supersedes is not None) \
        or previous.get("decision_sha256") != self_hash(
            previous, "decision_sha256", _decision_domain())
    if invalid:
        raise Spine42V3RasterReviewError("Previous decision is invalid")
    if revision > 1:
        sha_value(supersedes, "superseded decision")


def _candidate_domain():
    return "autospine-spine42-v3-raster-review-candidate/v1"


def _decision_domain():
    return "autospine-spine42-v3-raster-review-decision/v1"


__all__ = [
    "CANDIDATE_AUTHORITY", "CANDIDATE_FORMAT", "CANDIDATE_RELEASE_GATE",
    "CANDIDATE_SEMANTICS", "DECISION_AUTHORITY", "DECISION_FORMAT",
    "DECISION_RELEASE_GATE", "DECISION_SEMANTICS", "FORMAT_VERSION",
    "Spine42V3RasterReviewError", "canonical_sha256", "capture_shape",
    "domain_sha256", "normalized_decision_rows", "object_value",
    "require_spine42_v3_raster_review_candidate",
    "require_spine42_v3_raster_review_decision", "rows_value", "sha_value",
    "text_value", "token_value",
]
