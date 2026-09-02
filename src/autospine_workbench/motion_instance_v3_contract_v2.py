"""Version-isolated P10.6a v2 materialization into MotionInstance v3."""

from __future__ import annotations

from fractions import Fraction
import json
from typing import Any

from .body_sway_motion_consumer_profile_v2 import (
    FORMAT_VERSION as ADMISSION_FORMAT_VERSION,
    body_sway_base_channels_sha256_v2,
    body_sway_motion_domain_sha256_v2,
)
from .body_sway_preview_projection_v2 import (
    body_sway_preview_rotation_timeline_sha256_v2,
)
from .body_sway_probe_math import quantize_body_sway_number
from .motion_instance_v3_contract import (
    FORMAT,
    FORMAT_VERSION,
    OVERLAY_ROTATION_BONE_IDS,
    motion_instance_v3_profile,
    motion_instance_v3_profile_sha256,
)


class MotionInstanceV3V2ContractError(ValueError):
    """Raised when a P10.6a v2 source cannot form the frozen v3 payload."""


def build_motion_instance_v3_document_v2(
    admission: dict[str, Any],
    motion_instance_v2: dict[str, Any],
    *,
    admission_sha256: str,
    p9_bundle_sha256: str,
) -> dict[str, Any]:
    """Materialize v2-admitted channels without changing payload version."""

    try:
        domain = admission["motion_domain"]
        source = admission["source"]
        timeline = domain["rotation_timeline"]
        channels = domain["base_channels"]
        _require_exact_chain(
            admission, motion_instance_v2, domain, source, timeline,
            channels, p9_bundle_sha256,
        )
        _require_rotation_overlay_boundary(
            motion_instance_v2, domain["sample_ticks"], timeline["tracks"],
        )
        tracks = _copy(timeline["tracks"])
        tracks.extend(_copy(channels["root_translation"]["tracks"]))
        tracks.sort(key=lambda item: (item["bone_id"], item["property"]))
        return {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "clip_id": admission["clip_id"],
            "timing": _copy(domain["timing"]),
            "source": {
                "body_sway_motion_consumer_admission_sha256":
                    admission_sha256,
                "p9": {
                    "motion_instance_v2_sha256": source["p9"][
                        "motion_instance_v2_sha256"
                    ],
                    "bundle_sha256": p9_bundle_sha256,
                },
                "motion_domain_sha256": domain["motion_domain_sha256"],
                "rotation_timeline_sha256": timeline[
                    "rotation_timeline_sha256"
                ],
                "base_channels_sha256": channels[
                    "base_channels_sha256"
                ],
                "rig_ir_sha256": source["p3_rig_sha256"],
                "target_profile_sha256": source["target_profile_sha256"],
                "motion_instance_v3_profile_sha256":
                    motion_instance_v3_profile_sha256(),
            },
            "profile": motion_instance_v3_profile(),
            "target_space": _copy(domain["coordinate_space"]),
            "tracks": tracks,
            "markers": _copy(channels["markers"]["items"]),
            "draw_order": _copy(channels["draw_order"]["value"]),
        }
    except MotionInstanceV3V2ContractError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise MotionInstanceV3V2ContractError(
            f"MotionInstance v3 v2 materialization failed: {exc}"
        ) from exc


def _require_exact_chain(
    admission, motion, domain, source, timeline, channels, bundle_sha256,
) -> None:
    p9 = source["p9"]
    motion_source = motion["source"]
    if admission.get("format_version") != ADMISSION_FORMAT_VERSION:
        raise MotionInstanceV3V2ContractError(
            "MotionInstance v3 v2 requires a P10.6a v2 admission"
        )
    if admission["clip_id"] != motion["clip_id"] \
            or domain["timing"] != motion["timing"] \
            or domain["coordinate_space"] != motion["target_space"]:
        raise MotionInstanceV3V2ContractError(
            "P10.6a v2 clip, timing, or target space differs from exact MIv2"
        )
    if p9["motion_instance_v2_sha256"] \
            != channels["motion_instance_v2_sha256"] \
            or p9["bundle_sha256"] != bundle_sha256:
        raise MotionInstanceV3V2ContractError(
            "P10.6a v2 base-channel identity differs from exact P9"
        )
    if source["p3_rig_sha256"] != motion_source["p3_rig_sha256"] \
            or source["target_profile_sha256"] \
            != motion_source["target_profile_sha256"]:
        raise MotionInstanceV3V2ContractError(
            "P10.6a v2 rig or target identity differs from exact MIv2"
        )
    expected_channels = _exact_base_channels(motion, p9)
    if channels != expected_channels:
        raise MotionInstanceV3V2ContractError(
            "P10.6a v2 base channels differ from exact MIv2"
        )
    if domain["selected_gain"] != {"numerator": 1, "denominator": 1} \
            or timeline["interpolation"] != "sampled-linear" \
            or domain["coordinate_space"].get("interpolation") != "linear":
        raise MotionInstanceV3V2ContractError(
            "P10.6a v2 sampling or target interpolation is unsupported"
        )
    if body_sway_preview_rotation_timeline_sha256_v2(
        timeline["tracks"]
    ) != timeline["rotation_timeline_sha256"] \
            or body_sway_motion_domain_sha256_v2(domain) \
            != domain["motion_domain_sha256"]:
        raise MotionInstanceV3V2ContractError(
            "P10.6a v2 motion-domain identity is inconsistent"
        )


def _exact_base_channels(motion, p9):
    channels = {
        "motion_instance_v2_sha256": p9["motion_instance_v2_sha256"],
        "root_translation": {
            "mode": "exact-motion-instance-v2-linear",
            "tracks": [
                _copy(track) for track in motion["tracks"]
                if track["property"] == "translation"
            ],
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
    return channels


def _require_rotation_overlay_boundary(motion, sample_ticks, tracks) -> None:
    base = {
        track["bone_id"]: track["keys"] for track in motion["tracks"]
        if track["property"] == "rotation"
    }
    projected = {track["bone_id"]: track["keys"] for track in tracks}
    base_ids, projected_ids = set(base), set(projected)
    allowed = set(OVERLAY_ROTATION_BONE_IDS)
    if not base_ids <= projected_ids or not projected_ids - base_ids <= allowed:
        raise MotionInstanceV3V2ContractError(
            "Rotation timeline must retain MIv2 and add only torso overlays"
        )
    for bone_id in sorted(base_ids - allowed):
        keys = projected[bone_id]
        if len(keys) != len(sample_ticks):
            raise MotionInstanceV3V2ContractError(
                "Rotation timeline does not match its sample schedule"
            )
        for tick, key in zip(sample_ticks, keys, strict=True):
            expected = quantize_body_sway_number(
                _sample_rotation(base[bone_id], tick)
            )
            if key.get("tick") != tick or key.get("value") != expected:
                raise MotionInstanceV3V2ContractError(
                    "A non-torso rotation differs from exact MIv2 sampling"
                )


def _sample_rotation(keys, tick: int) -> float:
    for index, right in enumerate(keys):
        right_tick = right["tick"]
        if right_tick == tick:
            return float(right["value"])
        if right_tick > tick and index:
            left = keys[index - 1]
            ratio = float(Fraction(
                tick - left["tick"], right_tick - left["tick"]
            ))
            start, end = float(left["value"]), float(right["value"])
            return start + (end - start) * ratio
    raise MotionInstanceV3V2ContractError(
        "Rotation sample tick is outside the exact MIv2 track"
    )


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


__all__ = [
    "MotionInstanceV3V2ContractError",
    "build_motion_instance_v3_document_v2",
]
