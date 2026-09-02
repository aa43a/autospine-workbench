"""Strict in-memory input for one approved P10.3c v2 visual head."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from .body_sway_review_admission_input_checks_v2 import (
    BodySwayReviewAdmissionInputV2CheckError,
    require_body_sway_review_admission_input_v2_content,
)
from .body_sway_runtime_execution_reader import (
    VerifiedBodySwayRuntimeExecution,
)
from .body_sway_visual_review_address_v2 import ExactVisualReviewAddressV2
from .body_sway_visual_review_application_models_v2 import (
    ExactBodySwayVisualReviewDecisionV2, PreparedBodySwayVisualReviewV2,
)
from .body_sway_visual_review_candidate_source_v2 import (
    BodySwayVisualReviewCandidateSourceV2Error,
    require_verified_visual_review_execution_v2,
)
from .body_sway_visual_review_history_snapshot_v2 import (
    BodySwayVisualReviewHistorySnapshotV2,
)
from .p10_visual_review_v2_context import P10VisualReviewV2Context
from .p10_completed_job_snapshot import (
    P10CompletedJobSnapshotError, VerifiedCompletedP10CaptureJob,
    require_verified_completed_p10_capture_job,
)
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2
from .temporary_body_sway_preview_validation_v2 import (
    TemporaryBodySwayPreviewValidationV2Error,
    require_temporary_body_sway_preview_v2,
)


class BodySwayReviewAdmissionInputV2Error(ValueError):
    """Raised when job, execution, preview, and current v2 head diverge."""


@dataclass(frozen=True, slots=True)
class BodySwayReviewAdmissionInputV2:
    job_id: str
    package_id: str
    job_terminal_event_sha256: str
    job_terminal_sequence: int
    address: ExactVisualReviewAddressV2
    visual_candidate_sha256: str
    visual_revision: int
    visual_decision_sha256: str
    history_before: BodySwayVisualReviewHistorySnapshotV2
    history_after: BodySwayVisualReviewHistorySnapshotV2
    _completed_job: VerifiedCompletedP10CaptureJob = field(repr=False)
    _execution: VerifiedBodySwayRuntimeExecution = field(repr=False)
    _preview_json: str = field(repr=False)
    _preview_artifact_items: tuple[tuple[str, bytes], ...] = field(repr=False)
    _candidate_json: str = field(repr=False)
    _decision_json: str = field(repr=False)

    @property
    def preview_document(self) -> dict[str, Any]:
        return json.loads(self._preview_json)

    @property
    def candidate_document(self) -> dict[str, Any]:
        return json.loads(self._candidate_json)

    @property
    def decision_document(self) -> dict[str, Any]:
        return json.loads(self._decision_json)

    @property
    def project_id(self) -> str:
        return self.preview_document["project_id"]

    @property
    def clip_id(self) -> str:
        return self.preview_document["clip_id"]

    @property
    def timing(self) -> dict[str, Any]:
        return dict(self.preview_document["timing"])

    @property
    def selection(self) -> dict[str, Any]:
        return _copy(self.preview_document["selection"])

    @property
    def evidence(self) -> dict[str, Any]:
        return _copy(self.candidate_document["source"])


def build_body_sway_review_admission_input_v2(
    context_before: P10VisualReviewV2Context,
    before: PreparedBodySwayVisualReviewV2,
    decision: ExactBodySwayVisualReviewDecisionV2,
    context_after: P10VisualReviewV2Context,
    after: PreparedBodySwayVisualReviewV2,
    *, candidate_sha256: str, revision: int, decision_sha256: str,
) -> BodySwayReviewAdmissionInputV2:
    """Detach two independently resolved source/head observations."""

    try:
        if type(context_before) is not P10VisualReviewV2Context \
                or type(context_after) is not P10VisualReviewV2Context \
                or type(before) is not PreparedBodySwayVisualReviewV2 \
                or type(after) is not PreparedBodySwayVisualReviewV2 \
                or type(decision) is not ExactBodySwayVisualReviewDecisionV2:
            raise BodySwayReviewAdmissionInputV2Error(
                "Review admission v2 requires exact application value objects"
            )
        _require_matching_contexts(context_before, context_after)
        mount = context_before.preview
        preview = mount.preview
        execution = mount.execution
        value = BodySwayReviewAdmissionInputV2(
            job_id=context_before.job_id,
            package_id=context_before.package_id,
            job_terminal_event_sha256=
                context_before.job_head_event_sha256 or "",
            job_terminal_sequence=context_before.job_event_count,
            address=context_before.address,
            visual_candidate_sha256=candidate_sha256,
            visual_revision=revision,
            visual_decision_sha256=decision_sha256,
            history_before=before.history,
            history_after=after.history,
            _completed_job=context_before._completed_job,
            _execution=execution,
            _preview_json=_canonical(preview.document),
            _preview_artifact_items=tuple(sorted(preview.artifact_bytes.items())),
            _candidate_json=_canonical(before.candidate_document),
            _decision_json=_canonical(decision.decision_document),
        )
        if before.address != value.address or after.address != value.address \
                or decision.address != value.address \
                or before.candidate_sha256 != candidate_sha256 \
                or after.candidate_sha256 != candidate_sha256 \
                or decision.candidate_sha256 != candidate_sha256 \
                or decision.revision != revision \
                or decision.decision_sha256 != decision_sha256 \
                or before.candidate_document != after.candidate_document:
            raise BodySwayReviewAdmissionInputV2Error(
                "Review application v2 snapshots differ from their addresses"
            )
        return require_body_sway_review_admission_input_v2(value)
    except BodySwayReviewAdmissionInputV2Error:
        raise
    except _FAILURES as exc:
        raise BodySwayReviewAdmissionInputV2Error(
            f"Body-sway review admission v2 input build failed: {exc}"
        ) from exc


def require_body_sway_review_admission_input_v2(
    value: BodySwayReviewAdmissionInputV2,
) -> BodySwayReviewAdmissionInputV2:
    try:
        if type(value) is not BodySwayReviewAdmissionInputV2 \
                or type(value.address) is not ExactVisualReviewAddressV2:
            raise BodySwayReviewAdmissionInputV2Error(
                "Review admission v2 input has the wrong representation"
            )
        preview = TemporaryBodySwayPreviewV2(
            value._preview_json, value._preview_artifact_items,
        )
        require_temporary_body_sway_preview_v2(
            preview.document, preview.artifact_bytes,
        )
        require_verified_visual_review_execution_v2(value._execution)
        require_body_sway_review_admission_input_v2_content(value, preview)
        return value
    except BodySwayReviewAdmissionInputV2Error:
        raise
    except _FAILURES as exc:
        raise BodySwayReviewAdmissionInputV2Error(
            f"Body-sway review admission v2 input failed: {exc}"
        ) from exc


def _require_matching_contexts(before, after) -> None:
    left, right = before.preview, after.preview
    before_job = _require_context_job(before)
    after_job = _require_context_job(after)
    if before_job != after_job \
            or before.job_id != after.job_id \
            or before.package_id != after.package_id \
            or before.job_head_event_sha256 is None \
            or before.job_head_event_sha256 != after.job_head_event_sha256 \
            or before.job_event_count < 1 \
            or before.job_event_count != after.job_event_count \
            or before.address != after.address \
            or left.preview.canonical_bytes != right.preview.canonical_bytes \
            or left.preview.artifact_bytes != right.preview.artifact_bytes \
            or left.execution.execution.canonical_bytes \
                != right.execution.execution.canonical_bytes \
            or left.execution.execution.capture.canonical_bytes \
                != right.execution.execution.capture.canonical_bytes \
            or left.execution.execution.capture.capture_bytes \
                != right.execution.execution.capture.capture_bytes:
        raise BodySwayReviewAdmissionInputV2Error(
            "Completed job source changed during v2 admission observation"
        )


def _require_context_job(context) -> VerifiedCompletedP10CaptureJob:
    try:
        job = require_verified_completed_p10_capture_job(
            context._completed_job,
        )
        if context.job_id != job.job_id \
                or context.package_id != job.package_id \
                or context.job_head_event_sha256 \
                    != job.terminal_event_sha256 \
                or context.job_event_count != job.terminal_sequence \
                or context.address != job.address:
            raise BodySwayReviewAdmissionInputV2Error(
                "Completed job context differs from its event-chain proof"
            )
        return job
    except P10CompletedJobSnapshotError as exc:
        raise BodySwayReviewAdmissionInputV2Error(
            "Completed job context proof is invalid"
        ) from exc


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


_FAILURES = (
    AttributeError, BodySwayReviewAdmissionInputV2CheckError,
    BodySwayVisualReviewCandidateSourceV2Error, KeyError, OverflowError,
    P10CompletedJobSnapshotError,
    RecursionError, RuntimeError, TemporaryBodySwayPreviewValidationV2Error,
    TypeError, UnicodeError, ValueError,
)


__all__ = [
    "BodySwayReviewAdmissionInputV2",
    "BodySwayReviewAdmissionInputV2Error",
    "build_body_sway_review_admission_input_v2",
    "require_body_sway_review_admission_input_v2",
]
