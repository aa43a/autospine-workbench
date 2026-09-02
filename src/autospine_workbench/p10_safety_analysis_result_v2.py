"""Cross-layer result binding and redacted P10.4b v2 public receipt."""

from __future__ import annotations

from .p10_safety_analysis_manager_error_v2 import (
    P10SafetyAnalysisManagerV2Error,
)
from .p10_safety_analysis_v2_commands import P10SafetyAnalysisV2CommandError


def require_request_job(request, completed) -> None:
    address = completed.address
    expected = {
        "project_id": address.project_id,
        "temporary_preview_v2_sha256": address.temporary_preview_v2_sha256,
        "runtime_execution_bundle_sha256":
            address.runtime_execution_bundle_sha256,
        "capture_artifact_set_sha256": address.capture_artifact_set_sha256,
    }
    if request["job_id"] != completed.job_id \
            or request["package_id"] != completed.package_id \
            or request["terminal_event_sha256"] \
                != completed.terminal_event_sha256 \
            or request["terminal_sequence"] != completed.terminal_sequence \
            or request["capture_address"] != expected:
        raise P10SafetyAnalysisManagerV2Error(
            "Safety analysis request differs from its completed job"
        )


def require_compiled_result(request, result) -> None:
    admission = result._admission._result
    address = request["capture_address"]
    if result.job_id != request["job_id"] \
            or result.package_id != request["package_id"] \
            or result.project_id != address["project_id"] \
            or admission.terminal_event_sha256 \
                != request["terminal_event_sha256"] \
            or admission.terminal_sequence != request["terminal_sequence"] \
            or admission.temporary_preview_v2_sha256 \
                != address["temporary_preview_v2_sha256"] \
            or admission.runtime_execution_bundle_sha256 \
                != address["runtime_execution_bundle_sha256"] \
            or admission.capture_artifact_set_sha256 \
                != address["capture_artifact_set_sha256"]:
        raise P10SafetyAnalysisV2CommandError(
            "Compiled analysis differs from its launch request"
        )


def public_result(job_id, run, amplitude, continuous):
    probes = [{
        "gain": row["gain"], "status": row["status"],
        "visual_review_status": row["visual_review_status"],
    } for row in amplitude["probes"]]
    segments = [{
        "left_tick": row["left_tick"], "right_tick": row["right_tick"],
        "status": row["status"], "reason_codes": row["reason_codes"],
    } for row in continuous["segments"]]
    sealed = run["result"]
    documents = {
        "amplitude": _document_receipt(amplitude, sealed, "amplitude"),
        "continuous": _document_receipt(continuous, sealed, "continuous"),
    }
    summary = continuous["summary"]
    claims = continuous["claims"]
    release = continuous["release_gate"]
    return {
        "ok": True, "status": "completed", "job_id": job_id,
        "authority_scope": "compile_time_snapshot", "run": run,
        "project_id": continuous["project_id"],
        "clip_id": continuous["clip_id"],
        "admission": {
            "sha256": sealed["admission_sha256"],
            "visual_candidate_sha256": sealed["visual_candidate_sha256"],
            "visual_revision": sealed["visual_revision"],
            "visual_decision_sha256": sealed["visual_decision_sha256"],
        },
        "amplitude": {
            "sha256": sealed["amplitude_sha256"],
            "status": amplitude["status"], "probes": probes,
        },
        "continuous": {
            "sha256": sealed["continuous_sha256"],
            "status": continuous["status"], "summary": {
                "segment_count": summary["segment_count"],
                "certified_segment_count":
                    summary["certified_segment_count"],
                "indeterminate_segment_count":
                    summary["indeterminate_segment_count"],
            }, "segments": segments,
        },
        "claims": {key: claims[key] for key in _CLAIM_FIELDS},
        "release_gate": {
            "status": release["status"],
            "reason_codes": release["reason_codes"],
        },
        "documents": documents,
    }


def _document_receipt(document, sealed, kind):
    return {
        "format": document["format"],
        "format_version": document["format_version"],
        "sha256": sealed[f"{kind}_sha256"],
        "size_bytes": sealed[f"{kind}_size_bytes"],
    }


_CLAIM_FIELDS = (
    "continuous_preview_model_structural_safety",
    "uniform_gain_zero_to_reviewed_structurally_certified",
    "official_runtime_continuous_equivalence", "visual_gain_range",
    "reviewed_seam_anchors", "motion_instance_v3",
    "publishable_timeline", "release_authority",
)


__all__ = [
    "public_result", "require_compiled_result", "require_request_job",
]
