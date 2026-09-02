"""Exact persisted-result binding for P10.4b v2 asynchronous runs."""

from __future__ import annotations

from .body_sway_amplitude_envelope_validation_v2 import (
    body_sway_amplitude_envelope_candidate_sha256_v2,
    require_body_sway_amplitude_envelope_candidate_v2,
)
from .body_sway_continuous_proof_validation_v2 import (
    require_sealed_body_sway_continuous_preview_proof_v2,
)
from .p10_safety_analysis_job_validation_v2 import require_result_address
from .resolved_project import canonical_sha256


class P10SafetyAnalysisResultValidationV2Error(ValueError):
    """Raised when sealed v2 documents are stale or cross-wired."""


def require_p10_safety_analysis_result_v2(
    snapshot, amplitude, continuous,
) -> None:
    require_p10_safety_analysis_result_documents_v2(
        snapshot.request.document,
        snapshot.events[-1].document["result"],
        amplitude, continuous,
    )


def require_p10_safety_analysis_result_documents_v2(
    request, sealed, amplitude, continuous,
) -> None:
    """Validate staged or completed documents against one exact request."""

    try:
        require_body_sway_amplitude_envelope_candidate_v2(amplitude)
        require_sealed_body_sway_continuous_preview_proof_v2(continuous)
        sealed = require_result_address(sealed)
        candidate = continuous["source"][
            "amplitude_envelope_candidate_v2"
        ]
        admission = amplitude["source"]["review_admission_v2"]
        source = admission["source"]
        job, evidence = source["job"], source["evidence"]
        visual = source["visual_review"]
        address = request["capture_address"]
        if candidate != amplitude \
                or continuous["source"][
                    "amplitude_envelope_candidate_v2_sha256"
                ] != body_sway_amplitude_envelope_candidate_sha256_v2(
                    amplitude
                ) \
                or sealed["admission_sha256"] \
                    != amplitude["source"]["review_admission_v2_sha256"] \
                or sealed["authority_scope"] != "compile_time_snapshot" \
                or sealed["amplitude_sha256"] \
                    != canonical_sha256(amplitude) \
                or sealed["continuous_sha256"] \
                    != canonical_sha256(continuous) \
                or request["analyzers_sha256"] != canonical_sha256({
                    "domain": "autospine-p10-safety-analyzers/v2",
                    "amplitude": amplitude["analyzer"],
                    "continuous": continuous["analyzer"],
                }) \
                or job != {
                    "job_id": request["job_id"],
                    "package_id": request["package_id"],
                    "terminal_event_sha256":
                        request["terminal_event_sha256"],
                    "terminal_sequence": request["terminal_sequence"],
                } \
                or admission["project_id"] != address["project_id"] \
                or evidence["temporary_preview_v2_sha256"] \
                    != address["temporary_preview_v2_sha256"] \
                or evidence["runtime_execution_bundle_sha256"] \
                    != address["runtime_execution_bundle_sha256"] \
                or evidence["capture_artifact_set_sha256"] \
                    != address["capture_artifact_set_sha256"] \
                or sealed["visual_candidate_sha256"] \
                    != visual["candidate_v2_sha256"] \
                or sealed["visual_revision"] != visual["revision"] \
                or sealed["visual_decision_sha256"] \
                    != visual["decision_v2_sha256"] \
                or visual["decision_v2_sha256"] \
                    != visual["head_decision_v2_sha256"]:
            raise P10SafetyAnalysisResultValidationV2Error(
                "Safety analysis result source chain is cross-wired"
            )
    except P10SafetyAnalysisResultValidationV2Error:
        raise
    except Exception as exc:
        raise P10SafetyAnalysisResultValidationV2Error(
            "Safety analysis result validation failed"
        ) from exc


__all__ = [
    "P10SafetyAnalysisResultValidationV2Error",
    "require_p10_safety_analysis_result_documents_v2",
    "require_p10_safety_analysis_result_v2",
]
