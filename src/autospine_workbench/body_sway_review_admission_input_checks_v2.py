"""Identity and stable-head checks for P10.4a v2 admission inputs."""

from __future__ import annotations

import json
from typing import Any

from .body_sway_visual_review_candidate_validation_v2 import (
    BodySwayVisualReviewCandidateV2ValidationError,
    body_sway_visual_review_candidate_sha256_v2,
    require_body_sway_visual_review_candidate_v2,
)
from .body_sway_visual_review_decision_validation_v2 import (
    BodySwayVisualReviewDecisionV2ValidationError,
    body_sway_visual_review_decision_sha256_v2,
    require_body_sway_visual_review_decision_v2,
)
from .body_sway_visual_review_history_snapshot_v2 import (
    BodySwayVisualReviewHistorySnapshotV2,
)
from .body_sway_visual_review_profile_v2 import MAX_VISUAL_REVIEW_REVISIONS
from .manifest_artifacts import (
    LayerManifestError, require_sha256,
)
from .p10_completed_job_snapshot import (
    P10CompletedJobSnapshotError,
    require_verified_completed_p10_capture_job,
)


class BodySwayReviewAdmissionInputV2CheckError(ValueError):
    """Raised when detached P10.4a v2 snapshots are inconsistent."""


def require_body_sway_review_admission_input_v2_content(value, preview) -> None:
    try:
        job = require_sha256(value.job_id, "Runtime capture job")
        event = require_sha256(
            value.job_terminal_event_sha256,
            "Runtime capture terminal event",
        )
        package = require_sha256(
            value.package_id, "Runtime capture package",
        )
        candidate_sha = require_sha256(
            value.visual_candidate_sha256, "Visual candidate v2",
        )
        decision_sha = require_sha256(
            value.visual_decision_sha256, "Visual decision v2",
        )
        if not job or not event or not package:
            raise BodySwayReviewAdmissionInputV2CheckError(
                "Runtime capture job identity is invalid"
            )
        if type(value.job_terminal_sequence) is not int \
                or value.job_terminal_sequence < 1:
            raise BodySwayReviewAdmissionInputV2CheckError(
                "Runtime capture terminal sequence is invalid"
            )
        completed_job = require_verified_completed_p10_capture_job(
            value._completed_job,
        )
        if job != completed_job.job_id \
                or package != completed_job.package_id \
                or event != completed_job.terminal_event_sha256 \
                or value.job_terminal_sequence \
                    != completed_job.terminal_sequence \
                or value.address != completed_job.address:
            raise BodySwayReviewAdmissionInputV2CheckError(
                "Runtime capture identity differs from its completed chain"
            )
        if type(value.visual_revision) is not int \
                or not 1 <= value.visual_revision \
                    <= MAX_VISUAL_REVIEW_REVISIONS:
            raise BodySwayReviewAdmissionInputV2CheckError(
                "Visual decision v2 revision is invalid"
            )
        candidate = _restore_candidate_paths(value.candidate_document)
        require_body_sway_visual_review_candidate_v2(
            candidate, execution=value._execution, preview=preview,
        )
        decision = value.decision_document
        require_body_sway_visual_review_decision_v2(
            decision, candidates=candidate,
        )
        _require_identities(
            value, preview, candidate, decision,
            candidate_sha, decision_sha,
        )
        _require_approved_stable_head(value, candidate_sha, decision_sha)
    except BodySwayReviewAdmissionInputV2CheckError:
        raise
    except _FAILURES as exc:
        raise BodySwayReviewAdmissionInputV2CheckError(
            f"Body-sway review admission v2 input checks failed: {exc}"
        ) from exc


def _require_identities(
    value, preview, candidate, decision, candidate_sha, decision_sha,
) -> None:
    address = value.address
    execution = value._execution
    execution_source = execution.execution.document["source"]
    if preview.sha256 != address.temporary_preview_v2_sha256 \
            or preview.document["project_id"] != address.project_id \
            or execution.project_id != address.project_id \
            or execution.temporary_preview_v2_sha256 \
                != address.temporary_preview_v2_sha256 \
            or execution.bundle_sha256 \
                != address.runtime_execution_bundle_sha256 \
            or execution.artifact_set_sha256 \
                != address.capture_artifact_set_sha256 \
            or execution_source["preview_artifact_set_sha256"] \
                != preview.artifact_set_sha256 \
            or body_sway_visual_review_candidate_sha256_v2(candidate) \
                != candidate_sha \
            or body_sway_visual_review_decision_sha256_v2(decision) \
                != decision_sha \
            or candidate["project_id"] != address.project_id \
            or decision["project_id"] != address.project_id \
            or candidate["clip_id"] != preview.document["clip_id"] \
            or decision["clip_id"] != preview.document["clip_id"]:
        raise BodySwayReviewAdmissionInputV2CheckError(
            "Job, execution, preview, candidate, and decision are cross-wired"
        )


def _require_approved_stable_head(value, candidate_sha, decision_sha) -> None:
    before, after = value.history_before, value.history_after
    if type(before) is not BodySwayVisualReviewHistorySnapshotV2 \
            or type(after) is not BodySwayVisualReviewHistorySnapshotV2 \
            or before != after:
        raise BodySwayReviewAdmissionInputV2CheckError(
            "Visual review v2 head changed during compile-time observation"
        )
    revision = value.visual_revision
    if before.project_id != value.address.project_id \
            or before.candidate_sha256 != candidate_sha \
            or before.revision_count != len(before.rows) \
            or before.current_revision != revision \
            or before.revision_count != revision \
            or before.head_decision_sha256 != decision_sha \
            or not before.rows \
            or before.rows[-1].revision != revision \
            or before.rows[-1].decision_sha256 != decision_sha \
            or before.rows[-1].status != "sampled_visual_approved":
        raise BodySwayReviewAdmissionInputV2CheckError(
            "Only the current sampled_visual_approved v2 head is admissible"
        )
    document = value.decision_document
    if document["review"]["revision"] != revision \
            or document["status"] != "sampled_visual_approved" \
            or any(row["action"] != "approve"
                   for row in document["decisions"]):
        raise BodySwayReviewAdmissionInputV2CheckError(
            "Visual decision v2 does not approve every sampled case"
        )


def _restore_candidate_paths(public: dict[str, Any]) -> dict[str, Any]:
    candidate = json.loads(_canonical(public))
    for row in candidate.get("cases", []):
        image, case_id = row.get("image"), row.get("case_id")
        if not isinstance(image, dict) or "path" in image \
                or type(case_id) is not str:
            raise BodySwayReviewAdmissionInputV2CheckError(
                "Public visual candidate v2 shape is invalid"
            )
        image["path"] = f"captures/{case_id}.png"
    return candidate


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


_FAILURES = (
    AttributeError, BodySwayVisualReviewCandidateV2ValidationError,
    BodySwayVisualReviewDecisionV2ValidationError, KeyError,
    LayerManifestError, OverflowError, P10CompletedJobSnapshotError,
    RecursionError, RuntimeError,
    TypeError, UnicodeError, ValueError,
)


__all__ = [
    "BodySwayReviewAdmissionInputV2CheckError",
    "require_body_sway_review_admission_input_v2_content",
]
