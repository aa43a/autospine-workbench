"""Exact P10.2 schedule replay for tri-domain capture envelopes."""

from __future__ import annotations

from .body_sway_probe_geometry import (
    evaluate_prepared_body_sway_geometry_sample,
)
from .body_sway_probe_geometry_context import (
    prepare_body_sway_geometry_context,
)
from .body_sway_probe_math import BodySwayPoseSample, build_body_sway_sample_ticks
from .body_sway_probe_report_evidence import tick_schedule_sha256
from .body_sway_probe_sampler import prepare_body_sway_sampler
from .capture_framing_envelopes import (
    CaptureEnvelopeAccumulator,
    CaptureFramingEnvelopeError,
    CaptureFramingEnvelopeSet,
    build_capture_framing_envelope_set,
    canvas_bounds_to_runtime,
    contains_with_capture_margin,
    observe_geometry,
    proposed_runtime_world_viewport,
    setup_capture_envelope,
    union_canvas_envelope,
)


class CaptureFramingGeometryError(ValueError):
    """Raised when exact sampled geometry cannot form bounded framing."""


def sample_capture_envelopes(inputs, report) -> CaptureFramingEnvelopeSet:
    """Replay the exact P10.2 schedule into setup/base/combined envelopes."""

    try:
        parameters = inputs.selection["parameters"]
        motion = inputs.motion_instance_v2
        ticks = build_body_sway_sample_ticks(
            inputs.timing, motion["tracks"], cycles=parameters["cycles"],
            per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
        )
        if tick_schedule_sha256(ticks) \
                != report.document["schedule"]["tick_schedule_sha256"]:
            raise CaptureFramingGeometryError(
                "Capture framing schedule differs from P10.2"
            )
        sampler = prepare_body_sway_sampler(
            inputs.timing, motion["tracks"], cycles=parameters["cycles"],
            per_bone_amplitude_deg=parameters["per_bone_amplitude_deg"],
            per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
        )
        context = prepare_body_sway_geometry_context(
            inputs.rig, inputs.target_profile,
        )
        base = CaptureEnvelopeAccumulator("base", context.canvas_size[1])
        combined = CaptureEnvelopeAccumulator(
            "combined", context.canvas_size[1],
        )
        for tick in ticks:
            sample = sampler.sample(tick)
            zero_overlay = tuple(
                (bone_id, 0.0)
                for bone_id, _value in sample.overlay_rotation_deg
            )
            base_pose = BodySwayPoseSample(
                sample.tick, sample.base_rotation_deg, zero_overlay,
                sample.base_rotation_deg, sample.root_translation_xy,
            )
            observe_geometry(
                base, tick,
                evaluate_prepared_body_sway_geometry_sample(context, base_pose),
            )
            observe_geometry(
                combined, tick,
                evaluate_prepared_body_sway_geometry_sample(context, sample),
            )
        return build_capture_framing_envelope_set(
            setup_capture_envelope(context), base.finish(), combined.finish(),
            context.canvas_size[1],
        )
    except CaptureFramingGeometryError:
        raise
    except (
        CaptureFramingEnvelopeError, KeyError, OverflowError,
        TypeError, ValueError,
    ) as exc:
        raise CaptureFramingGeometryError(
            f"Capture framing geometry failed: {exc}"
        ) from exc


__all__ = [
    "CaptureFramingGeometryError", "sample_capture_envelopes",
    "canvas_bounds_to_runtime", "contains_with_capture_margin",
    "proposed_runtime_world_viewport", "union_canvas_envelope",
]
