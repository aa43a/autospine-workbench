"""Read-only exact application command for P10.4b1 gain candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .body_sway_amplitude_envelope import (
    BodySwayAmplitudeEnvelopeCandidate,
    BodySwayAmplitudeEnvelopeError,
    compile_body_sway_amplitude_envelope_candidate,
)
from .body_sway_amplitude_envelope_inputs import (
    BodySwayAmplitudeEnvelopeInputError,
    require_body_sway_amplitude_envelope_inputs,
)
from .body_sway_visual_review_address import ExactVisualReviewAddress
from .body_sway_visual_review_application import (
    BodySwayVisualReviewApplication,
    BodySwayVisualReviewApplicationError,
)
from .p10_review_admission_commands import (
    P10ReviewAdmissionCommandError,
    compile_body_sway_review_admission_command,
)


class P10AmplitudeEnvelopeCommandError(RuntimeError):
    """Raised when exact approved evidence cannot yield current candidates."""


@dataclass(frozen=True, slots=True)
class P10AmplitudeEnvelopeCommandResult:
    """Path-free public identities plus private exact input locations."""

    input_paths: tuple[Path, ...] = field(repr=False)
    project_id: str
    clip_id: str
    review_admission_sha256: str
    preview_projection_sha256: str
    visual_candidate_sha256: str
    visual_revision: int
    visual_decision_sha256: str
    amplitude_envelope_sha256: str
    _candidate: BodySwayAmplitudeEnvelopeCandidate = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return self._candidate.document


def compile_body_sway_amplitude_envelope_command(
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
) -> P10AmplitudeEnvelopeCommandResult:
    """Replay approval, analyze fixed gains, then reject a changed head."""

    try:
        admitted = compile_body_sway_review_admission_command(
            state_root, project_id,
            candidates_path, decision_path, probe_report_path,
            layer_manifest_sha256=layer_manifest_sha256,
            p3_rig_sha256=p3_rig_sha256,
            p3_bundle_sha256=p3_bundle_sha256,
            motion_instance_sha256=motion_instance_sha256,
            motion_retarget_bundle_sha256=motion_retarget_bundle_sha256,
            motion_instance_v2_sha256=motion_instance_v2_sha256,
            reviewed_motion_bundle_sha256=reviewed_motion_bundle_sha256,
            temporary_preview_sha256=temporary_preview_sha256,
            runtime_capture_bundle_sha256=runtime_capture_bundle_sha256,
            capture_artifact_set_sha256=capture_artifact_set_sha256,
            visual_candidate_sha256=visual_candidate_sha256,
            visual_revision=visual_revision,
            visual_decision_sha256=visual_decision_sha256,
        )
        preview = admitted._preview_result
        inputs = require_body_sway_amplitude_envelope_inputs(
            admitted._admission, preview._inputs, preview._preview
        )
        candidate = compile_body_sway_amplitude_envelope_candidate(inputs)
        _require_unchanged_head(
            state_root, project_id,
            temporary_preview_sha256, runtime_capture_bundle_sha256,
            capture_artifact_set_sha256, visual_candidate_sha256,
            visual_revision, visual_decision_sha256,
        )
        return P10AmplitudeEnvelopeCommandResult(
            input_paths=admitted.input_paths,
            project_id=candidate.document["project_id"],
            clip_id=candidate.document["clip_id"],
            review_admission_sha256=admitted.admission_sha256,
            preview_projection_sha256=inputs.projection.sha256,
            visual_candidate_sha256=admitted.visual_candidate_sha256,
            visual_revision=admitted.visual_revision,
            visual_decision_sha256=admitted.visual_decision_sha256,
            amplitude_envelope_sha256=candidate.sha256,
            _candidate=candidate,
        )
    except P10AmplitudeEnvelopeCommandError:
        raise
    except _FAILURES as exc:
        raise P10AmplitudeEnvelopeCommandError(
            "Body-sway amplitude envelope command failed"
        ) from exc


def _require_unchanged_head(
    state_root, project_id, preview_sha, capture_bundle_sha,
    capture_artifact_sha, candidate_sha, revision, decision_sha,
) -> None:
    address = ExactVisualReviewAddress(
        project_id, preview_sha, capture_bundle_sha, capture_artifact_sha
    )
    application = BodySwayVisualReviewApplication(state_root)
    before = application.prepare(address)
    exact = application.exact_decision(
        address, candidate_sha256=candidate_sha,
        revision=revision, decision_sha256=decision_sha,
    )
    after = application.prepare(address)
    if not _is_exact_head(before, candidate_sha, revision, decision_sha) \
            or not _is_exact_head(after, candidate_sha, revision, decision_sha) \
            or exact.candidate_sha256 != candidate_sha \
            or exact.revision != revision \
            or exact.decision_sha256 != decision_sha:
        raise P10AmplitudeEnvelopeCommandError(
            "Visual-review head changed during amplitude analysis"
        )


def _is_exact_head(prepared, candidate_sha, revision, decision_sha):
    history = prepared.history
    return prepared.candidate_sha256 == candidate_sha \
        and history.current_revision == revision \
        and history.head_decision_sha256 == decision_sha


_FAILURES = (
    AttributeError, BodySwayAmplitudeEnvelopeError,
    BodySwayAmplitudeEnvelopeInputError,
    BodySwayVisualReviewApplicationError, KeyError, OSError, OverflowError,
    P10ReviewAdmissionCommandError, RecursionError, RuntimeError, TypeError,
    UnicodeError, ValueError,
)
