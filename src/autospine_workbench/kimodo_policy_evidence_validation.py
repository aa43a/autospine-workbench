"""Strict semantic contract for candidate-free Kimodo policy evidence."""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any

from .kimodo_policy_evidence_arrays import extract_kimodo_policy_arrays
from .kimodo_policy_signal_validation import (
    require_policy_array_profile,
    require_policy_signals,
)
from .motion_bundle_integrity import VerifiedMotionBundle
from .projected_motion_bundle_integrity import VerifiedProjectedMotionBundle


FORMAT = "autospine-kimodo-policy-evidence"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOP = {
    "format", "format_version", "clip_id", "source", "array_profile",
    "timing", "policy", "signals",
}
_SOURCE = {
    "p7_motion_ir_sha256", "p7_bundle_sha256", "p7_run_sha256",
    "raw_npz_sha256", "kimodo_source_sha256", "kimodo_map_sha256",
    "array_inventory_sha256", "p8_projected_motion_sha256",
    "p8_bundle_sha256", "p8_run_sha256", "camera_sha256",
    "legacy_motion_ir_sha256",
}
_POLICY = {
    "mode": "evidence_only",
    "candidate_emitted": False,
    "decision_emitted": False,
    "runtime_timeline_emitted": False,
    "missing_signal_policy": "explicit_unavailable_no_inference",
    "contact_reduction": "none_per_channel_preserved",
    "heading_axis_interpretation": "deferred_to_reviewed_policy_map",
}
class KimodoPolicyEvidenceValidationError(ValueError):
    """Raised when Kimodo ancillary evidence is ambiguous or inconsistent."""


def require_kimodo_policy_evidence(
    document: Mapping[str, Any],
    *,
    p7_bundle: VerifiedMotionBundle | None = None,
    p8_bundle: VerifiedProjectedMotionBundle | None = None,
) -> None:
    """Validate standalone evidence and optional exact upstream bindings."""

    try:
        root = _object(document, "Kimodo policy evidence")
        _exact(root, _TOP, "Kimodo policy evidence")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise KimodoPolicyEvidenceValidationError(
                "Kimodo policy evidence format is unsupported"
            )
        _identifier(root.get("clip_id"), "clip_id")
        source = _source(root.get("source"))
        profile = require_policy_array_profile(root.get("array_profile"))
        frame_count = _timing(root.get("timing"))
        if root.get("policy") != _POLICY:
            raise KimodoPolicyEvidenceValidationError(
                "Kimodo policy evidence mode is not evidence-only"
            )
        require_policy_signals(root.get("signals"), profile, frame_count)
        supplied = (p7_bundle, p8_bundle)
        if any(value is not None for value in supplied):
            if not all(value is not None for value in supplied):
                raise KimodoPolicyEvidenceValidationError(
                    "P7 and P8 bundles must be supplied together"
                )
            _cross_bundles(root, source, p7_bundle, p8_bundle)
        encoded = json.dumps(
            dict(root), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise KimodoPolicyEvidenceValidationError(
                "Kimodo policy evidence byte limit exceeded"
            )
    except KimodoPolicyEvidenceValidationError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise KimodoPolicyEvidenceValidationError(
            f"Kimodo policy evidence validation failed: {exc}"
        ) from exc


def evidence_only_policy() -> dict[str, Any]:
    return dict(_POLICY)


def _source(value: Any) -> Mapping[str, Any]:
    source = _object(value, "Kimodo policy evidence source")
    _exact(source, _SOURCE, "Kimodo policy evidence source")
    for field in _SOURCE:
        if not isinstance(source.get(field), str) \
                or not _SHA.fullmatch(source[field]):
            raise KimodoPolicyEvidenceValidationError(
                f"Kimodo policy evidence {field} is invalid"
            )
    if source["legacy_motion_ir_sha256"] != source["p7_motion_ir_sha256"]:
        raise KimodoPolicyEvidenceValidationError(
            "Kimodo legacy and P7 MotionIR identities differ"
        )
    return source


def _timing(value: Any) -> int:
    timing = _object(value, "Kimodo policy timing")
    _exact(
        timing,
        {"ticks_per_second", "duration_ticks", "frame_count", "loop", "frames"},
        "Kimodo policy timing",
    )
    count, duration = timing.get("frame_count"), timing.get("duration_ticks")
    if timing.get("ticks_per_second") != 1_000_000 \
            or type(count) is not int or not 2 <= count <= 4096 \
            or type(duration) is not int or duration <= 0 \
            or type(timing.get("loop")) is not bool:
        raise KimodoPolicyEvidenceValidationError(
            "Kimodo policy timing values are invalid"
        )
    frames = _array(timing.get("frames"), "Kimodo policy frames")
    if len(frames) != count:
        raise KimodoPolicyEvidenceValidationError(
            "Kimodo policy frame count differs from timing"
        )
    ticks = []
    for index, raw in enumerate(frames):
        frame = _object(raw, "Kimodo policy frame")
        _exact(frame, {"source_frame_index", "tick"}, "Kimodo policy frame")
        tick = frame.get("tick")
        if frame.get("source_frame_index") != index \
                or type(tick) is not int or tick < 0:
            raise KimodoPolicyEvidenceValidationError(
                "Kimodo policy frame identity is invalid"
            )
        ticks.append(tick)
    if ticks[0] != 0 or ticks[-1] != duration \
            or any(right <= left for left, right in zip(ticks, ticks[1:])):
        raise KimodoPolicyEvidenceValidationError(
            "Kimodo policy frame ticks are not canonical"
        )
    return count


def _cross_bundles(root, source, p7, p8) -> None:
    if type(p7) is not VerifiedMotionBundle or p7.source_kind != "kimodo_npz" \
            or type(p8) is not VerifiedProjectedMotionBundle:
        raise KimodoPolicyEvidenceValidationError(
            "Kimodo policy evidence cross-check requires exact P7/P8 bundles"
        )
    run_source = p7.run_manifest["source"]
    expected = {
        "p7_motion_ir_sha256": p7.clip_sha256,
        "p7_bundle_sha256": p7.bundle_sha256,
        "p7_run_sha256": p7.run_sha256,
        "raw_npz_sha256": run_source["raw_npz_sha256"],
        "kimodo_source_sha256": run_source["source_sha256"],
        "kimodo_map_sha256": run_source["map_sha256"],
        "array_inventory_sha256": run_source["array_inventory_sha256"],
        "p8_projected_motion_sha256": p8.projected_motion_sha256,
        "p8_bundle_sha256": p8.bundle_sha256,
        "p8_run_sha256": p8.run_sha256,
        "camera_sha256": p8.camera_sha256,
        "legacy_motion_ir_sha256": p8.legacy_motion_sha256,
    }
    upstream = p8.projected_motion["source"]
    if root["clip_id"] != p7.clip_id or source != expected \
            or p8.clip_id != p7.clip_id \
            or p8.p7_motion_sha256 != p7.clip_sha256 \
            or p8.p7_bundle_sha256 != p7.bundle_sha256 \
            or p8.p7_run_sha256 != p7.run_sha256 \
            or upstream["motion_bundle_sha256"] != p7.bundle_sha256:
        raise KimodoPolicyEvidenceValidationError(
            "Kimodo policy evidence P7/P8 bindings differ"
        )
    raw, sidecar = p7.raw_npz, p7.kimodo_source
    if raw is None or sidecar is None:
        raise KimodoPolicyEvidenceValidationError(
            "Kimodo policy evidence exact NPZ inputs are unavailable"
        )
    profile, signals = extract_kimodo_policy_arrays(raw, sidecar)
    projected = p8.projected_motion
    expected_timing = dict(projected["timing"])
    expected_timing["frames"] = projected["frames"]
    if root["array_profile"] != profile or root["signals"] != signals \
            or root["timing"] != expected_timing:
        raise KimodoPolicyEvidenceValidationError(
            "Kimodo policy evidence differs from exact ancillary arrays"
        )


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128 \
            or not value[0].isalnum() \
            or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
                   for char in value):
        raise KimodoPolicyEvidenceValidationError(
            f"Kimodo policy evidence {label} is invalid"
        )
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KimodoPolicyEvidenceValidationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise KimodoPolicyEvidenceValidationError(f"{label} must be an array")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise KimodoPolicyEvidenceValidationError(
            f"{label} fields are incomplete or unsupported"
        )
