"""Strict standalone validation for reviewed runtime policy timelines."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
from typing import Any

from .resolved_project import canonical_sha256


FORMAT = "autospine-reviewed-motion-policy"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
MAX_NUMBER = 1_000_000_000_000.0
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "timing", "semantics", "root_correction_keys", "slot_order",
}
_P8 = {
    "projected_motion_sha256", "bundle_sha256", "camera_sha256",
    "run_sha256", "legacy_motion_sha256", "p7_motion_sha256",
    "p7_bundle_sha256", "p7_run_sha256",
}
_P5 = {
    "target_profile_sha256", "instance_sha256", "run_sha256",
    "retarget_report_sha256", "mesh_regression_sha256", "bundle_sha256",
}
_P3 = {
    "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
    "resolved_project_sha256", "rig_sha256", "run_sha256",
    "probes_sha256", "visuals_sha256", "bundle_sha256",
}
SEMANTICS = {
    "root_correction": "additive-target-root-translation",
    "root_unit": "pixel",
    "root_interpolation": "linear",
    "slot_order": "full-back-to-front-permutation",
    "slot_interpolation": "stepped",
    "attachment_switching": False,
    "raster_truth_claimed": False,
}


class ReviewedMotionPolicyValidationError(ValueError):
    """Raised when a reviewed motion policy is ambiguous or unsafe."""


def require_reviewed_motion_policy(document: Mapping[str, Any]) -> None:
    """Require the complete standalone ReviewedMotionPolicy v1 contract."""

    try:
        root = _object(document, "Reviewed motion policy")
        _exact(root, _TOP, "Reviewed motion policy")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise ReviewedMotionPolicyValidationError(
                "Reviewed motion policy format is unsupported"
            )
        _identifier(root.get("project_id"), "project_id")
        _identifier(root.get("clip_id"), "clip_id")
        _source(root.get("source"))
        duration, loop = _timing(root.get("timing"))
        if root.get("semantics") != SEMANTICS:
            raise ReviewedMotionPolicyValidationError(
                "Reviewed motion policy semantics are unsupported"
            )
        _root_keys(root.get("root_correction_keys"), duration, loop)
        _slot_order(root.get("slot_order"), duration, loop)
        encoded = json.dumps(
            dict(root), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise ReviewedMotionPolicyValidationError(
                "Reviewed motion policy byte limit exceeded"
            )
    except ReviewedMotionPolicyValidationError:
        raise
    except (KeyError, OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise ReviewedMotionPolicyValidationError(
            f"Reviewed motion policy validation failed: {exc}"
        ) from exc


def reviewed_motion_policy_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical digest only after strict standalone validation."""

    require_reviewed_motion_policy(document)
    return canonical_sha256(document)


def _source(value: Any) -> None:
    source = _object(value, "Reviewed motion policy source")
    _exact(
        source,
        {
            "motion_policy_decision_sha256", "foot_lock_candidates_sha256",
            "depth_order_candidates_sha256", "depth_pair_policy_sha256",
            "p8", "p5", "p3",
        },
        "Reviewed motion policy source",
    )
    for field in (
        "motion_policy_decision_sha256", "foot_lock_candidates_sha256",
        "depth_order_candidates_sha256", "depth_pair_policy_sha256",
    ):
        _digest(source.get(field), field)
    for stage, fields in (("p8", _P8), ("p5", _P5), ("p3", _P3)):
        row = _object(source.get(stage), f"Reviewed motion policy {stage} source")
        _exact(row, fields, f"Reviewed motion policy {stage} source")
        for field in fields:
            _digest(row.get(field), f"{stage}.{field}")


def _timing(value: Any) -> tuple[int, bool]:
    timing = _object(value, "Reviewed motion policy timing")
    _exact(
        timing,
        {"ticks_per_second", "duration_ticks", "loop", "frame_count"},
        "Reviewed motion policy timing",
    )
    duration, frames = timing.get("duration_ticks"), timing.get("frame_count")
    loop = timing.get("loop")
    if timing.get("ticks_per_second") != 1_000_000 \
            or type(duration) is not int or not 1 <= duration <= 600_000_000 \
            or type(frames) is not int or not 2 <= frames <= 4096 \
            or type(loop) is not bool:
        raise ReviewedMotionPolicyValidationError(
            "Reviewed motion policy timing is invalid"
        )
    return duration, loop


def _root_keys(value: Any, duration: int, loop: bool) -> None:
    rows = _array(value, "Reviewed root correction keys", minimum=2)
    previous = -1
    for raw in rows:
        row = _object(raw, "Reviewed root correction key")
        _exact(
            row, {"tick", "correction_xy_px", "incoming_interpolation"},
            "Reviewed root correction key",
        )
        tick = _tick(row.get("tick"), duration, "root correction")
        if tick <= previous:
            raise ReviewedMotionPolicyValidationError(
                "Reviewed root correction ticks must be strictly increasing"
            )
        previous = tick
        _vector(row.get("correction_xy_px"), "root correction")
        if row.get("incoming_interpolation") != "linear":
            raise ReviewedMotionPolicyValidationError(
                "Reviewed root correction interpolation must be linear"
            )
    if rows[0]["tick"] != 0 or rows[-1]["tick"] != duration:
        raise ReviewedMotionPolicyValidationError(
            "Reviewed root correction must key tick zero and duration"
        )
    if loop and (
        not _zero_vector(rows[0]["correction_xy_px"])
        or not _zero_vector(rows[-1]["correction_xy_px"])
    ):
        raise ReviewedMotionPolicyValidationError(
            "Loop root correction endpoints must both be zero"
        )


def _slot_order(value: Any, duration: int, loop: bool) -> None:
    slot_order = _object(value, "Reviewed slot order")
    _exact(slot_order, {"setup_slot_ids", "keys"}, "Reviewed slot order")
    setup = _identifiers(slot_order.get("setup_slot_ids"), "setup slot ids")
    rows = _array(slot_order.get("keys"), "Reviewed slot-order keys", minimum=1)
    expected, previous_tick, previous_order = set(setup), -1, None
    for raw in rows:
        row = _object(raw, "Reviewed slot-order key")
        _exact(row, {"tick", "slot_ids"}, "Reviewed slot-order key")
        tick = _tick(row.get("tick"), duration, "slot order")
        if tick <= previous_tick:
            raise ReviewedMotionPolicyValidationError(
                "Reviewed slot-order ticks must be strictly increasing"
            )
        previous_tick = tick
        order = _identifiers(row.get("slot_ids"), "slot-order permutation")
        if len(order) != len(setup) or set(order) != expected:
            raise ReviewedMotionPolicyValidationError(
                "Reviewed slot order must be a complete setup permutation"
            )
        if previous_order is not None and order == previous_order:
            raise ReviewedMotionPolicyValidationError(
                "Adjacent reviewed slot-order permutations must differ"
            )
        previous_order = order
    if rows[0]["tick"] != 0 or rows[0]["slot_ids"] != setup:
        raise ReviewedMotionPolicyValidationError(
            "Reviewed slot order must start with setup order at tick zero"
        )
    if loop:
        changed = any(row["slot_ids"] != setup for row in rows)
        if not changed and len(rows) != 1:
            raise ReviewedMotionPolicyValidationError(
                "Static loop slot order must contain only tick-zero setup"
            )
        if changed and (
            rows[-1]["tick"] != duration or rows[-1]["slot_ids"] != setup
        ):
            raise ReviewedMotionPolicyValidationError(
                "Dynamic loop slot order must restore setup at duration"
            )


def _identifiers(value: Any, label: str) -> list[str]:
    rows = _array(value, label, minimum=1)
    result = [_identifier(item, label) for item in rows]
    if len(set(result)) != len(result):
        raise ReviewedMotionPolicyValidationError(
            f"Reviewed motion policy {label} must be unique"
        )
    return result


def _vector(value: Any, label: str) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise ReviewedMotionPolicyValidationError(f"Reviewed {label} is invalid")
    for number in value:
        if isinstance(number, bool) or not isinstance(number, (int, float)) \
                or not math.isfinite(number) \
                or abs(float(number)) > MAX_NUMBER:
            raise ReviewedMotionPolicyValidationError(
                f"Reviewed {label} must be finite and bounded"
            )


def _zero_vector(value: list[float]) -> bool:
    return float(value[0]) == 0.0 and float(value[1]) == 0.0


def _tick(value: Any, duration: int, label: str) -> int:
    if type(value) is not int or not 0 <= value <= duration:
        raise ReviewedMotionPolicyValidationError(
            f"Reviewed {label} tick is outside the clip"
        )
    return value


def _digest(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ReviewedMotionPolicyValidationError(
            f"Reviewed motion policy {label} is not a SHA-256"
        )


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ReviewedMotionPolicyValidationError(
            f"Reviewed motion policy {label} is invalid"
        )
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewedMotionPolicyValidationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str, *, minimum: int) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= 4096:
        raise ReviewedMotionPolicyValidationError(
            f"{label} must contain {minimum}..4096 items"
        )
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise ReviewedMotionPolicyValidationError(f"{label} fields are unsupported")
