"""P10.4b2 v2 viewport-aware continuous preview-model proof."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_amplitude_envelope_v2 import (
    BodySwayAmplitudeEnvelopeCandidateV2,
)
from .body_sway_amplitude_envelope_validation_v2 import (
    body_sway_amplitude_envelope_candidate_sha256_v2,
    require_body_sway_amplitude_envelope_candidate_v2,
)
from .body_sway_continuous_backend_validation import (
    BodySwayContinuousBackendValidationError,
    require_body_sway_interval_backend_result,
)
from .body_sway_continuous_interval import (
    BodySwayContinuousIntervalError, BodySwayIntervalProofBudget,
    prove_body_sway_sampled_linear_segment,
)
from .body_sway_continuous_proof_analysis import (
    _indeterminate_segment, _summary,
)
from .body_sway_continuous_proof_profile_v2 import (
    continuous_analyzer_profile_v2, continuous_claims_v2,
    continuous_problem_v2, continuous_proof_budget_v2,
    continuous_release_gate_v2, continuous_segment_sha256_v2,
    continuous_source_sha256_v2,
)
from .body_sway_probe_geometry_context import (
    prepare_body_sway_geometry_context_for_viewport,
)
from .body_sway_probe_sampler import prepare_body_sway_sampler
from .motion_instance_v2_validation import motion_instance_v2_sha256
from .p10_safety_analysis_source_v2 import P10SafetyAnalysisSourceV2
from .resolved_project import canonical_sha256
from .temporary_body_sway_preview_validation_v2 import (
    require_temporary_body_sway_preview_manifest_v2,
)


FORMAT = "autospine-body-sway-continuous-preview-proof"
FORMAT_VERSION = 2
Progress = Callable[[str, int, int], None]


class BodySwayContinuousProofV2Error(ValueError):
    """Raised when a complete exact v2 source cannot form a safe result."""


class _ProgressCallbackError(RuntimeError):
    """Keep observer faults outside the geometric evidence domain."""


@dataclass(frozen=True, slots=True)
class BodySwayContinuousPreviewProofV2:
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def compile_body_sway_continuous_preview_proof_v2(
    candidate: BodySwayAmplitudeEnvelopeCandidateV2,
    exact: P10SafetyAnalysisSourceV2,
    *, on_progress: Progress | None = None,
) -> BodySwayContinuousPreviewProofV2:
    """Prove every adjacent Preview v2 segment over closed gain [0, 1]."""

    try:
        if type(candidate) is not BodySwayAmplitudeEnvelopeCandidateV2 \
                or type(exact) is not P10SafetyAnalysisSourceV2 \
                or on_progress is not None and not callable(on_progress):
            raise BodySwayContinuousProofV2Error(
                "Continuous proof v2 requires exact in-memory inputs"
            )
        require_body_sway_amplitude_envelope_candidate_v2(
            candidate.document
        )
        source = _build_source(candidate, exact)
        analysis = _analyze(source, on_progress=on_progress)
        certified = analysis["status"] \
            == "continuous_preview_model_structural_certified"
        document = {
            "format": FORMAT, "format_version": FORMAT_VERSION,
            "project_id": exact.project_id, "clip_id": exact.clip_id,
            "source": source, **analysis,
            "analyzer": continuous_analyzer_profile_v2(),
            "release_gate": continuous_release_gate_v2(certified),
        }
        from .body_sway_continuous_proof_validation_v2 import (
            require_body_sway_continuous_preview_proof_v2,
        )
        validation_progress = None if on_progress is None else (
            lambda _stage, _current, _total:
                _forward_progress(
                    on_progress, "continuous_validation", _current, _total,
                )
        )
        require_body_sway_continuous_preview_proof_v2(
            document, on_progress=validation_progress,
        )
        return BodySwayContinuousPreviewProofV2(_canonical(document))
    except BodySwayContinuousProofV2Error:
        raise
    except _FAILURES as exc:
        raise BodySwayContinuousProofV2Error(
            f"Body-sway continuous proof v2 failed: {exc}"
        ) from exc


def _build_source(candidate, exact):
    inputs = exact.preview_inputs
    probe = inputs.probe_inputs
    preview = exact.record.result._preview
    projection = exact.projection
    candidate_doc = candidate.document
    if candidate_doc["project_id"] != exact.project_id \
            or candidate_doc["clip_id"] != exact.clip_id \
            or candidate_doc["source"]["temporary_preview_v2_sha256"] \
                != preview.sha256 \
            or candidate_doc["source"]["preview_projection_v2_sha256"] \
                != projection.sha256:
        raise BodySwayContinuousProofV2Error(
            "Continuous proof v2 candidate is cross-wired"
        )
    require_temporary_body_sway_preview_manifest_v2(preview.document)
    source = {
        "amplitude_envelope_candidate_v2_sha256":
            candidate.sha256,
        "amplitude_envelope_candidate_v2": candidate_doc,
        "rig_ir_sha256": canonical_sha256(probe.rig),
        "rig_ir": probe.rig,
        "target_profile_sha256": canonical_sha256(probe.target_profile),
        "target_profile": probe.target_profile,
        "motion_instance_v2_sha256":
            motion_instance_v2_sha256(probe.motion_instance_v2),
        "motion_instance_v2": probe.motion_instance_v2,
        "temporary_preview_v2_sha256": preview.sha256,
        "temporary_preview_v2": preview.document,
        "preview_projection_v2_sha256": projection.sha256,
        "preview_projection_v2": projection.document,
        "reviewed_world_viewport": inputs.world_viewport,
    }
    source["source_set_sha256"] = continuous_source_sha256_v2(source)
    return source


def _analyze(source, *, on_progress):
    candidate = source["amplitude_envelope_candidate_v2"]
    timing, selection = candidate["timing"], candidate["reviewed_selection"]
    parameters = selection["parameters"]
    motion = source["motion_instance_v2"]
    ticks = source["preview_projection_v2"]["sample_ticks"]
    sampler = prepare_body_sway_sampler(
        timing, motion["tracks"], cycles=parameters["cycles"],
        per_bone_amplitude_deg=parameters["per_bone_amplitude_deg"],
        per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
    )
    samples = tuple(sampler.sample(tick) for tick in ticks)
    context = prepare_body_sway_geometry_context_for_viewport(
        source["rig_ir"], source["target_profile"],
        source["reviewed_world_viewport"],
    )
    values = continuous_proof_budget_v2()
    segments, used = [], 0
    if on_progress is not None:
        _forward_progress(
            on_progress, "continuous_boxes", 0, values["max_total_boxes"],
        )
    for left, right in zip(samples, samples[1:]):
        remaining = values["max_total_boxes"] - used
        if remaining <= 0:
            row = _v2_indeterminate(
                context, left.tick, right.tick,
                "global_subdivision_box_budget_exhausted",
            )
        else:
            budget = BodySwayIntervalProofBudget(
                max_depth=values["max_depth"],
                max_boxes=min(values["max_boxes_per_segment"], remaining),
            )
            box_progress = None if on_progress is None else (
                lambda current, _total, offset=used:
                    _forward_progress(
                        on_progress,
                        "continuous_boxes",
                        min(values["max_total_boxes"], offset + current),
                        values["max_total_boxes"],
                    )
            )
            row = _prove_segment(
                context, left, right, budget,
                on_progress=box_progress,
            )
        used += row["evaluated_box_count"]
        if "interval_backend_error" in row["reason_codes"]:
            used = values["max_total_boxes"]
        segments.append(row)
    if on_progress is not None:
        _forward_progress(
            on_progress,
            "continuous_boxes", values["max_total_boxes"],
            values["max_total_boxes"],
        )
    certified = bool(segments) and all(
        row["status"] == "continuous_structural_certified"
        for row in segments
    )
    return {
        "problem": continuous_problem_v2(
            source["source_set_sha256"], list(ticks),
        ),
        "segments": segments,
        "status": "continuous_preview_model_structural_certified"
            if certified else "indeterminate",
        "claims": continuous_claims_v2(certified),
        "summary": _summary(segments),
    }


def _prove_segment(context, left, right, budget, *, on_progress=None):
    try:
        proof = prove_body_sway_sampled_linear_segment(
            context, left, right, budget=budget,
            on_progress=on_progress,
        )
        row = require_body_sway_interval_backend_result(
            proof, context=context, left_tick=left.tick,
            right_tick=right.tick, budget=budget,
        )
    except _ProgressCallbackError:
        raise
    except (
        ArithmeticError, BodySwayContinuousBackendValidationError,
        BodySwayContinuousIntervalError, OverflowError, RuntimeError,
        TypeError, ValueError,
    ):
        return _v2_indeterminate(
            context, left.tick, right.tick, "interval_backend_error",
        )
    row["segment_evidence_sha256"] = continuous_segment_sha256_v2(row)
    return row


def _forward_progress(callback, stage, current, total):
    try:
        callback(stage, current, total)
    except Exception as exc:
        raise _ProgressCallbackError(
            "Continuous proof v2 progress observer failed"
        ) from exc


def _v2_indeterminate(context, left, right, reason):
    row = _indeterminate_segment(context, left, right, reason)
    row.pop("segment_evidence_sha256", None)
    row["segment_evidence_sha256"] = continuous_segment_sha256_v2(row)
    return row


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


_FAILURES = (
    AttributeError, BodySwayContinuousBackendValidationError,
    BodySwayContinuousIntervalError, KeyError, OverflowError,
    RecursionError, RuntimeError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "BodySwayContinuousPreviewProofV2", "BodySwayContinuousProofV2Error",
    "compile_body_sway_continuous_preview_proof_v2",
]
