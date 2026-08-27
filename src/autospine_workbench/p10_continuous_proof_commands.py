"""Read-only exact application command for P10.4b2 continuous proof."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .body_sway_continuous_proof import (
    BodySwayContinuousPreviewProof,
    BodySwayContinuousProofError,
    compile_body_sway_continuous_preview_proof,
)
from .body_sway_continuous_proof_inputs import (
    BodySwayContinuousProofInputError,
    require_body_sway_continuous_proof_inputs,
)
from .p10_amplitude_envelope_commands import (
    P10AmplitudeEnvelopeCommandError,
    compile_body_sway_amplitude_envelope_command,
    require_unchanged_visual_review_head,
)
from .body_sway_visual_review_application import (
    BodySwayVisualReviewApplicationError,
)


class P10ContinuousProofCommandError(RuntimeError):
    """Raised when exact current evidence cannot yield a continuous proof."""


@dataclass(frozen=True, slots=True)
class P10ContinuousProofCommandResult:
    """Path-free public proof identities plus private input locations."""

    input_paths: tuple[Path, ...] = field(repr=False)
    project_id: str
    clip_id: str
    amplitude_envelope_sha256: str
    preview_projection_sha256: str
    visual_candidate_sha256: str
    visual_revision: int
    visual_decision_sha256: str
    continuous_proof_sha256: str
    _proof: BodySwayContinuousPreviewProof = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return self._proof.document


def compile_body_sway_continuous_proof_command(
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
) -> P10ContinuousProofCommandResult:
    """Replay P10.4b1, prove all segments, then reject a changed head."""

    try:
        amplitude = compile_body_sway_amplitude_envelope_command(
            state_root, project_id, candidates_path, decision_path,
            probe_report_path,
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
        inputs = require_body_sway_continuous_proof_inputs(
            amplitude._candidate, amplitude._inputs
        )
        proof = compile_body_sway_continuous_preview_proof(inputs)
        require_unchanged_visual_review_head(
            state_root, project_id,
            temporary_preview_sha256, runtime_capture_bundle_sha256,
            capture_artifact_set_sha256, visual_candidate_sha256,
            visual_revision, visual_decision_sha256,
        )
        return P10ContinuousProofCommandResult(
            input_paths=amplitude.input_paths,
            project_id=proof.document["project_id"],
            clip_id=proof.document["clip_id"],
            amplitude_envelope_sha256=amplitude.amplitude_envelope_sha256,
            preview_projection_sha256=amplitude.preview_projection_sha256,
            visual_candidate_sha256=amplitude.visual_candidate_sha256,
            visual_revision=amplitude.visual_revision,
            visual_decision_sha256=amplitude.visual_decision_sha256,
            continuous_proof_sha256=proof.sha256,
            _proof=proof,
        )
    except P10ContinuousProofCommandError:
        raise
    except _FAILURES as exc:
        raise P10ContinuousProofCommandError(
            "Body-sway continuous proof command failed"
        ) from exc


_FAILURES = (
    AttributeError, BodySwayContinuousProofError,
    BodySwayContinuousProofInputError, KeyError, OSError, OverflowError,
    BodySwayVisualReviewApplicationError, P10AmplitudeEnvelopeCommandError,
    RecursionError, RuntimeError,
    TypeError, UnicodeError, ValueError,
)
