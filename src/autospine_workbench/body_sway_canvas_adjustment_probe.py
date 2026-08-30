"""Prepared gain probes for sampled P10.2 canvas adjustment diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from .body_sway_canvas_adjustment_profile import (
    EVIDENCE_HASH_DOMAIN,
    GAIN_DENOMINATOR,
    scaled_body_sway_amplitudes,
)
from .body_sway_probe_geometry import (
    evaluate_prepared_body_sway_geometry_sample,
)
from .body_sway_probe_geometry_context import (
    PreparedBodySwayGeometryContext,
    prepare_body_sway_geometry_context,
)
from .body_sway_probe_inputs import BodySwayProbeInputs
from .body_sway_probe_math import (
    BodySwayPoseSample,
    build_body_sway_sample_ticks,
    quantize_body_sway_number,
    sample_body_sway_overlay,
)
from .body_sway_probe_math_inputs import normalize_phases
from .body_sway_probe_report_evidence import tick_schedule_sha256
from .body_sway_probe_sampler import (
    PreparedBodySwaySampler,
    prepare_body_sway_sampler,
)
from .idle_behavior_inventory import BODY_BONE_IDS


class BodySwayCanvasAdjustmentProbeError(ValueError):
    """Raised when an exact gain cannot produce sampled diagnostics."""


@dataclass(frozen=True, slots=True)
class PreparedBodySwayCanvasAdjustmentProbe:
    """Detached schedule, sampler, and geometry shared by all fixed gains."""

    timing: dict[str, Any]
    parameters: dict[str, Any]
    ticks: tuple[int, ...]
    tick_schedule_sha256: str
    sampler: PreparedBodySwaySampler
    geometry: PreparedBodySwayGeometryContext


def prepare_body_sway_canvas_adjustment_probe(
    inputs: BodySwayProbeInputs,
) -> PreparedBodySwayCanvasAdjustmentProbe:
    """Prepare exact P10.2 inputs once for bounded uniform-gain replay."""

    try:
        if type(inputs) is not BodySwayProbeInputs:
            raise BodySwayCanvasAdjustmentProbeError(
                "Canvas adjustment requires exact admitted P10.2 inputs"
            )
        timing = inputs.timing
        parameters = inputs.selection["parameters"]
        tracks = inputs.motion_instance_v2["tracks"]
        ticks = build_body_sway_sample_ticks(
            timing, tracks, cycles=parameters["cycles"],
            per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
        )
        return PreparedBodySwayCanvasAdjustmentProbe(
            timing=timing,
            parameters=parameters,
            ticks=ticks,
            tick_schedule_sha256=tick_schedule_sha256(ticks),
            sampler=prepare_body_sway_sampler(
                timing, tracks, cycles=parameters["cycles"],
                per_bone_amplitude_deg=parameters["per_bone_amplitude_deg"],
                per_bone_phase_fraction=parameters[
                    "per_bone_phase_fraction"
                ],
            ),
            geometry=prepare_body_sway_geometry_context(
                inputs.rig, inputs.target_profile,
            ),
        )
    except BodySwayCanvasAdjustmentProbeError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise BodySwayCanvasAdjustmentProbeError(
            f"Canvas adjustment preparation failed: {exc}"
        ) from exc


def probe_body_sway_canvas_gain(
    prepared: PreparedBodySwayCanvasAdjustmentProbe,
    numerator: int,
) -> dict[str, Any]:
    """Evaluate one discrete gain; this is not a safe interval claim."""

    try:
        if type(prepared) is not PreparedBodySwayCanvasAdjustmentProbe:
            raise BodySwayCanvasAdjustmentProbeError(
                "Canvas adjustment prepared probe is invalid"
            )
        amplitudes = scaled_body_sway_amplitudes(
            prepared.parameters["per_bone_amplitude_deg"], numerator,
        )
        phases = normalize_phases(
            prepared.parameters["per_bone_phase_fraction"]
        )
        digest = hashlib.sha256()
        _feed(digest, {
            "domain": EVIDENCE_HASH_DOMAIN,
            "gain": {"numerator": numerator,
                     "denominator": GAIN_DENOMINATOR},
            "tick_schedule_sha256": prepared.tick_schedule_sha256,
        })
        stats = _CanvasStats(prepared.geometry.canvas_size)
        peaks = {bone_id: 0.0 for bone_id in BODY_BONE_IDS}
        for tick in prepared.ticks:
            sample = _scaled_sample(
                prepared.sampler.sample(tick), amplitudes, phases,
                prepared.timing, prepared.parameters["cycles"],
            )
            result = evaluate_prepared_body_sway_geometry_sample(
                prepared.geometry, sample,
            )
            stats.observe(result)
            for bone_id, value in sample.overlay_rotation_deg:
                peaks[bone_id] = max(peaks[bone_id], abs(value))
            _feed(digest, {
                "tick": tick,
                "overlay_rotation_deg": list(sample.overlay_rotation_deg),
                "geometry_status": result.status,
                "canvas_failures": [
                    asdict(failure) for failure in result.canvas_failures
                ],
            })
        return stats.document(
            numerator, len(prepared.ticks), peaks, digest.hexdigest(),
        )
    except BodySwayCanvasAdjustmentProbeError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise BodySwayCanvasAdjustmentProbeError(
            f"Canvas adjustment gain probe failed: {exc}"
        ) from exc


@dataclass(slots=True)
class _CanvasStats:
    canvas_size: tuple[float, float]
    failure_ticks: int = 0
    failure_vertices: int = 0
    geometry_rejections: int = 0
    first_tick: int | None = None
    last_tick: int | None = None
    attachments: set[str] | None = None
    sides: set[str] | None = None
    maximum: float = 0.0
    worst: dict[str, Any] | None = None

    def __post_init__(self):
        self.attachments, self.sides = set(), set()

    def observe(self, result):
        failures = result.canvas_failures
        self.geometry_rejections += int(result.status != "passed")
        if failures:
            self.failure_ticks += 1
            self.first_tick = result.tick if self.first_tick is None else self.first_tick
            self.last_tick = result.tick
        for failure in failures:
            self.failure_vertices += 1
            self.attachments.add(failure.attachment_id)
            self.sides.update(failure.sides)
            overflow = _overflow(failure.point_xy, failure.sides, self.canvas_size)
            if overflow > self.maximum:
                self.maximum = overflow
                self.worst = {
                    "tick": result.tick,
                    "attachment_id": failure.attachment_id,
                    "vertex_index": failure.vertex_index,
                    "point_xy": [_number(value) for value in failure.point_xy],
                    "sides": sorted(failure.sides),
                    "overflow_px": _number(overflow),
                }

    def document(self, numerator, sample_count, peaks, evidence_sha):
        return {
            "gain": {"numerator": numerator,
                     "denominator": GAIN_DENOMINATOR},
            "sample_count": sample_count,
            "canvas_status": "rejected" if self.failure_ticks else "passed",
            "sampled_geometry_status": (
                "rejected" if self.geometry_rejections else "passed"
            ),
            "canvas_failure_tick_count": self.failure_ticks,
            "canvas_failure_vertex_count": self.failure_vertices,
            "geometry_rejection_tick_count": self.geometry_rejections,
            "first_failure_tick": self.first_tick,
            "last_failure_tick": self.last_tick,
            "affected_attachment_ids": sorted(self.attachments),
            "failure_sides": sorted(self.sides),
            "max_overflow_px": _number(self.maximum),
            "worst_failure": self.worst,
            "sampled_body_sway_peak_abs_delta_deg": [
                {"bone_id": bone_id, "value": _number(peaks[bone_id])}
                for bone_id in BODY_BONE_IDS
            ],
            "evidence_sha256": evidence_sha,
        }


def _scaled_sample(source, amplitudes, phases, timing, cycles):
    overlay = tuple(
        (row["bone_id"], sample_body_sway_overlay(
            row["value"], phase, source.tick,
            timing["duration_ticks"], cycles,
        ))
        for row, (_bone_id, phase) in zip(amplitudes, phases, strict=True)
    )
    base, overlay_map = dict(source.base_rotation_deg), dict(overlay)
    combined = tuple(
        (bone_id, quantize_body_sway_number(
            value + overlay_map.get(bone_id, 0.0)
        )) for bone_id, value in sorted(base.items())
    )
    return BodySwayPoseSample(
        source.tick, source.base_rotation_deg, overlay, combined,
        source.root_translation_xy,
    )


def _overflow(point, sides, canvas):
    x, y = point
    values = {
        "left": -x, "right": x - canvas[0],
        "top": -y, "bottom": y - canvas[1],
    }
    return max(values[side] for side in sides)


def _number(value):
    return quantize_body_sway_number(float(value))


def _feed(digest, value):
    payload = json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)
