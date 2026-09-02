"""Pure P10.6a v2 core compiled between current-head observations."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any

from .body_sway_dynamic_seam_bundle_reader_v2 import (
    VerifiedBodySwayDynamicSeamBundleV2,
)
from .body_sway_motion_consumer_profile_v2 import (
    CORE_FORMAT,
    CORE_FORMAT_VERSION,
    MAX_CORE_BYTES,
    SELECTED_GAIN,
    body_sway_base_channels_sha256_v2,
    body_sway_motion_consumer_profile_v2,
    body_sway_motion_consumer_release_gate_v2,
    body_sway_motion_domain_sha256_v2,
)
from .body_sway_motion_consumer_source_v2 import (
    AdmittedBodySwayMotionConsumerSourceV2,
    BodySwayMotionConsumerSourceV2Error,
    admit_body_sway_motion_consumer_source_v2,
)
from .body_sway_preview_projection_v2 import (
    body_sway_preview_rotation_timeline_sha256_v2,
)
from .body_sway_probe_report_evidence import tick_schedule_sha256
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .seam_anchor_review_json import canonical_json_bytes


CORE_FIELDS = {
    "format", "format_version", "project_id", "clip_id", "source",
    "motion_domain", "profile", "status", "release_gate", "summary",
}


class BodySwayMotionConsumerAdmissionV2Error(ValueError):
    """Raised when exact v2 evidence cannot admit a setup-local consumer."""


@dataclass(frozen=True, slots=True)
class BodySwayMotionConsumerAdmissionCoreV2:
    _canonical_json: str = field(repr=False)
    _head_identity_sha256: str = field(repr=False)
    _expected_head_json: str = field(repr=False)

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
    def head_identity_sha256(self) -> str:
        return self._head_identity_sha256

    @property
    def expected_head_observation(self) -> dict[str, Any]:
        return json.loads(self._expected_head_json)


def compile_body_sway_motion_consumer_admission_core_v2(
    dynamic_seam_bundle: VerifiedBodySwayDynamicSeamBundleV2,
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> BodySwayMotionConsumerAdmissionCoreV2:
    """Compile unit-gain setup-local channels without observing mutable heads."""

    try:
        admitted = admit_body_sway_motion_consumer_source_v2(
            dynamic_seam_bundle, reviewed_bundle,
        )
        return _compile_admitted_body_sway_motion_consumer_core_v2(admitted)
    except BodySwayMotionConsumerAdmissionV2Error:
        raise
    except (
        AttributeError, BodySwayMotionConsumerSourceV2Error, KeyError,
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayMotionConsumerAdmissionV2Error(
            f"Motion consumer v2 core compilation failed: {exc}"
        ) from exc


def _compile_admitted_body_sway_motion_consumer_core_v2(
    admitted: AdmittedBodySwayMotionConsumerSourceV2,
) -> BodySwayMotionConsumerAdmissionCoreV2:
    """Build the unchanged core bytes from one already-admitted source."""

    try:
        if type(admitted) is not AdmittedBodySwayMotionConsumerSourceV2:
            raise BodySwayMotionConsumerAdmissionV2Error(
                "Motion consumer v2 core requires an admitted source"
            )
        motion_domain = _build_motion_domain(
            admitted.motion_instance_v2,
            admitted.preview_projection_v2,
            admitted.source,
        )
        gate = body_sway_motion_consumer_release_gate_v2()
        document = {
            "format": CORE_FORMAT,
            "format_version": CORE_FORMAT_VERSION,
            "project_id": admitted.project_id,
            "clip_id": admitted.clip_id,
            "source": admitted.source,
            "motion_domain": motion_domain,
            "profile": body_sway_motion_consumer_profile_v2(),
            "status": "eligible_pending_compile_time_v2_head_seal",
            "release_gate": {
                "status": "blocked",
                "reason_codes": sorted([
                    *gate["reason_codes"],
                    "current_review_heads_not_yet_sealed",
                ]),
            },
            "summary": _summary(motion_domain),
        }
        encoded = canonical_json_bytes(document)
        if len(encoded) > MAX_CORE_BYTES:
            raise BodySwayMotionConsumerAdmissionV2Error(
                "Motion consumer v2 core exceeds its byte limit"
            )
        return BodySwayMotionConsumerAdmissionCoreV2(
            encoded.decode("utf-8"), admitted.head_identity_sha256,
            _canonical(admitted.expected_head_observation),
        )
    except BodySwayMotionConsumerAdmissionV2Error:
        raise
    except (
        AttributeError, BodySwayMotionConsumerSourceV2Error, KeyError,
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayMotionConsumerAdmissionV2Error(
            f"Motion consumer v2 core compilation failed: {exc}"
        ) from exc


def _build_motion_domain(motion, projection, source):
    ticks, tracks = projection["sample_ticks"], projection["rotation_tracks"]
    _require_rotation_domain(ticks, tracks, projection)
    if motion["timing"] != projection["timing"]:
        raise BodySwayMotionConsumerAdmissionV2Error(
            "Motion consumer v2 projection timing differs from exact MIv2"
        )
    root_tracks = [
        _copy(track) for track in motion["tracks"]
        if track["property"] == "translation"
    ]
    if len(root_tracks) > 1:
        raise BodySwayMotionConsumerAdmissionV2Error(
            "Motion consumer v2 found multiple root translation tracks"
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
    channels["base_channels_sha256"] = (
        body_sway_base_channels_sha256_v2(channels)
    )
    domain = {
        "coordinate_space": _copy(motion["target_space"]),
        "timing": _copy(motion["timing"]),
        "selected_gain": _copy(SELECTED_GAIN),
        "sample_ticks": _copy(ticks),
        "sample_schedule": {
            "sampling": "p10-preview-v2-probe-schedule",
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
            "projection_v2_sha256": source["preview_projection_v2_sha256"],
            "rotation_timeline_sha256":
                body_sway_preview_rotation_timeline_sha256_v2(tracks),
            "tracks": _copy(tracks),
        },
        "base_channels": channels,
    }
    domain["motion_domain_sha256"] = body_sway_motion_domain_sha256_v2(
        domain
    )
    return domain


def _require_rotation_domain(ticks, tracks, projection):
    if type(ticks) is not list or len(ticks) < 2 \
            or any(type(tick) is not int for tick in ticks) \
            or any(left >= right for left, right in zip(ticks, ticks[1:])):
        raise BodySwayMotionConsumerAdmissionV2Error(
            "Motion consumer v2 sample ticks are invalid"
        )
    if tick_schedule_sha256(tuple(ticks)) \
            != projection["probe_tick_schedule_sha256"]:
        raise BodySwayMotionConsumerAdmissionV2Error(
            "Motion consumer v2 sample schedule digest is inconsistent"
        )
    if type(tracks) is not list or not tracks:
        raise BodySwayMotionConsumerAdmissionV2Error(
            "Motion consumer v2 rotation timeline is empty"
        )
    previous = None
    for track in tracks:
        if type(track) is not dict or set(track) != {
            "bone_id", "property", "keys"
        } or type(track.get("bone_id")) is not str \
                or track.get("property") != "rotation" \
                or previous is not None and track["bone_id"] <= previous:
            raise BodySwayMotionConsumerAdmissionV2Error(
                "Motion consumer v2 rotation track inventory is invalid"
            )
        keys = track["keys"]
        if type(keys) is not list or len(keys) != len(ticks):
            raise BodySwayMotionConsumerAdmissionV2Error(
                "Motion consumer v2 rotation key inventory is invalid"
            )
        for tick, key in zip(ticks, keys, strict=True):
            value = key.get("value") if type(key) is dict else None
            if type(key) is not dict or set(key) != {"tick", "value"} \
                    or key.get("tick") != tick or isinstance(value, bool) \
                    or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)):
                raise BodySwayMotionConsumerAdmissionV2Error(
                    "Motion consumer v2 rotation key is invalid"
                )
        previous = track["bone_id"]
    if projection["summary"] != {
        "sample_count": len(ticks),
        "rotation_track_count": len(tracks),
        "rotation_key_count": len(ticks) * len(tracks),
    }:
        raise BodySwayMotionConsumerAdmissionV2Error(
            "Motion consumer v2 projection summary is inconsistent"
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


def _copy(value):
    return json.loads(_canonical(value))


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


__all__ = [
    "BodySwayMotionConsumerAdmissionCoreV2",
    "BodySwayMotionConsumerAdmissionV2Error", "CORE_FIELDS",
    "compile_body_sway_motion_consumer_admission_core_v2",
]
