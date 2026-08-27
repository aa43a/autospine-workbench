"""Candidate and decision compilers for sampled P10.7b raster review."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any

from .spine42_v3_raster_metrics import spine42_v3_raster_metrics_sha256
from .spine42_v3_raster_review_evidence import (
    verified_spine42_v3_review_inventory,
)
from .spine42_v3_raster_review_validation import (
    CANDIDATE_AUTHORITY,
    CANDIDATE_FORMAT,
    CANDIDATE_RELEASE_GATE,
    CANDIDATE_SEMANTICS,
    DECISION_AUTHORITY,
    DECISION_FORMAT,
    DECISION_RELEASE_GATE,
    DECISION_SEMANTICS,
    FORMAT_VERSION,
    Spine42V3RasterReviewError,
    canonical_sha256,
    capture_shape,
    domain_sha256,
    normalized_decision_rows,
    object_value,
    require_spine42_v3_raster_review_candidate,
    require_spine42_v3_raster_review_decision,
    rows_value,
    sha_value,
    text_value,
    token_value,
)


def compile_spine42_v3_raster_review_candidate(
    manifest: Mapping[str, Any],
    metrics: Mapping[str, Any],
    *,
    capture_bundle_sha256: str,
) -> dict[str, Any]:
    """Build candidate-only rows from one exact stored capture package."""

    root, report = object_value(manifest, "capture manifest"), object_value(
        metrics, "raster metrics"
    )
    capture_shape(root)
    metrics_sha = spine42_v3_raster_metrics_sha256(report)
    bundle_sha = sha_value(capture_bundle_sha256, "capture bundle")
    source = object_value(root["source"], "capture source")
    plan, artifacts, metric_cases, verified_metrics_sha = \
        verified_spine42_v3_review_inventory(root, report)
    if metrics_sha != verified_metrics_sha:
        raise Spine42V3RasterReviewError("Raster metrics identity changed")
    cases = [
        _case_candidate(case, artifacts, metric_cases)
        for case in rows_value(plan["cases"], "capture cases")
    ]
    attachments = [
        _attachment_candidate(row, cases, artifacts, metric_cases)
        for row in rows_value(plan["attachments"], "attachments")
    ]
    passed = report["summary"].get("all_sampled_cases_passed") is True
    body = {
        "format": CANDIDATE_FORMAT, "format_version": FORMAT_VERSION,
        "project_id": root["project_id"], "clip_id": root["clip_id"],
        "source": {
            "skeleton_json_sha256": source["skeleton_json_sha256"],
            "spine42_v3_bundle_sha256": source["spine42_v3_bundle_sha256"],
            "run_document_sha256": source["run_document_sha256"],
            "capture_plan_sha256": source["capture_plan_sha256"],
            "runtime_session_set_sha256": source[
                "runtime_session_set_sha256"
            ],
            "runtime_capture_manifest_sha256": canonical_sha256(root),
            "runtime_capture_bundle_sha256": bundle_sha,
            "raster_metrics_sha256": metrics_sha,
        },
        "metrics_status": "passed" if passed else "rejected",
        "cases": cases, "attachments": attachments,
        "semantics": dict(CANDIDATE_SEMANTICS),
        "authority": dict(CANDIDATE_AUTHORITY),
        "status": "candidate_only",
        "release_gate": _copy(CANDIDATE_RELEASE_GATE),
    }
    body["candidate_sha256"] = domain_sha256(
        "autospine-spine42-v3-raster-review-candidate/v1", body
    )
    require_spine42_v3_raster_review_candidate(body)
    return body


def build_spine42_v3_raster_review_decision(
    candidate: Mapping[str, Any], *, reviewer_id: str, notes: str,
    case_decisions: Sequence[Mapping[str, Any]],
    attachment_decisions: Sequence[Mapping[str, Any]],
    previous_decision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind explicit human choices; non-approval rows fail closed."""

    require_spine42_v3_raster_review_candidate(candidate)
    cases = normalized_decision_rows(
        candidate["cases"], case_decisions, "case_id"
    )
    attachments = normalized_decision_rows(
        candidate["attachments"], attachment_decisions, "attachment_key"
    )
    if previous_decision is None:
        revision, supersedes = 1, None
    else:
        previous = object_value(previous_decision, "previous decision")
        previous_review = object_value(previous.get("review"), "previous review")
        revision = previous_review.get("revision")
        if type(revision) is not int:
            raise Spine42V3RasterReviewError("Previous revision is invalid")
        revision, supersedes = revision + 1, previous.get("decision_sha256")
    approved = candidate["metrics_status"] == "passed" and all(
        row["action"] == "approve" for row in (*cases, *attachments)
    )
    body = {
        "format": DECISION_FORMAT, "format_version": FORMAT_VERSION,
        "project_id": candidate["project_id"],
        "clip_id": candidate["clip_id"],
        "source": {
            "candidate_sha256": candidate["candidate_sha256"],
            **candidate["source"],
        },
        "review": {
            "method": "human", "status": "completed",
            "reviewer_id": token_value(reviewer_id, "reviewer id"),
            "notes": text_value(notes, "review notes", allow_empty=True),
            "revision": revision,
            "supersedes_decision_sha256": supersedes,
        },
        "case_decisions": cases, "attachment_decisions": attachments,
        "claims": {
            "human_reviewed": True,
            "sampled_raster_visual_quality": approved,
            "sampled_complete_attachment_inventory_reviewed": approved,
            "continuous_runtime_raster_safety": False,
            "persistent_current_head_authority": False,
            "publishable_spine_timeline": False,
            "release_authority": False,
        },
        "semantics": dict(DECISION_SEMANTICS),
        "authority": dict(DECISION_AUTHORITY),
        "status": "sampled_raster_approved" if approved
            else "sampled_raster_rejected",
        "release_gate": _copy(DECISION_RELEASE_GATE),
    }
    body["decision_sha256"] = domain_sha256(
        "autospine-spine42-v3-raster-review-decision/v1", body
    )
    require_spine42_v3_raster_review_decision(
        body, candidate=candidate, previous_decision=previous_decision
    )
    return body


def _case_candidate(case, artifacts, metrics):
    selected = [artifacts[item] for item in case["artifact_ids"]]
    opaque = next(row for row in selected if row["kind"] == "opaque_composite")
    metric = metrics[case["case_id"]]
    result = {
        "case_id": case["case_id"], "tick": case["tick"],
        "time_seconds": case["time_seconds"],
        "composite": {key: opaque[key] for key in (
            "artifact_id", "stored_path", "sha256", "size_bytes"
        )},
        "metrics_passed": metric["passed"],
        "reason_codes": metric["reason_codes"],
    }
    result["evidence_sha256"] = domain_sha256("p10.7b-case/v1", result)
    return result


def _attachment_candidate(attachment, cases, artifacts, metric_cases):
    frames = []
    for case in cases:
        metric = next(row for row in metric_cases[case["case_id"]][
            "attachment_isolates"
        ] if row["slot_id"] == attachment["slot_id"]
            and row["attachment_id"] == attachment["attachment_id"])
        artifact = next(row for row in artifacts.values()
                        if row["case_id"] == case["case_id"]
                        and row["kind"] == "attachment_isolate"
                        and row["slot_id"] == attachment["slot_id"]
                        and row["attachment_id"] == attachment["attachment_id"])
        frames.append({
            "case_id": case["case_id"], "artifact_id": artifact["artifact_id"],
            "stored_path": artifact["stored_path"], "sha256": artifact["sha256"],
            "nonempty": metric["nonempty"],
            "boundary_pixels": metric["boundary_pixels"],
            "clipped_boundary_pixels": metric["clipped_boundary_pixels"],
        })
    result = {
        "attachment_key": (
            f"{attachment['slot_id']}::{attachment['attachment_id']}"
        ), **attachment, "frames": frames,
    }
    result["evidence_sha256"] = domain_sha256(
        "p10.7b-attachment/v1", result
    )
    return result


def canonical_spine42_v3_raster_review_bytes(value) -> bytes:
    """Serialize one already validated review document canonically."""

    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode()


def _copy(value):
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":")))


__all__ = [
    "Spine42V3RasterReviewError",
    "build_spine42_v3_raster_review_decision",
    "canonical_spine42_v3_raster_review_bytes",
    "compile_spine42_v3_raster_review_candidate",
    "require_spine42_v3_raster_review_candidate",
    "require_spine42_v3_raster_review_decision",
]
