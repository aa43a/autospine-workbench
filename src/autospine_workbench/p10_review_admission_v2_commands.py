"""Job-centric, read-only P10.4a v2 admission orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .body_sway_review_admission_inputs_v2 import (
    BodySwayReviewAdmissionInputV2,
    BodySwayReviewAdmissionInputV2Error,
    build_body_sway_review_admission_input_v2,
)
from .body_sway_review_admission_v2 import (
    BodySwayReviewAdmissionV2, BodySwayReviewAdmissionV2Error,
    compile_body_sway_review_admission_v2,
)
from .body_sway_visual_review_application_v2 import (
    BodySwayVisualReviewApplicationV2,
    BodySwayVisualReviewApplicationV2Error,
)
from .manifest_artifacts import LayerManifestError, require_sha256
from .p10_visual_review_v2_context import (
    P10VisualReviewV2ContextError,
    resolve_p10_visual_review_v2_context,
)
from .project_store import ProjectStore


class P10ReviewAdmissionV2CommandError(RuntimeError):
    """Raised when the completed job's current approved head is inadmissible."""


@dataclass(frozen=True, slots=True)
class P10ReviewAdmissionV2CommandResult:
    job_id: str
    package_id: str
    terminal_event_sha256: str
    terminal_sequence: int
    project_id: str
    clip_id: str
    temporary_preview_v2_sha256: str
    runtime_execution_sha256: str
    runtime_execution_bundle_sha256: str
    capture_artifact_set_sha256: str
    visual_candidate_sha256: str
    visual_revision: int
    visual_decision_sha256: str
    admission_sha256: str
    _admission: BodySwayReviewAdmissionV2 = field(repr=False)
    _inputs: BodySwayReviewAdmissionInputV2 = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return self._admission.document


def compile_body_sway_review_admission_v2_for_job(
    job_reader: Any,
    store: ProjectStore,
    job_id: str,
    *,
    expected_candidate_sha256: str | None = None,
    expected_visual_revision: int | None = None,
    expected_decision_sha256: str | None = None,
) -> P10ReviewAdmissionV2CommandResult:
    """Resolve current source twice and auto-admit its explicit approved head."""

    try:
        if type(store) is not ProjectStore or not callable(
            getattr(job_reader, "get", None)
        ):
            raise P10ReviewAdmissionV2CommandError(
                "Review admission v2 requires read-only job and project stores"
            )
        expected_job = require_sha256(job_id, "Runtime capture job")
        pins = _expected_pins(
            expected_candidate_sha256, expected_visual_revision,
            expected_decision_sha256,
        )
        context_before = resolve_p10_visual_review_v2_context(
            job_reader, store, expected_job, allow_acceleration=False,
        )
        application = BodySwayVisualReviewApplicationV2(store.state_root)
        before = application.prepare(
            context_before.address, context_before.preview,
        )
        candidate_sha, revision, decision_sha = _current_head(before)
        if pins is not None and pins != (
            candidate_sha, revision, decision_sha,
        ):
            raise P10ReviewAdmissionV2CommandError(
                "Pinned visual review v2 head is no longer current"
            )
        exact = application.exact_decision(
            context_before.address, context_before.preview,
            candidate_sha256=candidate_sha, revision=revision,
            decision_sha256=decision_sha,
        )
        context_after = resolve_p10_visual_review_v2_context(
            job_reader, store, expected_job, allow_acceleration=False,
        )
        after = application.prepare(
            context_after.address, context_after.preview,
        )
        inputs = build_body_sway_review_admission_input_v2(
            context_before, before, exact, context_after, after,
            candidate_sha256=candidate_sha, revision=revision,
            decision_sha256=decision_sha,
        )
        admission = compile_body_sway_review_admission_v2(inputs)
        return _result(inputs, admission)
    except P10ReviewAdmissionV2CommandError:
        raise
    except _FAILURES as exc:
        raise P10ReviewAdmissionV2CommandError(
            "Body-sway review admission v2 command failed"
        ) from exc


def _expected_pins(candidate, revision, decision):
    supplied = (candidate is not None, revision is not None, decision is not None)
    if any(supplied) and not all(supplied):
        raise P10ReviewAdmissionV2CommandError(
            "Expected visual head pins must be supplied together"
        )
    if not any(supplied):
        return None
    if type(revision) is not int or not 1 <= revision <= 64:
        raise P10ReviewAdmissionV2CommandError(
            "Expected visual revision v2 is invalid"
        )
    return (
        require_sha256(candidate, "Expected visual candidate v2"),
        revision,
        require_sha256(decision, "Expected visual decision v2"),
    )


def _current_head(prepared):
    history = prepared.history
    if history.current_revision < 1 or not history.rows \
            or history.revision_count != len(history.rows) \
            or history.current_revision != history.revision_count \
            or history.head_decision_sha256 is None:
        raise P10ReviewAdmissionV2CommandError(
            "Completed job has no current visual review v2 decision"
        )
    return (
        prepared.candidate_sha256,
        history.current_revision,
        history.head_decision_sha256,
    )


def _result(inputs, admission):
    address = inputs.address
    return P10ReviewAdmissionV2CommandResult(
        job_id=inputs.job_id, package_id=inputs.package_id,
        terminal_event_sha256=inputs.job_terminal_event_sha256,
        terminal_sequence=inputs.job_terminal_sequence,
        project_id=inputs.project_id, clip_id=inputs.clip_id,
        temporary_preview_v2_sha256=address.temporary_preview_v2_sha256,
        runtime_execution_sha256=inputs._execution.execution.sha256,
        runtime_execution_bundle_sha256=
            address.runtime_execution_bundle_sha256,
        capture_artifact_set_sha256=address.capture_artifact_set_sha256,
        visual_candidate_sha256=inputs.visual_candidate_sha256,
        visual_revision=inputs.visual_revision,
        visual_decision_sha256=inputs.visual_decision_sha256,
        admission_sha256=admission.sha256,
        _admission=admission, _inputs=inputs,
    )


_FAILURES = (
    AttributeError, BodySwayReviewAdmissionInputV2Error,
    BodySwayReviewAdmissionV2Error,
    BodySwayVisualReviewApplicationV2Error, KeyError, LayerManifestError,
    OSError, OverflowError, P10VisualReviewV2ContextError, RecursionError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "P10ReviewAdmissionV2CommandError", "P10ReviewAdmissionV2CommandResult",
    "compile_body_sway_review_admission_v2_for_job",
]
