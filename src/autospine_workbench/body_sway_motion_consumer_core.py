"""Pure frozen P10.6a core compiled between two current-head checks."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any

from .body_sway_dynamic_seam_head_checks import (
    BodySwayDynamicSeamHeadIdentity,
)
from .body_sway_motion_consumer_profile import (
    CORE_FORMAT,
    CORE_FORMAT_VERSION,
    MAX_CORE_BYTES,
    SELECTED_GAIN,
    body_sway_base_channels_sha256,
    body_sway_motion_consumer_profile,
    body_sway_motion_consumer_release_gate,
    body_sway_motion_domain_sha256,
)
from .body_sway_motion_consumer_source import (
    BodySwayMotionConsumerSourceError,
    admit_body_sway_motion_consumer_source,
)
from .body_sway_preview_projection import (
    body_sway_preview_rotation_timeline_sha256,
)
from .body_sway_probe_report_evidence import tick_schedule_sha256
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .seam_anchor_review_json import canonical_json_bytes


CORE_FIELDS = {
    "format", "format_version", "project_id", "clip_id", "source",
    "motion_domain", "profile", "status", "release_gate", "summary",
}


class BodySwayMotionConsumerAdmissionError(ValueError):
    """Raised when exact evidence cannot admit a setup-local consumer."""


@dataclass(frozen=True, slots=True)
class BodySwayMotionConsumerAdmissionCore:
    """Frozen path-free value safe to carry between head observations."""

    _canonical_json: str = field(repr=False)
    _head_identity: BodySwayDynamicSeamHeadIdentity = field(repr=False)

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
    def head_identity(self) -> BodySwayDynamicSeamHeadIdentity:
        return self._head_identity


def compile_body_sway_motion_consumer_admission_core(
    dynamic_seam_probe: Any,
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> BodySwayMotionConsumerAdmissionCore:
    """Compile exact unit-gain channels without observing mutable heads."""

    try:
        admitted = admit_body_sway_motion_consumer_source(
            dynamic_seam_probe, reviewed_bundle
        )
        motion_domain = _build_motion_domain(
            admitted.motion_instance_v2, admitted.preview_projection,
            admitted.source,
        )
        summary = _summary(motion_domain)
        gate = body_sway_motion_consumer_release_gate()
        document = {
            "format": CORE_FORMAT,
            "format_version": CORE_FORMAT_VERSION,
            "project_id": admitted.project_id,
            "clip_id": admitted.clip_id,
            "source": admitted.source,
            "motion_domain": motion_domain,
            "profile": body_sway_motion_consumer_profile(),
            "status": "eligible_pending_compile_time_head_seal",
            "release_gate": {
                "status": "blocked",
                "reason_codes": sorted([
                    *gate["reason_codes"],
                    "current_review_heads_not_yet_sealed",
                ]),
            },
            "summary": summary,
        }
        encoded = canonical_json_bytes(document)
        if len(encoded) > MAX_CORE_BYTES:
            raise BodySwayMotionConsumerAdmissionError(
                "Motion consumer core exceeds its byte limit"
            )
        return BodySwayMotionConsumerAdmissionCore(
            encoded.decode("utf-8"), admitted.head_identity
        )
    except BodySwayMotionConsumerAdmissionError:
        raise
    except (
        AttributeError, BodySwayMotionConsumerSourceError, KeyError,
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayMotionConsumerAdmissionError(
            f"Motion consumer core compilation failed: {exc}"
        ) from exc


def _build_motion_domain(motion, projection, source):
    ticks = projection["sample_ticks"]
    tracks = projection["rotation_tracks"]
    _require_rotation_domain(ticks, tracks, projection)
    if motion["timing"] != projection["timing"]:
        raise BodySwayMotionConsumerAdmissionError(
            "Motion consumer projection timing differs from exact MIv2"
        )
    root_tracks = [
        _copy(track) for track in motion["tracks"]
        if track["property"] == "translation"
    ]
    if len(root_tracks) > 1:
        raise BodySwayMotionConsumerAdmissionError(
            "Motion consumer found multiple root translation tracks"
        )
    channels = {
        "motion_instance_v2_sha256": source["p9"][
            "motion_instance_v2_sha256"
        ],
        "root_translation": {
            "mode": "exact-motion-instance-v2-linear",
            "tracks": root_tracks,
        },
        "markers": {
            "mode": "exact-motion-instance-v2",
            "items": _copy(motion["markers"]),
        },
        "draw_order": {
            "mode": "exact-motion-instance-v2-stepped",
            "value": _copy(motion["draw_order"]),
        },
    }
    channels["base_channels_sha256"] = body_sway_base_channels_sha256(
        channels
    )
    domain = {
        "coordinate_space": _copy(motion["target_space"]),
        "timing": _copy(motion["timing"]),
        "selected_gain": _copy(SELECTED_GAIN),
        "sample_ticks": _copy(ticks),
        "sample_schedule": {
            "sampling": "p10-probe-schedule",
            "probe_tick_schedule_sha256": projection[
                "probe_tick_schedule_sha256"
            ],
            "probe_sample_stream_sha256": projection[
                "probe_sample_stream_sha256"
            ],
            "sample_count": len(ticks),
            "first_tick": ticks[0],
            "last_tick": ticks[-1],
        },
        "rotation_timeline": {
            "interpolation": "sampled-linear",
            "projection_sha256": source["preview_projection_sha256"],
            "rotation_timeline_sha256":
                body_sway_preview_rotation_timeline_sha256(tracks),
            "tracks": _copy(tracks),
        },
        "base_channels": channels,
    }
    domain["motion_domain_sha256"] = body_sway_motion_domain_sha256(domain)
    return domain


def _require_rotation_domain(ticks, tracks, projection) -> None:
    if type(ticks) is not list or len(ticks) < 2 \
            or any(type(tick) is not int for tick in ticks) \
            or any(left >= right for left, right in zip(ticks, ticks[1:])):
        raise BodySwayMotionConsumerAdmissionError(
            "Motion consumer sample ticks are invalid"
        )
    if tick_schedule_sha256(tuple(ticks)) \
            != projection["probe_tick_schedule_sha256"]:
        raise BodySwayMotionConsumerAdmissionError(
            "Motion consumer sample schedule digest is inconsistent"
        )
    if type(tracks) is not list or not tracks:
        raise BodySwayMotionConsumerAdmissionError(
            "Motion consumer rotation timeline is empty"
        )
    previous = None
    for track in tracks:
        if type(track) is not dict or set(track) != {
            "bone_id", "property", "keys"
        } or type(track.get("bone_id")) is not str \
                or track.get("property") != "rotation" \
                or previous is not None and track["bone_id"] <= previous:
            raise BodySwayMotionConsumerAdmissionError(
                "Motion consumer rotation track inventory is invalid"
            )
        keys = track["keys"]
        if type(keys) is not list or len(keys) != len(ticks):
            raise BodySwayMotionConsumerAdmissionError(
                "Motion consumer rotation key inventory is invalid"
            )
        for tick, key in zip(ticks, keys, strict=True):
            value = key.get("value") if type(key) is dict else None
            if type(key) is not dict or set(key) != {"tick", "value"} \
                    or key.get("tick") != tick or isinstance(value, bool) \
                    or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)):
                raise BodySwayMotionConsumerAdmissionError(
                    "Motion consumer rotation key is invalid"
                )
        previous = track["bone_id"]
    summary = projection["summary"]
    if summary != {
        "sample_count": len(ticks),
        "rotation_track_count": len(tracks),
        "rotation_key_count": len(ticks) * len(tracks),
    }:
        raise BodySwayMotionConsumerAdmissionError(
            "Motion consumer projection summary is inconsistent"
        )


def _summary(domain):
    tracks = domain["rotation_timeline"]["tracks"]
    roots = domain["base_channels"]["root_translation"]["tracks"]
    draw_keys = domain["base_channels"]["draw_order"]["value"]["keys"]
    return {
        "sample_count": len(domain["sample_ticks"]),
        "rotation_track_count": len(tracks),
        "rotation_key_count": sum(len(track["keys"]) for track in tracks),
        "root_translation_track_count": len(roots),
        "root_translation_key_count": sum(len(track["keys"]) for track in roots),
        "marker_count": len(domain["base_channels"]["markers"]["items"]),
        "draw_order_key_count": len(draw_keys),
    }


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))
