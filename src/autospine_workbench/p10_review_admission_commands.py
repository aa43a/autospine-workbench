"""Read-only exact application command for P10.4a review admission."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .body_sway_review_admission import (
    BodySwayReviewAdmission,
    BodySwayReviewAdmissionError,
    compile_body_sway_review_admission,
)
from .body_sway_review_admission_inputs import (
    BodySwayReviewAdmissionInputError,
    build_body_sway_review_admission_input,
)
from .body_sway_runtime_capture_reader import (
    VerifiedBodySwayRuntimeCaptureReader,
    VerifiedBodySwayRuntimeCaptureReaderError,
)
from .body_sway_visual_review_address import (
    ExactVisualReviewAddress,
    ExactVisualReviewAddressError,
)
from .body_sway_visual_review_application import (
    BodySwayVisualReviewApplication,
    BodySwayVisualReviewApplicationError,
)
from .p10_preview_commands import (
    P10PreviewCommandError,
    compile_body_sway_preview_command,
    require_exact_preview_for_mount,
)


class P10ReviewAdmissionCommandError(RuntimeError):
    """Raised when exact persisted evidence cannot admit its current head."""


@dataclass(frozen=True, slots=True)
class P10ReviewAdmissionCommandResult:
    """Path-free admission identity plus private exact input locations."""

    input_paths: tuple[Path, ...] = field(repr=False)
    idle_behavior_candidates_sha256: str
    idle_behavior_decision_sha256: str
    body_sway_probe_report_sha256: str
    temporary_preview_sha256: str
    preview_artifact_set_sha256: str
    runtime_capture_manifest_sha256: str
    runtime_capture_bundle_sha256: str
    capture_artifact_set_sha256: str
    visual_candidate_sha256: str
    visual_revision: int
    visual_decision_sha256: str
    admission_sha256: str
    _admission: BodySwayReviewAdmission = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return self._admission.document


def compile_body_sway_review_admission_command(
    state_root: Path,
    project_id: str,
    candidates_path: Path,
    decision_path: Path,
    probe_report_path: Path,
    *,
    layer_manifest_sha256: str,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
    motion_instance_sha256: str,
    motion_retarget_bundle_sha256: str,
    motion_instance_v2_sha256: str,
    reviewed_motion_bundle_sha256: str,
    temporary_preview_sha256: str,
    runtime_capture_bundle_sha256: str,
    capture_artifact_set_sha256: str,
    visual_candidate_sha256: str,
    visual_revision: int,
    visual_decision_sha256: str,
) -> P10ReviewAdmissionCommandResult:
    """Replay P10 and observe one exact approved head twice without writes."""

    try:
        address = ExactVisualReviewAddress(
            project_id,
            temporary_preview_sha256,
            runtime_capture_bundle_sha256,
            capture_artifact_set_sha256,
        )
        preview_result = compile_body_sway_preview_command(
            state_root, project_id,
            candidates_path, decision_path, probe_report_path,
            layer_manifest_sha256=layer_manifest_sha256,
            p3_rig_sha256=p3_rig_sha256,
            p3_bundle_sha256=p3_bundle_sha256,
            motion_instance_sha256=motion_instance_sha256,
            motion_retarget_bundle_sha256=motion_retarget_bundle_sha256,
            motion_instance_v2_sha256=motion_instance_v2_sha256,
            reviewed_motion_bundle_sha256=reviewed_motion_bundle_sha256,
        )
        if preview_result.temporary_preview_sha256 \
                != address.temporary_preview_sha256:
            raise P10ReviewAdmissionCommandError(
                "Runtime capture does not address the exact P10 preview"
            )
        preview = require_exact_preview_for_mount(preview_result)
        capture = VerifiedBodySwayRuntimeCaptureReader(state_root).load(
            *address.reader_arguments
        )
        application = BodySwayVisualReviewApplication(state_root)
        history_before = application.prepare(address)
        exact_decision = application.exact_decision(
            address,
            candidate_sha256=visual_candidate_sha256,
            revision=visual_revision,
            decision_sha256=visual_decision_sha256,
        )
        history_after = application.prepare(address)
        admitted_inputs = build_body_sway_review_admission_input(
            preview, capture, history_before, exact_decision, history_after,
            address=address,
            candidate_sha256=visual_candidate_sha256,
            revision=visual_revision,
            decision_sha256=visual_decision_sha256,
        )
        admission = compile_body_sway_review_admission(admitted_inputs)
        return _result(preview_result, capture, admitted_inputs, admission)
    except P10ReviewAdmissionCommandError:
        raise
    except _FAILURES as exc:
        raise P10ReviewAdmissionCommandError(
            "Body-sway review admission command failed"
        ) from exc


def _result(preview, capture, admitted, admission):
    return P10ReviewAdmissionCommandResult(
        input_paths=(*preview.input_paths, capture.path),
        idle_behavior_candidates_sha256=
            preview.idle_behavior_candidates_sha256,
        idle_behavior_decision_sha256=
            preview.idle_behavior_decision_sha256,
        body_sway_probe_report_sha256=preview.body_sway_probe_report_sha256,
        temporary_preview_sha256=preview.temporary_preview_sha256,
        preview_artifact_set_sha256=preview.artifact_set_sha256,
        runtime_capture_manifest_sha256=
            admitted.runtime_capture_manifest_sha256,
        runtime_capture_bundle_sha256=capture.bundle_sha256,
        capture_artifact_set_sha256=capture.artifact_set_sha256,
        visual_candidate_sha256=admitted.visual_candidate_sha256,
        visual_revision=admitted.visual_revision,
        visual_decision_sha256=admitted.visual_decision_sha256,
        admission_sha256=admission.sha256,
        _admission=admission,
    )


_FAILURES = (
    AttributeError, BodySwayReviewAdmissionError,
    BodySwayReviewAdmissionInputError,
    BodySwayVisualReviewApplicationError, ExactVisualReviewAddressError,
    KeyError, OSError, OverflowError, P10PreviewCommandError,
    RecursionError, RuntimeError, TypeError, UnicodeError, ValueError,
    VerifiedBodySwayRuntimeCaptureReaderError,
)
