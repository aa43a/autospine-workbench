"""Pure P10.4b1 v2 compiler bound to current Admission and Preview v2."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_amplitude_envelope_analysis import (
    _inventories, _probe_gain, _require_preview_schedule,
)
from .body_sway_amplitude_envelope_profile_v2 import (
    GAIN_DENOMINATOR, PROBE_HASH_DOMAIN,
    amplitude_analyzer_profile_v2, amplitude_claims_v2,
    amplitude_parameterization_v2, amplitude_release_gate_v2,
)
from .body_sway_preview_projection_v2 import BodySwayPreviewProjectionV2
from .body_sway_probe_geometry_context import (
    prepare_body_sway_geometry_context_for_viewport,
)
from .body_sway_probe_math_inputs import normalize_phases
from .body_sway_probe_report_evidence import tick_schedule_sha256
from .body_sway_probe_sampler import prepare_body_sway_sampler
from .body_sway_review_admission_consumer_v2 import (
    CurrentBodySwayReviewAdmissionV2,
)
from .p10_safety_analysis_source_v2 import P10SafetyAnalysisSourceV2
from .resolved_project import canonical_sha256


FORMAT = "autospine-body-sway-amplitude-envelope-candidate"
FORMAT_VERSION = 2


class BodySwayAmplitudeEnvelopeV2Error(ValueError):
    """Raised when current v2 evidence cannot form sampled gain evidence."""


@dataclass(frozen=True, slots=True)
class BodySwayAmplitudeEnvelopeCandidateV2:
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


def compile_body_sway_amplitude_envelope_candidate_v2(
    admission: CurrentBodySwayReviewAdmissionV2,
    source: P10SafetyAnalysisSourceV2,
) -> BodySwayAmplitudeEnvelopeCandidateV2:
    """Compile nine viewport-aware structural points; infer no interval."""

    try:
        _require_exact_inputs(admission, source)
        inputs = source.preview_inputs
        probe_inputs = inputs.probe_inputs
        report, projection = inputs.report, source.projection
        timing, selection = inputs.timing, inputs.selection
        parameters = selection["parameters"]
        ticks = projection.sample_ticks
        schedule_sha = tick_schedule_sha256(ticks)
        _require_preview_schedule(ticks, schedule_sha, report)
        sampler = prepare_body_sway_sampler(
            timing, probe_inputs.motion_instance_v2["tracks"],
            cycles=parameters["cycles"],
            per_bone_amplitude_deg=
                parameters["per_bone_amplitude_deg"],
            per_bone_phase_fraction=
                parameters["per_bone_phase_fraction"],
        )
        geometry = prepare_body_sway_geometry_context_for_viewport(
            probe_inputs.rig, probe_inputs.target_profile,
            inputs.world_viewport,
        )
        inventory = _inventories(
            probe_inputs.rig,
            probe_inputs.motion_instance_v2["tracks"], parameters,
        )
        phases = normalize_phases(
            parameters["per_bone_phase_fraction"]
        )
        probes, reviewed_tracks = [], None
        for numerator in range(GAIN_DENOMINATOR + 1):
            row, tracks = _probe_gain(
                numerator, ticks=ticks, schedule_sha=schedule_sha,
                sampler=sampler, geometry=geometry, timing=timing,
                parameters=parameters, phases=phases,
                inventory=inventory,
            )
            _upgrade_probe_identity(row, numerator)
            probes.append(row)
            if numerator == GAIN_DENOMINATOR:
                reviewed_tracks = tracks
        _require_reviewed_replay(
            probes[-1], reviewed_tracks, report, projection,
        )
        document = _document(admission, source, probes)
        from .body_sway_amplitude_envelope_validation_v2 import (
            require_body_sway_amplitude_envelope_candidate_v2,
        )
        require_body_sway_amplitude_envelope_candidate_v2(document)
        return BodySwayAmplitudeEnvelopeCandidateV2(_canonical(document))
    except BodySwayAmplitudeEnvelopeV2Error:
        raise
    except _FAILURES as exc:
        raise BodySwayAmplitudeEnvelopeV2Error(
            f"Body-sway amplitude envelope v2 failed: {exc}"
        ) from exc


def _require_exact_inputs(admission, source) -> None:
    if type(admission) is not CurrentBodySwayReviewAdmissionV2 \
            or type(source) is not P10SafetyAnalysisSourceV2:
        raise BodySwayAmplitudeEnvelopeV2Error(
            "Amplitude v2 requires exact current process-local values"
        )
    result = admission._result
    preview = source.record.result._preview
    admitted = result._inputs
    if source.package_id != result.package_id \
            or source.project_id != result.project_id \
            or source.clip_id != result.clip_id \
            or preview.canonical_bytes \
                != admitted._preview_json.encode("utf-8") \
            or preview.artifact_bytes \
                != dict(admitted._preview_artifact_items):
        raise BodySwayAmplitudeEnvelopeV2Error(
            "Amplitude v2 source differs from its current admission"
        )


def _upgrade_probe_identity(row, numerator) -> None:
    reviewed = numerator == GAIN_DENOMINATOR
    row["visual_review_status"] = (
        "official_runtime_sampled_cases_approved"
        if reviewed else "not_reviewed"
    )
    row["preview_relation"] = (
        "exact-preview-v2-structural-replay-reviewed-world-viewport"
        if reviewed else "hypothetical-scaled-key-states"
    )
    row.pop("sampled_evidence_sha256", None)
    row["sampled_evidence_sha256"] = canonical_sha256({
        "domain": PROBE_HASH_DOMAIN, "probe": row,
    })


def _require_reviewed_replay(probe, tracks, report, projection) -> None:
    if tracks is None \
            or probe["sample_stream_sha256"] \
                != report["sample_stream"]["sample_stream_sha256"] \
            or tracks != projection.rotation_tracks:
        raise BodySwayAmplitudeEnvelopeV2Error(
            "Reviewed gain differs from exact Preview v2 keys"
        )
    original = {
        row["check_id"]: row for row in report["checks"]
        if row["check_id"] != "sampled_canvas_containment"
    }
    replay = {
        row["check_id"]: row for row in probe["checks"]
        if row["check_id"] != "sampled_canvas_containment"
    }
    if original != replay:
        raise BodySwayAmplitudeEnvelopeV2Error(
            "Reviewed gain non-canvas checks differ from P10.2"
        )


def _document(admission, source, probes):
    inputs = source.preview_inputs
    statuses = [row["status"] for row in probes]
    return {
        "format": FORMAT, "format_version": FORMAT_VERSION,
        "project_id": source.project_id, "clip_id": source.clip_id,
        "source": {
            "review_admission_v2_sha256": admission.admission_sha256,
            "review_admission_v2": admission.document,
            "temporary_preview_v2_sha256":
                source.record.result.temporary_preview_v2_sha256,
            "preview_projection_v2_sha256": source.projection.sha256,
            "reviewed_world_viewport": inputs.world_viewport,
            "reviewed_probe_report": inputs.report,
        },
        "timing": inputs.timing, "reviewed_selection": inputs.selection,
        "parameterization": amplitude_parameterization_v2(inputs.selection),
        "probes": probes, "analyzer": amplitude_analyzer_profile_v2(),
        "claims": amplitude_claims_v2(), "status": "candidate_only",
        "release_gate": amplitude_release_gate_v2(),
        "summary": {
            "gain_probe_count": len(probes),
            "sampled_structural_passed_count":
                statuses.count("sampled_structural_passed"),
            "sampled_structural_rejected_count":
                statuses.count("sampled_structural_rejected"),
            "reviewed_gain_status": probes[-1]["status"],
            "sample_evaluation_count": sum(
                row["sample_count"] for row in probes
            ),
        },
    }


def _canonical(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


_FAILURES = (
    AttributeError, ImportError, KeyError, OverflowError, RecursionError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "BodySwayAmplitudeEnvelopeCandidateV2",
    "BodySwayAmplitudeEnvelopeV2Error",
    "compile_body_sway_amplitude_envelope_candidate_v2",
]
