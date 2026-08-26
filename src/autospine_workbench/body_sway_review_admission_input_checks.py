"""Detached identity and stable-head checks for P10.4a admission inputs."""

from __future__ import annotations

import json
from typing import Any

from .body_sway_visual_review_candidate_validation import (
    BodySwayVisualReviewCandidateValidationError,
    body_sway_visual_review_candidate_sha256,
    require_body_sway_visual_review_candidate,
)
from .body_sway_visual_review_decision_validation import (
    BodySwayVisualReviewDecisionValidationError,
    body_sway_visual_review_decision_sha256,
    require_body_sway_visual_review_decision,
)
from .body_sway_visual_review_history_snapshot import (
    BodySwayVisualReviewHistorySnapshot,
)
from .body_sway_visual_review_profile import MAX_VISUAL_REVIEW_REVISIONS
from .manifest_artifacts import LayerManifestError, require_sha256


class BodySwayReviewAdmissionInputCheckError(ValueError):
    """Raised when detached admission snapshots are inconsistent."""


def require_body_sway_review_admission_input_content(value, preview) -> None:
    """Validate public candidate restoration, identities, and approved head."""

    try:
        candidate_sha = require_sha256(
            value.visual_candidate_sha256, "Visual candidate digest"
        )
        decision_sha = require_sha256(
            value.visual_decision_sha256, "Visual decision digest"
        )
        if type(value.visual_revision) is not int \
                or not 1 <= value.visual_revision <= MAX_VISUAL_REVIEW_REVISIONS:
            raise BodySwayReviewAdmissionInputCheckError(
                "Visual decision revision is invalid"
            )
        candidate = _restore_candidate_paths(value.candidate_document)
        require_body_sway_visual_review_candidate(
            candidate, capture=value._capture
        )
        decision = value.decision_document
        require_body_sway_visual_review_decision(
            decision, candidates=candidate
        )
        _require_identities(value, preview, candidate, decision)
        _require_approved_stable_head(value, candidate_sha, decision_sha)
    except BodySwayReviewAdmissionInputCheckError:
        raise
    except _FAILURES as exc:
        raise BodySwayReviewAdmissionInputCheckError(
            f"Body-sway review input checks failed: {exc}"
        ) from exc


def _require_identities(value, preview, candidate, decision) -> None:
    address = value.address
    source = candidate["source"]
    capture = value._capture.capture.document
    capture_address = (
        value._capture.project_id, value._capture.temporary_preview_sha256,
        value._capture.bundle_sha256, value._capture.artifact_set_sha256,
    )
    if preview.sha256 != address.temporary_preview_sha256 \
            or body_sway_visual_review_candidate_sha256(candidate) \
                != value.visual_candidate_sha256 \
            or body_sway_visual_review_decision_sha256(decision) \
                != value.visual_decision_sha256 \
            or capture_address != address.reader_arguments \
            or source["runtime_capture_manifest_sha256"] \
                != value._capture.capture.sha256 \
            or preview.document["project_id"] != address.project_id \
            or candidate["project_id"] != address.project_id \
            or decision["project_id"] != address.project_id \
            or preview.document["clip_id"] != candidate["clip_id"] \
            or candidate["clip_id"] != decision["clip_id"] \
            or capture["source"]["upstream"] != preview.document["source"] \
            or capture["source"]["preview_artifact_set_sha256"] \
                != preview.artifact_set_sha256 \
            or capture["timing"] != preview.document["timing"] \
            or capture["selection"] != preview.document["selection"] \
            or source["temporary_preview_sha256"] \
                != address.temporary_preview_sha256 \
            or source["runtime_capture_bundle_sha256"] \
                != address.runtime_capture_bundle_sha256 \
            or source["capture_artifact_set_sha256"] \
                != address.capture_artifact_set_sha256:
        raise BodySwayReviewAdmissionInputCheckError(
            "Preview, capture, candidate, and decision identities are cross-wired"
        )


def _require_approved_stable_head(value, candidate_sha, decision_sha) -> None:
    before, after = value.history_before, value.history_after
    if type(before) is not BodySwayVisualReviewHistorySnapshot \
            or type(after) is not BodySwayVisualReviewHistorySnapshot \
            or before != after:
        raise BodySwayReviewAdmissionInputCheckError(
            "Visual review head changed during compile-time observation"
        )
    revision = value.visual_revision
    if before.project_id != value.address.project_id \
            or before.candidate_sha256 != candidate_sha \
            or before.revision_count != len(before.rows) \
            or before.current_revision != revision \
            or before.revision_count != revision \
            or before.head_decision_sha256 != decision_sha \
            or len(before.rows) != revision \
            or before.rows[-1].revision != revision \
            or before.rows[-1].decision_sha256 != decision_sha \
            or before.rows[-1].status != "sampled_visual_approved":
        raise BodySwayReviewAdmissionInputCheckError(
            "Only the current sampled_visual_approved head is admissible"
        )
    document = value.decision_document
    if document["review"]["revision"] != revision \
            or document["status"] != "sampled_visual_approved" \
            or any(row["action"] != "approve" for row in document["decisions"]):
        raise BodySwayReviewAdmissionInputCheckError(
            "Visual decision does not approve every sampled case"
        )


def _restore_candidate_paths(public: dict[str, Any]) -> dict[str, Any]:
    candidate = json.loads(_canonical(public))
    for row in candidate.get("cases", []):
        image = row.get("image")
        case_id = row.get("case_id")
        if not isinstance(image, dict) or "path" in image \
                or type(case_id) is not str:
            raise BodySwayReviewAdmissionInputCheckError(
                "Public visual candidate shape is invalid"
            )
        image["path"] = f"captures/{case_id}.png"
    return candidate


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


_FAILURES = (
    AttributeError, BodySwayVisualReviewCandidateValidationError,
    BodySwayVisualReviewDecisionValidationError, KeyError,
    LayerManifestError, OverflowError, RecursionError, RuntimeError,
    TypeError, UnicodeError, ValueError,
)
