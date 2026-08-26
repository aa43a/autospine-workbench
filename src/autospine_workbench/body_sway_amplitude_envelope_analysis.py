"""Sample nine body-sway gains without claiming interval/continuous safety."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_probe_geometry import evaluate_prepared_body_sway_geometry_sample
from .body_sway_probe_geometry_context import prepare_body_sway_geometry_context
from .body_sway_probe_math import (
    BodySwayPoseSample, audit_body_sway_loop, quantize_body_sway_number,
    sample_body_sway_overlay,
)
from .body_sway_probe_math_inputs import normalize_phases
from .body_sway_probe_report import ENDPOINT_POSE_HASH_DOMAIN
from .body_sway_probe_report_evidence import (
    SampleStreamSealer, StructuralEvidenceAccumulator, tick_schedule_sha256,
)
from .body_sway_probe_sample_validation import representative_sample_sha256
from .body_sway_probe_sampler import prepare_body_sway_sampler
from .body_sway_amplitude_envelope_profile import (
    GAIN_DENOMINATOR,
    PROBE_HASH_DOMAIN,
    body_sway_scaled_amplitudes,
)
from .resolved_project import canonical_sha256

class BodySwayAmplitudeEnvelopeAnalysisError(ValueError):
    """Raised when exact admitted inputs cannot form sampled gain evidence."""

@dataclass(frozen=True, slots=True)
class AmplitudeEnvelopeAnalysis:
    """Frozen canonical JSON whose accessors always return detached values."""

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

def analyze_body_sway_amplitude_envelope(inputs: Any) -> AmplitudeEnvelopeAnalysis:
    """Replay gains 0/8 through 8/8 at exact preview sample ticks only."""

    try:
        from .body_sway_amplitude_envelope_inputs import (
            BodySwayAmplitudeEnvelopeInputs,
            require_body_sway_amplitude_envelope_inputs,
        )

        if type(inputs) is not BodySwayAmplitudeEnvelopeInputs:
            raise BodySwayAmplitudeEnvelopeAnalysisError(
                "Amplitude analysis requires exact admitted envelope inputs"
            )
        inputs = require_body_sway_amplitude_envelope_inputs(
            inputs.admission, inputs.preview_inputs, inputs.preview
        )
        probe_inputs = inputs.preview_inputs.probe_inputs
        report = inputs.preview_inputs.report
        projection = inputs.projection
        timing = probe_inputs.timing
        selection = probe_inputs.selection
        parameters = selection["parameters"]
        motion = probe_inputs.motion_instance_v2
        ticks = projection.sample_ticks
        schedule_sha = tick_schedule_sha256(ticks)
        _require_preview_schedule(ticks, schedule_sha, report)

        sampler = prepare_body_sway_sampler(
            timing, motion["tracks"],
            cycles=parameters["cycles"],
            per_bone_amplitude_deg=parameters["per_bone_amplitude_deg"],
            per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
        )
        geometry = prepare_body_sway_geometry_context(
            probe_inputs.rig, probe_inputs.target_profile)
        inventory = _inventories(probe_inputs.rig, motion["tracks"], parameters)
        phases = normalize_phases(parameters["per_bone_phase_fraction"])
        probes, reviewed_tracks = [], None
        for numerator in range(GAIN_DENOMINATOR + 1):
            probe, tracks_at_gain = _probe_gain(
                numerator, ticks=ticks, schedule_sha=schedule_sha,
                sampler=sampler, geometry=geometry, timing=timing,
                parameters=parameters, phases=phases, inventory=inventory,
            )
            probes.append(probe)
            if numerator == GAIN_DENOMINATOR:
                reviewed_tracks = tracks_at_gain
        _require_reviewed_gain_replay(
            probes[-1], reviewed_tracks, report, projection
        )
        return AmplitudeEnvelopeAnalysis(_canonical({"probes": probes}))
    except BodySwayAmplitudeEnvelopeAnalysisError:
        raise
    except (
        AttributeError, ImportError, KeyError, OverflowError, RecursionError,
        RuntimeError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayAmplitudeEnvelopeAnalysisError(
            f"Body-sway amplitude envelope analysis failed: {exc}"
        ) from exc


def _probe_gain(
    numerator: int, *, ticks, schedule_sha, sampler, geometry, timing,
    parameters, phases, inventory,
) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
    amplitudes = _scaled_amplitudes(
        parameters["per_bone_amplitude_deg"], numerator)
    stream = SampleStreamSealer(
        rig_bone_ids=inventory["rig_bone_ids"],
        rotation_bone_ids=inventory["rotation_bone_ids"],
        overlay_bone_ids=inventory["overlay_bone_ids"],
        attachments=inventory["attachments"],
    )
    structural = StructuralEvidenceAccumulator(
        rig_bone_ids=inventory["rig_bone_ids"],
        attachments=inventory["attachments"],
    )
    collect_tracks = numerator == GAIN_DENOMINATOR
    combined_keys = {
        bone_id: [] for bone_id in inventory["rotation_bone_ids"]
    } if collect_tracks else None
    start = end = None
    start_sha = end_sha = None
    for index, tick in enumerate(ticks):
        source = sampler.sample(tick)
        sample = _scaled_sample(
            source, amplitudes=amplitudes, phases=phases, timing=timing,
            cycles=parameters["cycles"],
        )
        visible = _visible_sample(sample, inventory["rotation_bone_ids"])
        stream.observe(tick, visible["sample_sha256"])
        structural.observe(
            evaluate_prepared_body_sway_geometry_sample(geometry, sample)
        )
        if combined_keys is not None:
            for row in visible["combined_rotation_deg"]:
                combined_keys[row["bone_id"]].append(
                    {"tick": tick, "value": row["value"]}
                )
        if index == 0:
            start, start_sha = sample, _endpoint_pose_sha256(visible)
        if index == len(ticks) - 1:
            end, end_sha = sample, _endpoint_pose_sha256(visible)
    if start is None or end is None or start_sha is None or end_sha is None:
        raise BodySwayAmplitudeEnvelopeAnalysisError(
            "Amplitude gain schedule produced no samples"
        )
    checks = structural.checks(
        loop_audit=audit_body_sway_loop(timing, start, end),
        start_pose_state_sha256=start_sha,
        end_pose_state_sha256=end_sha,
        expected_sample_count=len(ticks),
    )
    rejected = any(row["status"] == "rejected" for row in checks[:5])
    reviewed = numerator == GAIN_DENOMINATOR
    row = {
        "gain": {"numerator": numerator, "denominator": GAIN_DENOMINATOR},
        "amplitudes": amplitudes,
        "sample_count": len(ticks),
        "tick_schedule_sha256": schedule_sha,
        "sample_stream_sha256": stream.finish(len(ticks)),
        "checks": checks,
        "status": "sampled_structural_rejected" if rejected
                  else "sampled_structural_passed",
        "visual_review_status": "approved" if reviewed else "not_reviewed",
        "preview_relation": "exact-reviewed-probe-replay" if reviewed
        else "hypothetical-scaled-key-states",
    }
    row["sampled_evidence_sha256"] = canonical_sha256(
        {"domain": PROBE_HASH_DOMAIN, "probe": row})
    tracks = None if combined_keys is None else [
        {"bone_id": bone_id, "property": "rotation",
         "keys": combined_keys[bone_id]}
        for bone_id in inventory["rotation_bone_ids"]
    ]
    return row, tracks

def _scaled_sample(source, *, amplitudes, phases, timing, cycles):
    overlay = tuple(
        (
            amplitude["bone_id"],
            sample_body_sway_overlay(
                amplitude["value"], phase, source.tick,
                timing["duration_ticks"], cycles),
        )
        for amplitude, (_bone_id, phase) in zip(amplitudes, phases, strict=True)
    )
    base = dict(source.base_rotation_deg)
    overlay_map = dict(overlay)
    combined = tuple(
        (
            bone_id,
            quantize_body_sway_number(value + overlay_map.get(bone_id, 0.0)),
        )
        for bone_id, value in sorted(base.items())
    )
    return BodySwayPoseSample(
        source.tick, source.base_rotation_deg, overlay, combined,
        source.root_translation_xy)

def _scaled_amplitudes(rows, numerator):
    return body_sway_scaled_amplitudes(rows, numerator)

def _inventories(rig, tracks, parameters):
    overlay = tuple(row["bone_id"]
                    for row in parameters["per_bone_amplitude_deg"])
    rotations = tuple(sorted(
        {row["bone_id"] for row in tracks if row["property"] == "rotation"}
        | set(overlay)
    ))
    return {
        "rig_bone_ids": tuple(sorted(row["id"] for row in rig["bones"])),
        "rotation_bone_ids": rotations,
        "overlay_bone_ids": overlay,
        "attachments": tuple(sorted((row["id"], row["type"])
                                    for row in rig["attachments"])),
    }

def _visible_sample(sample, rotation_bone_ids):
    base = dict(sample.base_rotation_deg)
    overlay = dict(sample.overlay_rotation_deg)
    combined = dict(sample.combined_rotation_deg)
    if tuple(sorted(base)) != rotation_bone_ids \
            or tuple(sorted(combined)) != rotation_bone_ids:
        raise BodySwayAmplitudeEnvelopeAnalysisError(
            "Amplitude sample rotation inventory changed"
        )
    row = {
        "tick": sample.tick,
        "base_rotation_deg": _rotation_rows(rotation_bone_ids, base),
        "overlay_rotation_deg": _rotation_rows(rotation_bone_ids, overlay),
        "combined_rotation_deg": _rotation_rows(rotation_bone_ids, combined),
        "root_translation_xy": list(sample.root_translation_xy),
    }
    row["sample_sha256"] = representative_sample_sha256(row)
    return row

def _endpoint_pose_sha256(row):
    return canonical_sha256({
        "domain": ENDPOINT_POSE_HASH_DOMAIN,
        "base_rotation_deg": row["base_rotation_deg"],
        "overlay_rotation_deg": row["overlay_rotation_deg"],
        "combined_rotation_deg": row["combined_rotation_deg"],
        "root_translation_xy": row["root_translation_xy"],
    })

def _require_preview_schedule(ticks, schedule_sha, report):
    schedule = report["schedule"]
    if len(ticks) != schedule["sample_count"] \
            or ticks[0] != schedule["first_tick"] \
            or ticks[-1] != schedule["last_tick"] \
            or schedule_sha != schedule["tick_schedule_sha256"]:
        raise BodySwayAmplitudeEnvelopeAnalysisError(
            "Amplitude schedule differs from the exact preview"
        )

def _require_reviewed_gain_replay(probe, tracks, report, projection):
    if tracks is None \
            or probe["sample_stream_sha256"] \
            != report["sample_stream"]["sample_stream_sha256"] \
            or probe["checks"] != report["checks"] \
            or tracks != projection.rotation_tracks:
        raise BodySwayAmplitudeEnvelopeAnalysisError(
            "Reviewed gain differs from P10.2 or its exact preview keys"
        )

def _rotation_rows(inventory, values):
    return [
        {"bone_id": bone_id, "value": values.get(bone_id, 0.0)}
        for bone_id in inventory
    ]

def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
