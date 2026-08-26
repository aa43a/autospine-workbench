"""Strict validation for reviewed-policy MotionInstance v2 documents."""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any

from .motion_instance_validation import (
    MotionInstanceValidationError,
    require_motion_instance,
)
from .motion_instance_v2_overlay import overlay_motion_tracks
from .motion_target_validation import (
    MotionTargetValidationError,
    require_motion_target_profile,
)
from .resolved_project import canonical_sha256
from .reviewed_motion_policy_validation import (
    ReviewedMotionPolicyValidationError,
    require_reviewed_motion_policy,
)


FORMAT, FORMAT_VERSION = "autospine-motion-instance", 2
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_DRAW_ORDER_KEYS = 4096
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TOP = {
    "format", "format_version", "clip_id", "timing", "source",
    "target_space", "tracks", "markers", "draw_order",
}
_SOURCE = {
    "base_motion_instance_sha256", "base_retarget_bundle_sha256",
    "target_profile_sha256", "reviewed_motion_policy_sha256",
    "motion_policy_decision_sha256", "p3_rig_sha256", "p3_bundle_sha256",
}
_SPACE = {
    "translation": "setup-local-pixel",
    "rotation": "setup-local-degree",
    "positive_rotation": "clockwise",
    "interpolation": "linear",
    "draw_order": "full-back-to-front-stepped",
}


class MotionInstanceV2ValidationError(ValueError):
    """Raised when a v2 instance is ambiguous, stale, or non-canonical."""


def require_motion_instance_v2(
    document: Mapping[str, Any],
    *,
    target_profile: Mapping[str, Any] | None = None,
    base_motion_instance: Mapping[str, Any] | None = None,
    reviewed_motion_policy: Mapping[str, Any] | None = None,
) -> None:
    """Validate v2 semantics and any supplied exact source snapshots."""

    try:
        root = _object(document, "MotionInstance v2")
        _exact(root, _TOP, "MotionInstance v2")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise MotionInstanceV2ValidationError(
                "MotionInstance v2 format is unsupported"
            )
        source = _source(root.get("source"))
        space = _object(root.get("target_space"), "MotionInstance v2 target space")
        _exact(space, set(_SPACE), "MotionInstance v2 target space")
        if space != _SPACE:
            raise MotionInstanceV2ValidationError(
                "MotionInstance v2 target space is unsupported"
            )
        _validate_v1_payload(root, source, target_profile)
        _draw_order(root.get("draw_order"), root["timing"])
        if target_profile is not None:
            _cross_target(source, target_profile)
        if base_motion_instance is not None:
            _cross_base(root, source, base_motion_instance, target_profile)
        if reviewed_motion_policy is not None:
            _cross_policy(root, source, reviewed_motion_policy)
        if base_motion_instance is not None \
                and reviewed_motion_policy is not None:
            _cross_overlay(root, base_motion_instance, reviewed_motion_policy)
        if target_profile is not None and reviewed_motion_policy is not None \
                and target_profile["project_id"] != reviewed_motion_policy["project_id"]:
            raise MotionInstanceV2ValidationError(
                "Target profile and reviewed policy projects differ"
            )
        if len(_canonical(root)) > MAX_DOCUMENT_BYTES:
            raise MotionInstanceV2ValidationError(
                "MotionInstance v2 byte limit exceeded"
            )
    except MotionInstanceV2ValidationError:
        raise
    except (
        MotionInstanceValidationError, MotionTargetValidationError,
        ReviewedMotionPolicyValidationError, KeyError, OverflowError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise MotionInstanceV2ValidationError(
            f"MotionInstance v2 validation failed: {exc}"
        ) from exc


def motion_instance_v2_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical v2 digest only after standalone validation."""

    require_motion_instance_v2(document)
    return canonical_sha256(document)


def _source(value: Any) -> Mapping[str, Any]:
    source = _object(value, "MotionInstance v2 source")
    _exact(source, _SOURCE, "MotionInstance v2 source")
    for field in _SOURCE:
        if not isinstance(source.get(field), str) \
                or not _SHA.fullmatch(source[field]):
            raise MotionInstanceV2ValidationError(
                f"MotionInstance v2 {field} is not a SHA-256 digest"
            )
    return source


def _validate_v1_payload(root, source, target_profile) -> None:
    shadow = {
        "format": FORMAT,
        "format_version": 1,
        "clip_id": root.get("clip_id"),
        "timing": root.get("timing"),
        "source": {
            "motion_ir_sha256": source["base_motion_instance_sha256"],
            "motion_bundle_sha256": source["base_retarget_bundle_sha256"],
            "motion_run_sha256": source["reviewed_motion_policy_sha256"],
            "target_profile_sha256": source["target_profile_sha256"],
            "retarget_run_identity_sha256": source[
                "motion_policy_decision_sha256"
            ],
        },
        "target_space": {
            field: root["target_space"][field]
            for field in (
                "translation", "rotation", "positive_rotation", "interpolation"
            )
        },
        "tracks": root.get("tracks"),
        "markers": root.get("markers"),
    }
    require_motion_instance(shadow, target_profile=target_profile)


def _draw_order(value: Any, timing: Mapping[str, Any]) -> None:
    order = _object(value, "MotionInstance v2 draw order")
    _exact(order, {"setup_slot_ids", "keys"}, "MotionInstance v2 draw order")
    setup = _ids(order.get("setup_slot_ids"), "setup slot ids")
    keys = order.get("keys")
    if not isinstance(keys, list) or not 1 <= len(keys) <= MAX_DRAW_ORDER_KEYS:
        raise MotionInstanceV2ValidationError("Draw-order key limit exceeded")
    expected, previous_tick, previous_order = set(setup), -1, None
    duration = timing["duration_ticks"]
    for raw in keys:
        key = _object(raw, "MotionInstance v2 draw-order key")
        _exact(key, {"tick", "slot_ids"}, "MotionInstance v2 draw-order key")
        tick = key.get("tick")
        if type(tick) is not int or not 0 <= tick <= duration \
                or tick <= previous_tick:
            raise MotionInstanceV2ValidationError(
                "Draw-order key ticks must be strictly increasing and in range"
            )
        slots = _ids(key.get("slot_ids"), "draw-order slot ids")
        if len(slots) != len(setup) or set(slots) != expected:
            raise MotionInstanceV2ValidationError(
                "Draw-order key must be a complete setup permutation"
            )
        if slots == previous_order:
            raise MotionInstanceV2ValidationError(
                "Adjacent draw-order permutations must differ"
            )
        previous_tick, previous_order = tick, slots
    if keys[0]["tick"] != 0 or keys[0]["slot_ids"] != setup:
        raise MotionInstanceV2ValidationError(
            "Draw order must start with setup order at tick zero"
        )
    if timing["loop"]:
        changed = any(key["slot_ids"] != setup for key in keys)
        if not changed and len(keys) != 1:
            raise MotionInstanceV2ValidationError(
                "Static loop draw order must contain only tick-zero setup"
            )
        if changed and (keys[-1]["tick"] != duration
                        or keys[-1]["slot_ids"] != setup):
            raise MotionInstanceV2ValidationError(
                "Dynamic loop draw order must restore setup at duration"
            )


def _cross_target(source, target) -> None:
    require_motion_target_profile(target)
    if canonical_sha256(target) != source["target_profile_sha256"]:
        raise MotionInstanceV2ValidationError("Target profile SHA binding is stale")
    p3 = _object(target.get("source"), "target source").get("p3")
    p3 = _object(p3, "target P3 source")
    if p3.get("rig_sha256") != source["p3_rig_sha256"] \
            or p3.get("bundle_sha256") != source["p3_bundle_sha256"]:
        raise MotionInstanceV2ValidationError("Target P3 binding is stale")


def _cross_base(root, source, base, target_profile) -> None:
    require_motion_instance(base, target_profile=target_profile)
    if canonical_sha256(base) != source["base_motion_instance_sha256"]:
        raise MotionInstanceV2ValidationError("Base MotionInstance binding is stale")
    if base.get("clip_id") != root.get("clip_id") \
            or base.get("timing") != root.get("timing"):
        raise MotionInstanceV2ValidationError("Base MotionInstance clip timing differs")
    if base["source"]["target_profile_sha256"] != source["target_profile_sha256"]:
        raise MotionInstanceV2ValidationError("Base target profile binding differs")


def _cross_policy(root, source, policy) -> None:
    require_reviewed_motion_policy(policy)
    if canonical_sha256(policy) != source["reviewed_motion_policy_sha256"]:
        raise MotionInstanceV2ValidationError("Reviewed policy binding is stale")
    timing = {field: policy["timing"][field] for field in (
        "ticks_per_second", "duration_ticks", "loop"
    )}
    if policy.get("clip_id") != root.get("clip_id") or timing != root.get("timing"):
        raise MotionInstanceV2ValidationError("Reviewed policy clip timing differs")
    expected = {
        "motion_policy_decision_sha256": policy["source"][
            "motion_policy_decision_sha256"
        ],
        "base_motion_instance_sha256": policy["source"]["p5"]["instance_sha256"],
        "base_retarget_bundle_sha256": policy["source"]["p5"]["bundle_sha256"],
        "target_profile_sha256": policy["source"]["p5"][
            "target_profile_sha256"
        ],
        "p3_rig_sha256": policy["source"]["p3"]["rig_sha256"],
        "p3_bundle_sha256": policy["source"]["p3"]["bundle_sha256"],
    }
    if any(source[field] != value for field, value in expected.items()):
        raise MotionInstanceV2ValidationError("Reviewed policy source binding differs")
    if root.get("draw_order") != policy.get("slot_order"):
        raise MotionInstanceV2ValidationError("Draw order differs from reviewed policy")


def _cross_overlay(root, base, policy) -> None:
    if root.get("tracks") != overlay_motion_tracks(base, policy):
        raise MotionInstanceV2ValidationError(
            "MotionInstance v2 tracks differ from the exact reviewed overlay"
        )
    if root.get("markers") != base.get("markers"):
        raise MotionInstanceV2ValidationError(
            "MotionInstance v2 markers differ from the exact base instance"
        )


def _ids(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= 4096:
        raise MotionInstanceV2ValidationError(f"{label} must contain 1..4096 items")
    result = []
    for item in value:
        if not isinstance(item, str) or not _ID.fullmatch(item):
            raise MotionInstanceV2ValidationError(f"{label} contains an invalid id")
        result.append(item)
    if len(set(result)) != len(result):
        raise MotionInstanceV2ValidationError(f"{label} must be unique")
    return result


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MotionInstanceV2ValidationError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise MotionInstanceV2ValidationError(f"{label} fields are unsupported")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
