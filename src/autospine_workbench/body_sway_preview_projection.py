"""Internal frozen sampled-linear projection for a temporary body-sway preview."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .body_sway_preview_inputs import BodySwayPreviewInputs
from .body_sway_preview_profile import (
    BASE_ANIMATION_NAME,
    COMBINED_ANIMATION_NAME,
    MAX_PREVIEW_SAMPLE_COUNT,
    MAX_ROTATION_KEY_COUNT,
    MAX_ROTATION_TRACK_COUNT,
    PROJECTION_DIGEST_DOMAIN,
    body_sway_preview_compiler_profile,
)
from .body_sway_probe_math import build_body_sway_sample_ticks
from .body_sway_probe_math_inputs import BodySwayProbeMathError
from .body_sway_probe_report_evidence import tick_schedule_sha256
from .body_sway_probe_sampler import prepare_body_sway_sampler


class BodySwayPreviewProjectionError(ValueError):
    """Raised when exact probe samples cannot form the bounded projection."""


@dataclass(frozen=True, slots=True)
class BodySwayPreviewProjection:
    """Internal value; it is deliberately not a public motion contract."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def sample_ticks(self) -> tuple[int, ...]:
        return tuple(self.document["sample_ticks"])

    @property
    def rotation_tracks(self) -> list[dict[str, Any]]:
        return self.document["rotation_tracks"]

    @property
    def public_metadata(self) -> dict[str, Any]:
        document = self.document
        summary = document["summary"]
        return {
            "projection_sha256": self.sha256,
            "probe_tick_schedule_sha256":
                document["probe_tick_schedule_sha256"],
            "probe_sample_stream_sha256":
                document["probe_sample_stream_sha256"],
            "base_motion_instance_v2_sha256":
                document["source"]["base_motion_instance_v2_sha256"],
            "sample_count": summary["sample_count"],
            "rotation_track_count": summary["rotation_track_count"],
            "rotation_key_count": summary["rotation_key_count"],
            "sampling": "p10-probe-schedule",
            "rotation_interpolation": "sampled-linear",
            "root_translation": "exact-motion-instance-v2",
            "markers": "exact-motion-instance-v2",
            "draw_order": "exact-motion-instance-v2-stepped",
            "animation_names": {
                "base": BASE_ANIMATION_NAME,
                "combined": COMBINED_ANIMATION_NAME,
            },
        }


def compile_body_sway_preview_projection(
    inputs: BodySwayPreviewInputs,
) -> BodySwayPreviewProjection:
    """Sample the admitted math; do not emit MIv3 or a persistent timeline."""

    if type(inputs) is not BodySwayPreviewInputs:
        raise BodySwayPreviewProjectionError(
            "Body-sway projection requires exact preview inputs"
        )
    try:
        probe = inputs.probe_inputs
        report = inputs.report
        motion = probe.motion_instance_v2
        parameters = inputs.selection["parameters"]
        ticks = build_body_sway_sample_ticks(
            inputs.timing,
            motion["tracks"],
            cycles=parameters["cycles"],
            per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
        )
        _require_schedule(ticks, report)
        sampler = prepare_body_sway_sampler(
            inputs.timing,
            motion["tracks"],
            cycles=parameters["cycles"],
            per_bone_amplitude_deg=parameters["per_bone_amplitude_deg"],
            per_bone_phase_fraction=parameters["per_bone_phase_fraction"],
        )
        inventory = tuple(report["sample_stream"]["rotation_bone_ids"])
        _require_key_bounds(len(ticks), len(inventory))
        keys = {bone_id: [] for bone_id in inventory}
        for tick in ticks:
            sample = sampler.sample(tick)
            combined = dict(sample.combined_rotation_deg)
            if tuple(sorted(combined)) != inventory:
                raise BodySwayPreviewProjectionError(
                    "Projection rotation inventory differs from P10.2"
                )
            for bone_id in inventory:
                keys[bone_id].append({
                    "tick": tick, "value": combined[bone_id],
                })
        tracks = [
            {"bone_id": bone_id, "property": "rotation", "keys": keys[bone_id]}
            for bone_id in inventory
        ]
        document = {
            "domain": PROJECTION_DIGEST_DOMAIN,
            "compiler": body_sway_preview_compiler_profile(),
            "source": {
                "body_sway_probe_report_sha256": inputs.report_sha256,
                "base_motion_instance_v2_sha256":
                    report["source"]["p9"]["motion_instance_v2_sha256"],
            },
            "timing": inputs.timing,
            "selection": inputs.selection,
            "probe_tick_schedule_sha256":
                report["schedule"]["tick_schedule_sha256"],
            "probe_sample_stream_sha256":
                report["sample_stream"]["sample_stream_sha256"],
            "sample_ticks": list(ticks),
            "rotation_tracks": tracks,
            "summary": {
                "sample_count": len(ticks),
                "rotation_track_count": len(tracks),
                "rotation_key_count": len(ticks) * len(tracks),
            },
        }
        return BodySwayPreviewProjection(_canonical(document))
    except BodySwayPreviewProjectionError:
        raise
    except (
        BodySwayProbeMathError, KeyError, OverflowError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise BodySwayPreviewProjectionError(
            f"Body-sway preview projection failed: {exc}"
        ) from exc


def _require_schedule(ticks, report) -> None:
    if not 2 <= len(ticks) <= MAX_PREVIEW_SAMPLE_COUNT:
        raise BodySwayPreviewProjectionError(
            "Body-sway preview sample count exceeds the bounded profile"
        )
    schedule = report["schedule"]
    if len(ticks) != schedule["sample_count"] \
            or ticks[0] != schedule["first_tick"] \
            or ticks[-1] != schedule["last_tick"] \
            or tick_schedule_sha256(ticks) != schedule["tick_schedule_sha256"]:
        raise BodySwayPreviewProjectionError(
            "Body-sway preview schedule differs from P10.2 evidence"
        )


def _require_key_bounds(samples: int, tracks: int) -> None:
    if not 1 <= tracks <= MAX_ROTATION_TRACK_COUNT \
            or samples * tracks > MAX_ROTATION_KEY_COUNT:
        raise BodySwayPreviewProjectionError(
            "Body-sway preview rotation keys exceed the bounded profile"
        )


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
