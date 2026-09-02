"""Parent-owned completion checks for an isolated P10.4b v2 worker."""

from __future__ import annotations

from .body_sway_review_admission_consumer_v2 import (
    BodySwayReviewAdmissionV2ConsumerError,
    require_current_body_sway_review_admission_v2,
)
from .p10_safety_analysis_manager_error_v2 import (
    P10SafetyAnalysisManagerV2Error,
)
from .p10_safety_analysis_job_store_v2 import (
    P10SafetyAnalysisJobStoreV2Error,
)
from .p10_safety_analysis_v2_commands import (
    P10SafetyAnalysisV2CommandError,
)


def verify_parent_p10_safety_analysis_result_v2(
    job_reader, projects, result_store, run_id, worker_result,
):
    """Read staged bytes again and close their current authority in parent."""

    try:
        amplitude, continuous = result_store.verify_staged_result(
            run_id, worker_result.result,
        )
    except P10SafetyAnalysisJobStoreV2Error as exc:
        raise P10SafetyAnalysisV2CommandError(
            "P10.4b v2 staged result failed parent validation",
            failure_code="analysis_validation_failed", terminal=True,
        ) from exc
    if amplitude != worker_result.amplitude_document \
            or continuous != worker_result.continuous_document:
        raise P10SafetyAnalysisManagerV2Error(
            "Safety analysis worker readback differs"
        )
    admission = amplitude["source"]["review_admission_v2"]
    try:
        current = require_current_body_sway_review_admission_v2(
            job_reader, projects, admission,
        )
    except BodySwayReviewAdmissionV2ConsumerError as exc:
        raise P10SafetyAnalysisV2CommandError(
            "P10.4b v2 source changed before parent completion",
            failure_code="source_changed", terminal=True,
        ) from exc
    except OSError as exc:
        raise P10SafetyAnalysisV2CommandError(
            "P10.4b v2 source could not be rechecked by parent",
            failure_code="source_unavailable", terminal=False,
        ) from exc
    if current.admission_sha256 != worker_result.result["admission_sha256"] \
            or current.document != admission:
        raise P10SafetyAnalysisV2CommandError(
            "P10.4b v2 source changed before parent completion",
            failure_code="source_changed", terminal=True,
        )
    return amplitude, continuous


__all__ = ["verify_parent_p10_safety_analysis_result_v2"]
