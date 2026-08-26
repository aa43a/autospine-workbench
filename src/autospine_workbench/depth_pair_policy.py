"""Reviewed pair policy for candidate-only depth ordering."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
from typing import Any

from .depth_order_inputs import DepthOrderInputs
from .motion_roles import CANONICAL_BONE_ROLES
from .resolved_project import canonical_sha256


FORMAT = "autospine-depth-pair-policy"
FORMAT_VERSION = 1
HYSTERESIS_UNIT = "root_reference_normalized_depth"
MAX_PAIRS = 64
MAX_HOLD_FRAMES = 4096
MAX_THRESHOLD = 1024.0
MAX_DOCUMENT_BYTES = 1024 * 1024
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOP = {
    "format", "format_version", "policy_id", "project_id", "clip_id",
    "source", "review", "hysteresis", "pairs",
}
_PAIR = {"pair_id", "slots", "setup_front_slot"}
_SLOT = {"slot_id", "depth_role"}
_P8_SOURCE = {
    "projected_motion_sha256", "bundle_sha256", "camera_sha256",
    "run_sha256", "legacy_motion_sha256", "p7_motion_sha256",
    "p7_bundle_sha256", "p7_run_sha256",
}
_P5_SOURCE = {
    "target_profile_sha256", "instance_sha256", "run_sha256",
    "retarget_report_sha256", "mesh_regression_sha256", "bundle_sha256",
}
_P3_SOURCE = {
    "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
    "resolved_project_sha256", "rig_sha256", "run_sha256",
    "probes_sha256", "visuals_sha256", "bundle_sha256",
}


class DepthPairPolicyError(ValueError):
    """Raised when a reviewed depth-pair policy is ambiguous or stale."""


def require_depth_pair_policy(
    document: Mapping[str, Any], *, inputs: DepthOrderInputs | None = None
) -> None:
    """Validate standalone policy semantics and optional exact input binding."""

    try:
        root = _object(document, "Depth pair policy")
        _exact(root, _TOP, "Depth pair policy")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise DepthPairPolicyError("Depth pair policy format is unsupported")
        for field in ("policy_id", "project_id", "clip_id"):
            _identifier(root.get(field), field)
        source = _source(root.get("source"))
        if root.get("review") != {
            "status": "approved", "method": "human",
        }:
            raise DepthPairPolicyError(
                "Depth pair policy must be explicitly human approved"
            )
        _hysteresis(root.get("hysteresis"))
        pairs = _pairs(root.get("pairs"))
        if inputs is not None:
            _cross_inputs(root, source, pairs, inputs)
        encoded = json.dumps(
            dict(root), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise DepthPairPolicyError("Depth pair policy byte limit exceeded")
    except DepthPairPolicyError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise DepthPairPolicyError(
            f"Depth pair policy validation failed: {exc}"
        ) from exc


def depth_pair_policy_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical identity of one reviewed policy."""

    require_depth_pair_policy(document)
    return canonical_sha256(document)


def _source(value: Any) -> Mapping[str, Any]:
    source = _object(value, "Depth pair policy source")
    _exact(source, {"p8", "p5", "p3"}, "Depth pair policy source")
    for stage, fields in (
        ("p8", _P8_SOURCE), ("p5", _P5_SOURCE), ("p3", _P3_SOURCE),
    ):
        row = _object(source.get(stage), f"Depth pair policy {stage} source")
        _exact(row, fields, f"Depth pair policy {stage} source")
        for field in fields:
            value = row.get(field)
            if not isinstance(value, str) or not _SHA.fullmatch(value):
                raise DepthPairPolicyError(
                    f"Depth pair policy {stage}.{field} is not a SHA-256"
                )
    return source


def _hysteresis(value: Any) -> None:
    row = _object(value, "Depth pair hysteresis")
    _exact(
        row, {
            "unit", "enter_threshold", "exit_threshold",
            "minimum_hold_frames",
        },
        "Depth pair hysteresis",
    )
    if row.get("unit") != HYSTERESIS_UNIT:
        raise DepthPairPolicyError("Depth pair hysteresis unit is unsupported")
    enter = _number(row.get("enter_threshold"), "enter threshold")
    exit_ = _number(row.get("exit_threshold"), "exit threshold")
    hold = row.get("minimum_hold_frames")
    if not enter > exit_ >= 0:
        raise DepthPairPolicyError(
            "Depth pair thresholds require enter > exit >= 0"
        )
    if type(hold) is not int or not 1 <= hold <= MAX_HOLD_FRAMES:
        raise DepthPairPolicyError("Depth pair minimum hold is invalid")


def _pairs(value: Any) -> list[Mapping[str, Any]]:
    rows = _array(value, "Depth pair policy pairs")
    if not 1 <= len(rows) <= MAX_PAIRS:
        raise DepthPairPolicyError("Depth pair policy pair count is invalid")
    previous = None
    unordered: set[tuple[str, str]] = set()
    result = []
    for raw in rows:
        pair = _object(raw, "Depth pair policy pair")
        _exact(pair, _PAIR, "Depth pair policy pair")
        pair_id = _identifier(pair.get("pair_id"), "pair_id")
        if previous is not None and pair_id <= previous:
            raise DepthPairPolicyError(
                "Depth pair policies must be sorted and uniquely identified"
            )
        previous = pair_id
        slots = _array(pair.get("slots"), "Depth pair slots")
        if len(slots) != 2:
            raise DepthPairPolicyError("Depth pair must contain exactly two slots")
        normalized = []
        for slot_raw in slots:
            slot = _object(slot_raw, "Depth pair slot")
            _exact(slot, _SLOT, "Depth pair slot")
            slot_id = _identifier(slot.get("slot_id"), "slot_id")
            role = slot.get("depth_role")
            if role not in CANONICAL_BONE_ROLES:
                raise DepthPairPolicyError("Depth pair role is not canonical")
            normalized.append((slot_id, str(role)))
        if normalized[0][0] >= normalized[1][0]:
            raise DepthPairPolicyError(
                "Depth pair slots must be sorted and distinct"
            )
        identity = tuple(sorted((normalized[0][0], normalized[1][0])))
        if identity in unordered:
            raise DepthPairPolicyError(
                "Depth pair is duplicated or repeated in reverse"
            )
        unordered.add(identity)
        if pair.get("setup_front_slot") not in identity:
            raise DepthPairPolicyError("Setup front slot is absent from its pair")
        result.append(pair)
    return result


def _cross_inputs(root, source, pairs, inputs: DepthOrderInputs) -> None:
    if type(inputs) is not DepthOrderInputs:
        raise DepthPairPolicyError("Depth pair policy inputs are not exact")
    if source != inputs.identities \
            or root["project_id"] != inputs.target["project_id"] \
            or root["clip_id"] != inputs.projected["clip_id"]:
        raise DepthPairPolicyError("Depth pair policy source binding is stale")
    slots = {row["id"]: row for row in inputs.rig["slots"]}
    target_bones = {
        row["role"]: row["bone_id"] for row in inputs.target["bones"]
    }
    projected = {
        row["role"]: row for row in inputs.projected["segment_tracks"]
    }
    for pair in pairs:
        bound = []
        for row in pair["slots"]:
            slot = slots.get(row["slot_id"])
            track = projected.get(row["depth_role"])
            if slot is None:
                raise DepthPairPolicyError(
                    f"Depth pair slot is absent from P3: {row['slot_id']}"
                )
            if target_bones.get(row["depth_role"]) != slot.get("bone"):
                raise DepthPairPolicyError(
                    f"Depth role does not match slot bone: {row['slot_id']}"
                )
            if track is None or any(
                sample["projection_state"] != "observable"
                for sample in track["samples"]
            ):
                raise DepthPairPolicyError(
                    f"Depth role is collapsed or unobservable: {row['depth_role']}"
                )
            bound.append(slot)
        expected_front = max(
            bound, key=lambda slot: slot["setup_draw_order"]
        )["id"]
        if pair["setup_front_slot"] != expected_front:
            raise DepthPairPolicyError(
                "Setup front slot differs from P3 setup draw order"
            )


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) \
            or abs(float(value)) > MAX_THRESHOLD:
        raise DepthPairPolicyError(f"Depth pair {label} is invalid")
    return float(value)


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise DepthPairPolicyError(f"Depth pair {label} is invalid")
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DepthPairPolicyError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise DepthPairPolicyError(f"{label} must be an array")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise DepthPairPolicyError(f"{label} fields are unsupported")
