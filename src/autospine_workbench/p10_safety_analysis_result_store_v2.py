"""Canonical artifact storage for staged and completed P10.4b v2 results."""

from __future__ import annotations

from .body_sway_amplitude_envelope_profile_v2 import (
    MAX_DOCUMENT_BYTES as AMPLITUDE_MAX_BYTES,
)
from .body_sway_continuous_proof_profile_v2 import (
    MAX_DOCUMENT_BYTES as CONTINUOUS_MAX_BYTES,
)
from .p10_safety_analysis_job_files_v2 import (
    normalized_state_root, publish_once, read_json, run_directory,
)
from .p10_safety_analysis_job_validation_v2 import require_result_address
from .p10_safety_analysis_result_validation_v2 import (
    P10SafetyAnalysisResultValidationV2Error,
    require_p10_safety_analysis_result_documents_v2,
)
from .resolved_project import canonical_sha256


class P10SafetyAnalysisResultStoreV2Error(RuntimeError):
    """Raised when staged result bytes are unsafe or cross-wired."""


class P10SafetyAnalysisResultStoreV2:
    def __init__(self, state_root) -> None:
        self.state_root = normalized_state_root(state_root)

    def publish(
        self, run_id, amplitude, continuous, *, admission_sha256,
        visual_candidate_sha256, visual_revision, visual_decision_sha256,
    ):
        try:
            directory = run_directory(
                self.state_root, run_id, create=False,
            )
            amplitude_raw = amplitude.canonical_bytes
            continuous_raw = continuous.canonical_bytes
            if amplitude_raw != _canonical_bytes(amplitude.document) \
                    or continuous_raw \
                        != _canonical_bytes(continuous.document) \
                    or amplitude.sha256 \
                        != canonical_sha256(amplitude.document) \
                    or continuous.sha256 \
                        != canonical_sha256(continuous.document):
                raise P10SafetyAnalysisResultStoreV2Error(
                    "Safety analysis result artifact identity differs"
                )
            publish_once(
                directory / "amplitude.json", amplitude_raw,
                AMPLITUDE_MAX_BYTES,
            )
            publish_once(
                directory / "continuous.json", continuous_raw,
                CONTINUOUS_MAX_BYTES,
            )
            return require_result_address({
                "authority_scope": "compile_time_snapshot",
                "admission_sha256": admission_sha256,
                "visual_candidate_sha256": visual_candidate_sha256,
                "visual_revision": visual_revision,
                "visual_decision_sha256": visual_decision_sha256,
                "amplitude_sha256": amplitude.sha256,
                "continuous_sha256": continuous.sha256,
                "amplitude_size_bytes": len(amplitude_raw),
                "continuous_size_bytes": len(continuous_raw),
            })
        except P10SafetyAnalysisResultStoreV2Error:
            raise
        except Exception as exc:
            raise P10SafetyAnalysisResultStoreV2Error(
                "Safety analysis result cannot be published"
            ) from exc

    def read_and_validate(self, run_id, request, result):
        try:
            sealed = require_result_address(result)
            directory = run_directory(
                self.state_root, run_id, create=False,
            )
            amplitude = read_json(
                directory / "amplitude.json", AMPLITUDE_MAX_BYTES,
            )
            continuous = read_json(
                directory / "continuous.json", CONTINUOUS_MAX_BYTES,
            )
            if len(_canonical_bytes(amplitude)) \
                    != sealed["amplitude_size_bytes"] \
                    or len(_canonical_bytes(continuous)) \
                    != sealed["continuous_size_bytes"] \
                    or canonical_sha256(amplitude) \
                    != sealed["amplitude_sha256"] \
                    or canonical_sha256(continuous) \
                    != sealed["continuous_sha256"]:
                raise P10SafetyAnalysisResultStoreV2Error(
                    "Safety analysis result digest differs"
                )
            require_p10_safety_analysis_result_documents_v2(
                request, sealed, amplitude, continuous,
            )
            return amplitude, continuous
        except P10SafetyAnalysisResultStoreV2Error:
            raise
        except P10SafetyAnalysisResultValidationV2Error as exc:
            raise P10SafetyAnalysisResultStoreV2Error(
                "Safety analysis result binding differs"
            ) from exc
        except Exception as exc:
            raise P10SafetyAnalysisResultStoreV2Error(
                "Safety analysis result cannot be read"
            ) from exc


def _canonical_bytes(value):
    import json

    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


__all__ = [
    "P10SafetyAnalysisResultStoreV2",
    "P10SafetyAnalysisResultStoreV2Error",
]
