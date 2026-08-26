"""Internal frozen sampled-linear projection for a temporary body-sway preview."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .body_sway_preview_inputs import BodySwayPreviewInputs
from .body_sway_preview_profile import (
    BASE_ANIMATION_DIGEST_DOMAIN,
    BASE_ANIMATION_NAME,
    COMBINED_ANIMATION_NAME,
    MAX_PREVIEW_SAMPLE_COUNT,
    MAX_ROTATION_KEY_COUNT,
    MAX_ROTATION_TRACK_COUNT,
    PROJECTION_DIGEST_DOMAIN,
    ROTATION_TIMELINE_DIGEST_DOMAIN,
    SETUP_DIGEST_DOMAIN,
    body_sway_preview_compiler_profile,
)
from .body_sway_probe_math import build_body_sway_sample_ticks
from .body_sway_probe_math_inputs import BodySwayProbeMathError
from .body_sway_probe_report_evidence import tick_schedule_sha256
from .body_sway_probe_sampler import prepare_body_sway_sampler
from .resolved_project import canonical_sha256
from .spine42_timeline_projection import project_spine42_motion
from .spine42_json_adapter import build_spine42_json


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
            "base_animation_sha256": document["base_animation_sha256"],
            "setup_sha256": document["setup_sha256"],
            "rotation_timeline_sha256":
                body_sway_preview_rotation_timeline_sha256(
                    document["rotation_tracks"]
                ),
            "sample_count": summary["sample_count"],
            "rotation_track_count": summary["rotation_track_count"],
            "rotation_key_count": summary["rotation_key_count"],
            "sample_ticks": document["sample_ticks"],
            "rotation_bone_ids": [
                row["bone_id"] for row in document["rotation_tracks"]
            ],
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


def body_sway_preview_rotation_timeline_sha256(
    rotation_tracks: list[dict[str, Any]],
) -> str:
    """Seal the exact sampled rotation tracks exposed by the Spine preview."""

    return canonical_sha256({
        "domain": ROTATION_TIMELINE_DIGEST_DOMAIN,
        "rotation_tracks": rotation_tracks,
    })


def body_sway_preview_base_animation_sha256(
    animation: dict[str, Any],
) -> str:
    """Seal the exact projected MIv2 animation inherited by both previews."""

    return canonical_sha256({
        "domain": BASE_ANIMATION_DIGEST_DOMAIN,
        "animation": animation,
    })


def body_sway_preview_setup_sha256(skeleton: dict[str, Any]) -> str:
    """Seal the exact static setup emitted by the fixed Spine adapter."""

    metadata = skeleton["skeleton"]
    return canonical_sha256({
        "domain": SETUP_DIGEST_DOMAIN,
        "setup": {
            "skeleton": {
                field: metadata[field]
                for field in ("spine", "x", "y", "width", "height")
            },
            "bones": skeleton["bones"],
            "slots": skeleton["slots"],
            "skins": skeleton["skins"],
        },
    })


def build_body_sway_preview_projection_document(
    *,
    project_id: str,
    clip_id: str,
    report_sha256: str,
    base_motion_instance_v2_sha256: str,
    base_animation_sha256: str,
    setup_sha256: str,
    timing: dict[str, Any],
    selection: dict[str, Any],
    tick_schedule_sha256_value: str,
    sample_stream_sha256: str,
    sample_ticks: list[int],
    rotation_tracks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the sole internal projection document for compile or replay."""

    return {
        "domain": PROJECTION_DIGEST_DOMAIN,
        "compiler": body_sway_preview_compiler_profile(),
        "project_id": project_id,
        "clip_id": clip_id,
        "source": {
            "body_sway_probe_report_sha256": report_sha256,
            "base_motion_instance_v2_sha256": base_motion_instance_v2_sha256,
        },
        "timing": timing,
        "selection": selection,
        "probe_tick_schedule_sha256": tick_schedule_sha256_value,
        "probe_sample_stream_sha256": sample_stream_sha256,
        "base_animation_sha256": base_animation_sha256,
        "setup_sha256": setup_sha256,
        "sample_ticks": sample_ticks,
        "rotation_tracks": rotation_tracks,
        "summary": {
            "sample_count": len(sample_ticks),
            "rotation_track_count": len(rotation_tracks),
            "rotation_key_count": len(sample_ticks) * len(rotation_tracks),
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
        setup = build_spine42_json(probe.rig)
        projected_slots = [
            {"name": slot["id"]}
            for slot in sorted(
                probe.rig["slots"],
                key=lambda item: (item["setup_draw_order"], item["id"]),
            )
        ]
        _events, base_animation = project_spine42_motion(
            motion, projected_slots
        )
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
        document = build_body_sway_preview_projection_document(
            project_id=inputs.project_id,
            clip_id=inputs.clip_id,
            report_sha256=inputs.report_sha256,
            base_motion_instance_v2_sha256=
                report["source"]["p9"]["motion_instance_v2_sha256"],
            base_animation_sha256=
                body_sway_preview_base_animation_sha256(base_animation),
            setup_sha256=body_sway_preview_setup_sha256(setup),
            timing=inputs.timing,
            selection=inputs.selection,
            tick_schedule_sha256_value=
                report["schedule"]["tick_schedule_sha256"],
            sample_stream_sha256=
                report["sample_stream"]["sample_stream_sha256"],
            sample_ticks=list(ticks),
            rotation_tracks=tracks,
        )
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
