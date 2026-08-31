"""Capture-framed v2 domain around the unchanged v1 preview mathematics."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .body_sway_preview_inputs_v2 import BodySwayPreviewInputsV2
from .body_sway_preview_profile_v2 import (
    BASE_ANIMATION_DIGEST_DOMAIN,
    BASE_ANIMATION_NAME,
    COMBINED_ANIMATION_NAME,
    PREVIEW_SEMANTICS,
    PROJECTION_DIGEST_DOMAIN,
    ROTATION_TIMELINE_DIGEST_DOMAIN,
    SETUP_DIGEST_DOMAIN,
    body_sway_preview_compiler_profile_v2,
)
from .body_sway_preview_projection import (
    BodySwayPreviewProjectionError,
    compile_body_sway_preview_projection,
)
from .resolved_project import canonical_sha256
from .spine42_json_adapter import build_spine42_json
from .spine42_timeline_projection import project_spine42_motion


class BodySwayPreviewProjectionV2Error(ValueError):
    """Raised when admitted v2 framing cannot seal the legacy projection."""


@dataclass(frozen=True, slots=True)
class BodySwayPreviewProjectionV2:
    """Internal v2 projection; no persistent motion authority is implied."""

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
        framing = document["capture_framing"]
        return {
            "projection_sha256": self.sha256,
            "legacy_projection_sha256":
                document["legacy_projection_sha256"],
            "probe_tick_schedule_sha256":
                document["probe_tick_schedule_sha256"],
            "probe_sample_stream_sha256":
                document["probe_sample_stream_sha256"],
            "base_motion_instance_v2_sha256":
                document["source"]["base_motion_instance_v2_sha256"],
            "capture_framing_candidate_sha256":
                document["source"]["capture_framing_candidate_sha256"],
            "capture_framing_decision_sha256":
                document["source"]["capture_framing_decision_sha256"],
            "capture_framing_revision": framing["revision"],
            "world_viewport": dict(framing["world_viewport"]),
            "framing_mode": "human-reviewed-capture-framing",
            "base_animation_sha256": document["base_animation_sha256"],
            "setup_sha256": document["setup_sha256"],
            "rotation_timeline_sha256":
                body_sway_preview_rotation_timeline_sha256_v2(
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


def body_sway_preview_rotation_timeline_sha256_v2(rotation_tracks):
    return canonical_sha256({
        "domain": ROTATION_TIMELINE_DIGEST_DOMAIN,
        "rotation_tracks": rotation_tracks,
    })


def body_sway_preview_base_animation_sha256_v2(animation):
    return canonical_sha256({
        "domain": BASE_ANIMATION_DIGEST_DOMAIN,
        "animation": animation,
    })


def body_sway_preview_setup_sha256_v2(skeleton):
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


def build_body_sway_preview_projection_document_v2(
    *, project_id, clip_id, report_sha256,
    base_motion_instance_v2_sha256, capture_framing_candidate_sha256,
    capture_framing_decision_sha256, capture_framing_revision,
    world_viewport, legacy_projection_sha256, base_animation_sha256,
    setup_sha256, timing, selection, tick_schedule_sha256_value,
    sample_stream_sha256, sample_ticks, rotation_tracks,
):
    """Build the sole detached v2 projection document."""

    return {
        "domain": PROJECTION_DIGEST_DOMAIN,
        "compiler": body_sway_preview_compiler_profile_v2(),
        "semantics": dict(PREVIEW_SEMANTICS),
        "project_id": project_id,
        "clip_id": clip_id,
        "source": {
            "body_sway_probe_report_sha256": report_sha256,
            "base_motion_instance_v2_sha256":
                base_motion_instance_v2_sha256,
            "capture_framing_candidate_sha256":
                capture_framing_candidate_sha256,
            "capture_framing_decision_sha256":
                capture_framing_decision_sha256,
        },
        "capture_framing": {
            "revision": capture_framing_revision,
            "world_viewport": dict(world_viewport),
            "coordinate_space": "spine-world-bottom-left-y-up",
        },
        "legacy_projection_sha256": legacy_projection_sha256,
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


def compile_body_sway_preview_projection_v2(
    inputs: BodySwayPreviewInputsV2,
) -> BodySwayPreviewProjectionV2:
    """Reuse the v1 sampler exactly, then seal it in the reviewed v2 frame."""

    if type(inputs) is not BodySwayPreviewInputsV2:
        raise BodySwayPreviewProjectionV2Error(
            "Body-sway projection v2 requires exact preview inputs v2"
        )
    try:
        legacy = compile_body_sway_preview_projection(
            inputs.legacy_projection_inputs()
        )
        probe = inputs.probe_inputs
        motion = probe.motion_instance_v2
        setup = build_spine42_json(probe.rig)
        _apply_world_viewport(setup, inputs.world_viewport)
        slots = [
            {"name": row["id"]}
            for row in sorted(
                probe.rig["slots"],
                key=lambda row: (row["setup_draw_order"], row["id"]),
            )
        ]
        _events, base_animation = project_spine42_motion(motion, slots)
        document = build_body_sway_preview_projection_document_v2(
            project_id=inputs.project_id, clip_id=inputs.clip_id,
            report_sha256=inputs.report_sha256,
            base_motion_instance_v2_sha256=
                inputs.source["p9"]["motion_instance_v2_sha256"],
            capture_framing_candidate_sha256=
                inputs.framing_candidate_sha256,
            capture_framing_decision_sha256=
                inputs.framing_decision_sha256,
            capture_framing_revision=inputs.framing_revision,
            world_viewport=inputs.world_viewport,
            legacy_projection_sha256=legacy.sha256,
            base_animation_sha256=
                body_sway_preview_base_animation_sha256_v2(base_animation),
            setup_sha256=body_sway_preview_setup_sha256_v2(setup),
            timing=inputs.timing, selection=inputs.selection,
            tick_schedule_sha256_value=
                inputs.report["schedule"]["tick_schedule_sha256"],
            sample_stream_sha256=
                inputs.report["sample_stream"]["sample_stream_sha256"],
            sample_ticks=list(legacy.sample_ticks),
            rotation_tracks=legacy.rotation_tracks,
        )
        return BodySwayPreviewProjectionV2(_canonical(document))
    except BodySwayPreviewProjectionV2Error:
        raise
    except (
        BodySwayPreviewProjectionError, KeyError, OverflowError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayPreviewProjectionV2Error(
            f"Body-sway preview projection v2 failed: {exc}"
        ) from exc


def _apply_world_viewport(skeleton, viewport):
    metadata = skeleton["skeleton"]
    metadata.update({
        "x": viewport["x"], "y": viewport["y"],
        "width": viewport["width"], "height": viewport["height"],
    })


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
