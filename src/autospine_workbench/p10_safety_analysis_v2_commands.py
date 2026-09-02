"""Job-only orchestration for P10.4b v2 amplitude and continuous proof."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .body_sway_amplitude_envelope_v2 import (
    BodySwayAmplitudeEnvelopeCandidateV2,
    BodySwayAmplitudeEnvelopeV2Error,
    compile_body_sway_amplitude_envelope_candidate_v2,
)
from .body_sway_continuous_proof_v2 import (
    BodySwayContinuousPreviewProofV2, BodySwayContinuousProofV2Error,
    compile_body_sway_continuous_preview_proof_v2,
)
from .body_sway_review_admission_consumer_v2 import (
    BodySwayReviewAdmissionV2ConsumerError,
    CurrentBodySwayReviewAdmissionV2,
    require_current_body_sway_review_admission_v2,
)
from .p10_review_admission_v2_commands import (
    P10ReviewAdmissionV2CommandError,
    compile_body_sway_review_admission_v2_for_job,
)
from .p10_safety_analysis_source_v2 import (
    P10SafetyAnalysisSourceV2Error,
    replay_current_p10_safety_analysis_source_v2,
)
from .project_store import ProjectStore


Progress = Callable[[str, int, int], None]


class P10SafetyAnalysisV2CommandError(RuntimeError):
    """Raised when current v2 authority changes or analysis cannot close."""

    def __init__(
        self, message: str, *, failure_code: str = "analysis_validation_failed",
        terminal: bool = True,
    ) -> None:
        super().__init__(message)
        self.failure_code = failure_code
        self.terminal = terminal


@dataclass(frozen=True, slots=True)
class P10SafetyAnalysisV2CommandResult:
    job_id: str
    package_id: str
    project_id: str
    clip_id: str
    admission_sha256: str
    amplitude_sha256: str
    continuous_sha256: str
    status: str
    _admission: CurrentBodySwayReviewAdmissionV2 = field(repr=False)
    _amplitude: BodySwayAmplitudeEnvelopeCandidateV2 = field(repr=False)
    _continuous: BodySwayContinuousPreviewProofV2 = field(repr=False)

    @property
    def amplitude_document(self) -> dict[str, Any]:
        return self._amplitude.document

    @property
    def continuous_document(self) -> dict[str, Any]:
        return self._continuous.document


def compile_p10_safety_analysis_v2_for_job(
    job_reader: Any,
    store: ProjectStore,
    job_id: str,
    *,
    on_progress: Progress | None = None,
) -> P10SafetyAnalysisV2CommandResult:
    """Compile both v2 contracts between two exact current-head checks."""

    try:
        if type(store) is not ProjectStore \
                or not callable(getattr(job_reader, "get", None)) \
                or on_progress is not None and not callable(on_progress):
            raise P10SafetyAnalysisV2CommandError(
                "P10.4b v2 requires read-only job and project stores",
                failure_code="invalid_request",
            )
        _progress(on_progress, "review_admission", 0, 1)
        initial = compile_body_sway_review_admission_v2_for_job(
            job_reader, store, job_id,
        )
        current = CurrentBodySwayReviewAdmissionV2(
            initial.admission_sha256, initial,
        )
        _progress(on_progress, "review_admission", 1, 1)
        _progress(on_progress, "exact_source", 0, 1)
        source = replay_current_p10_safety_analysis_source_v2(
            store, initial.package_id,
        )
        _progress(on_progress, "exact_source", 1, 1)
        _progress(on_progress, "amplitude_probes", 0, 9)
        amplitude = compile_body_sway_amplitude_envelope_candidate_v2(
            current, source,
        )
        _progress(on_progress, "amplitude_probes", 9, 9)
        continuous = compile_body_sway_continuous_preview_proof_v2(
            amplitude, source, on_progress=on_progress,
        )
        _progress(on_progress, "current_head_recheck", 0, 1)
        final = require_current_body_sway_review_admission_v2(
            job_reader, store, initial.document,
        )
        if final.admission_sha256 != current.admission_sha256 \
                or final.document != current.document:
            raise P10SafetyAnalysisV2CommandError(
                "P10.4b v2 admission changed during analysis",
                failure_code="source_changed",
            )
        _progress(on_progress, "current_head_recheck", 1, 1)
        return P10SafetyAnalysisV2CommandResult(
            job_id=initial.job_id, package_id=initial.package_id,
            project_id=initial.project_id, clip_id=initial.clip_id,
            admission_sha256=current.admission_sha256,
            amplitude_sha256=amplitude.sha256,
            continuous_sha256=continuous.sha256,
            status=continuous.document["status"],
            _admission=current, _amplitude=amplitude,
            _continuous=continuous,
        )
    except P10SafetyAnalysisV2CommandError:
        raise
    except _FAILURES as exc:
        failure_code, terminal = _classify_failure(exc)
        raise P10SafetyAnalysisV2CommandError(
            "P10.4b v2 safety analysis failed closed",
            failure_code=failure_code, terminal=terminal,
        ) from exc


def _progress(callback, stage, current, total):
    if callback is not None:
        callback(stage, current, total)


def _classify_failure(exc):
    if isinstance(exc, OSError):
        return "source_unavailable", False
    if isinstance(exc, (
        BodySwayReviewAdmissionV2ConsumerError,
        P10ReviewAdmissionV2CommandError,
        P10SafetyAnalysisSourceV2Error,
    )):
        return "source_changed", True
    if isinstance(exc, (
        BodySwayAmplitudeEnvelopeV2Error,
        BodySwayContinuousProofV2Error,
    )):
        return "analysis_validation_failed", True
    return "analysis_failed", False


_FAILURES = (
    BodySwayAmplitudeEnvelopeV2Error,
    BodySwayContinuousProofV2Error,
    BodySwayReviewAdmissionV2ConsumerError,
    KeyError, OSError, OverflowError,
    P10ReviewAdmissionV2CommandError, P10SafetyAnalysisSourceV2Error,
    RecursionError, RuntimeError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "P10SafetyAnalysisV2CommandError",
    "P10SafetyAnalysisV2CommandResult",
    "compile_p10_safety_analysis_v2_for_job",
]
