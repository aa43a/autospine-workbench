"""Strict reviewed decision contract over foot-lock and depth candidates."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
from typing import Any

from .motion_policy_candidate_inventory import (
    MotionPolicyCandidateInventoryError,
    derive_motion_policy_candidates,
)
from .resolved_project import canonical_sha256


FORMAT = "autospine-motion-policy-decision"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
MAX_REVISION = 2 ** 31 - 1
MAX_NUMBER = 1_000_000_000_000.0
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOP = {
    "format", "format_version", "project_id", "clip_id", "source",
    "review", "decisions", "root_release_keys", "draw_order_loop_reset",
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


class MotionPolicyDecisionValidationError(ValueError):
    """Raised when a reviewed decision is incomplete, stale, or ambiguous."""


def require_motion_policy_decision(
    document: Mapping[str, Any],
    *,
    foot_candidates: Mapping[str, Any],
    depth_candidates: Mapping[str, Any],
) -> None:
    """Require exhaustive human decisions over two exact candidate reports."""

    try:
        root = _object(document, "Motion-policy decision")
        _exact(root, _TOP, "Motion-policy decision")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise MotionPolicyDecisionValidationError(
                "Motion-policy decision format is unsupported"
            )
        _identifier(root.get("project_id"), "project_id")
        _identifier(root.get("clip_id"), "clip_id")
        _source(root.get("source"))
        _review(root.get("review"))
        inventory = derive_motion_policy_candidates(
            foot_candidates, depth_candidates
        )
        if root["project_id"] != inventory.project_id \
                or root["clip_id"] != inventory.clip_id \
                or root["source"] != inventory.source:
            raise MotionPolicyDecisionValidationError(
                "Motion-policy decision candidate source binding is stale"
            )
        _decisions(root.get("decisions"), inventory.candidates)
        _release_keys(
            root.get("root_release_keys"), inventory.unconstrained_foot_ticks
        )
        _loop_reset(root.get("draw_order_loop_reset"), inventory.loop)
        encoded = json.dumps(
            dict(root), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise MotionPolicyDecisionValidationError(
                "Motion-policy decision byte limit exceeded"
            )
    except MotionPolicyDecisionValidationError:
        raise
    except MotionPolicyCandidateInventoryError as exc:
        raise MotionPolicyDecisionValidationError(
            f"Motion-policy decision candidates are invalid: {exc}"
        ) from exc
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise MotionPolicyDecisionValidationError(
            f"Motion-policy decision validation failed: {exc}"
        ) from exc


def motion_policy_decision_sha256(
    document: Mapping[str, Any], *,
    foot_candidates: Mapping[str, Any],
    depth_candidates: Mapping[str, Any],
) -> str:
    require_motion_policy_decision(
        document,
        foot_candidates=foot_candidates,
        depth_candidates=depth_candidates,
    )
    return canonical_sha256(document)


def _source(value: Any) -> None:
    source = _object(value, "Motion-policy decision source")
    _exact(
        source,
        {
            "foot_lock_candidates_sha256", "depth_order_candidates_sha256",
            "depth_pair_policy_sha256", "p8", "p5", "p3",
        },
        "Motion-policy decision source",
    )
    for field in (
        "foot_lock_candidates_sha256", "depth_order_candidates_sha256",
        "depth_pair_policy_sha256",
    ):
        _digest(source.get(field), field)
    for stage, fields in (("p8", _P8), ("p5", _P5), ("p3", _P3)):
        row = _object(source.get(stage), f"Motion-policy {stage} source")
        _exact(row, fields, f"Motion-policy {stage} source")
        for field in fields:
            _digest(row.get(field), f"{stage}.{field}")


def _review(value: Any) -> None:
    review = _object(value, "Motion-policy review")
    _exact(review, {"status", "method", "revision"}, "Motion-policy review")
    revision = review.get("revision")
    if review.get("status") != "approved" \
            or review.get("method") != "human" \
            or type(revision) is not int \
            or not 1 <= revision <= MAX_REVISION:
        raise MotionPolicyDecisionValidationError(
            "Motion-policy decision requires an approved human review revision"
        )


def _decisions(value: Any, candidates) -> None:
    rows = _array(value, "Motion-policy decisions")
    expected = tuple(row.candidate_id for row in candidates)
    if len(rows) != len(expected):
        raise MotionPolicyDecisionValidationError(
            "Motion-policy decisions are not exhaustive"
        )
    actual = []
    by_id = {row.candidate_id: row for row in candidates}
    previous = None
    for raw in rows:
        row = _object(raw, "Motion-policy decision row")
        _exact(
            row, {"candidate_id", "action", "reason_code", "payload"},
            "Motion-policy decision row",
        )
        candidate_id = _identifier(row.get("candidate_id"), "candidate_id")
        if previous is not None and candidate_id <= previous:
            raise MotionPolicyDecisionValidationError(
                "Motion-policy decisions must be sorted and unique"
            )
        previous = candidate_id
        candidate = by_id.get(candidate_id)
        if candidate is None:
            raise MotionPolicyDecisionValidationError(
                "Motion-policy decision references an extra candidate"
            )
        _identifier(row.get("reason_code"), "reason_code")
        _action_payload(row, candidate)
        actual.append(candidate_id)
    if tuple(actual) != expected:
        raise MotionPolicyDecisionValidationError(
            "Motion-policy decisions omit or reorder candidates"
        )


def _action_payload(row, candidate) -> None:
    action, payload = row.get("action"), row.get("payload")
    if action not in {"accept", "reject", "adjust", "unobservable"}:
        raise MotionPolicyDecisionValidationError(
            "Motion-policy decision action is unsupported"
        )
    if action != "adjust":
        if payload is not None:
            raise MotionPolicyDecisionValidationError(
                "Non-adjust motion-policy decision payload must be null"
            )
        if action == "accept" and candidate.kind == "foot_lock" \
                and candidate.foot_state != "candidate":
            raise MotionPolicyDecisionValidationError(
                "Automatically rejected foot-lock evidence cannot be accepted"
            )
        return
    payload = _object(payload, "Motion-policy adjustment payload")
    if candidate.kind == "foot_lock":
        _exact(payload, {"final_correction_xy_px"}, "Foot-lock adjustment")
        _vector(payload.get("final_correction_xy_px"))
        return
    _exact(payload, {"final_front_slot"}, "Depth-order adjustment")
    if payload.get("final_front_slot") not in candidate.depth_slots:
        raise MotionPolicyDecisionValidationError(
            "Depth-order adjusted front slot is outside its pair"
        )


def _release_keys(value: Any, unconstrained_ticks: tuple[int, ...]) -> None:
    rows = _array(value, "Motion-policy root release keys")
    allowed, previous = set(unconstrained_ticks), None
    for raw in rows:
        row = _object(raw, "Motion-policy root release key")
        _exact(
            row,
            {"tick", "correction_xy_px", "incoming_interpolation", "reason_code"},
            "Motion-policy root release key",
        )
        tick = row.get("tick")
        if type(tick) is not int or tick not in allowed \
                or previous is not None and tick <= previous:
            raise MotionPolicyDecisionValidationError(
                "Root release keys must be sorted unique unconstrained ticks"
            )
        previous = tick
        _vector(row.get("correction_xy_px"))
        if row.get("incoming_interpolation") not in {"linear", "stepped"}:
            raise MotionPolicyDecisionValidationError(
                "Root release interpolation is unsupported"
            )
        _identifier(row.get("reason_code"), "release reason_code")


def _loop_reset(value: Any, loop: bool) -> None:
    row = _object(value, "Motion-policy draw-order loop reset")
    _exact(row, {"mode", "approved"}, "Motion-policy draw-order loop reset")
    approved = row.get("approved")
    if row.get("mode") != "explicit" or type(approved) is not bool \
            or approved and not loop:
        raise MotionPolicyDecisionValidationError(
            "Draw-order loop reset must be explicit and requires a loop clip"
        )


def _vector(value: Any) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise MotionPolicyDecisionValidationError(
            "Motion-policy correction vector is invalid"
        )
    for number in value:
        if isinstance(number, bool) or not isinstance(number, (int, float)) \
                or not math.isfinite(number) or abs(float(number)) > MAX_NUMBER:
            raise MotionPolicyDecisionValidationError(
                "Motion-policy correction is not finite and bounded"
            )


def _digest(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise MotionPolicyDecisionValidationError(
            f"Motion-policy {label} is not a SHA-256"
        )


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise MotionPolicyDecisionValidationError(
            f"Motion-policy {label} is invalid"
        )
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MotionPolicyDecisionValidationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise MotionPolicyDecisionValidationError(f"{label} must be an array")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise MotionPolicyDecisionValidationError(f"{label} fields are unsupported")
