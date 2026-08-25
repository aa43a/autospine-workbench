"""Strict structural and semantic validation for P4 IK target profiles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import re
from typing import Any

from .ik_setup_local import solve_setup_local_ik
from .ik_target_geometry import (
    BEND_SOURCE,
    COLLINEAR_SINE_EPSILON,
    FALLBACK_SOURCE,
    HANDLE_SPECS,
    POSITION_TOLERANCE_PX,
    PROFILE_FORMAT,
    PROFILE_VERSION,
    ROTATION_TOLERANCE_DEG,
    SOLVER_ID,
    SOLVER_VERSION,
    SOURCE_IDENTITY_FIELDS,
    derive_ik_handles,
    solver_config,
)
from .mesh_bundle_integrity import VerifiedMeshBundle
from .resolved_project import canonical_sha256


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOP_FIELDS = set("format format_version project_id source canvas solver handles".split())
_HANDLE_FIELDS = set(
    "id limb side proximal_bone_id distal_bone_id root_xy hinge_xy "
    "setup_effector_xy proximal_length_px distal_length_px kinematic_reach "
    "setup_angles_deg bend_direction bend_source fallback_direction".split()
)


class IkTargetProfileValidationError(ValueError):
    """Raised when a P4 target profile is not strict, finite, and reproducible."""


def require_ik_target_profile(
    document: Mapping[str, Any],
    *,
    verified_bundle: VerifiedMeshBundle | None = None,
) -> None:
    """Fail closed on shape, inner geometry, or exact P3 source drift."""

    try:
        root = _object(document, "IK target profile")
        _exact(root, _TOP_FIELDS, "IK target profile")
        if root.get("format") != PROFILE_FORMAT or root.get("format_version") != PROFILE_VERSION \
                or isinstance(root.get("format_version"), bool):
            raise IkTargetProfileValidationError("IK target profile version is invalid")
        project_id = _safe_id(root.get("project_id"), "project_id")
        source = _source(root.get("source"))
        canvas = _canvas(root.get("canvas"))
        _solver(root.get("solver"))
        handles = _handles(root.get("handles"))
        canonical_sha256(root)
        if verified_bundle is not None:
            _bundle_binding(project_id, source, canvas, handles, verified_bundle)
    except IkTargetProfileValidationError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise IkTargetProfileValidationError(
            f"IK target profile validation failed: {exc}"
        ) from exc


def _source(value: Any) -> dict[str, str]:
    source = _object(value, "IK source")
    _exact(source, set(SOURCE_IDENTITY_FIELDS), "IK source")
    return {
        field: _sha(source.get(field), field) for field in SOURCE_IDENTITY_FIELDS
    }


def _canvas(value: Any) -> dict[str, Any]:
    canvas = _object(value, "IK canvas")
    fields = {"width", "height", "origin", "x_axis", "y_axis", "units"}
    _exact(canvas, fields, "IK canvas")
    if any(type(canvas.get(field)) is not int or canvas[field] < 1
           for field in ("width", "height")):
        raise IkTargetProfileValidationError("IK canvas dimensions are invalid")
    expected = {
        "origin": "top_left", "x_axis": "right",
        "y_axis": "down", "units": "pixel",
    }
    if any(canvas.get(field) != value for field, value in expected.items()):
        raise IkTargetProfileValidationError("IK canvas coordinate system is unsupported")
    return dict(canvas)


def _solver(value: Any) -> None:
    solver = _object(value, "IK solver")
    _exact(solver, {"id", "version", "config"}, "IK solver")
    if solver.get("id") != SOLVER_ID or solver.get("version") != SOLVER_VERSION:
        raise IkTargetProfileValidationError("IK solver identity is unsupported")
    config = _object(solver.get("config"), "IK solver config")
    if config != solver_config():
        raise IkTargetProfileValidationError("IK solver config is unsupported")


def _handles(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise IkTargetProfileValidationError("IK handles must be an array")
    if len(value) != len(HANDLE_SPECS):
        raise IkTargetProfileValidationError("IK profile must contain four handles")
    result = []
    for index, (raw, spec) in enumerate(zip(value, HANDLE_SPECS)):
        item = _object(raw, f"IK handle {index}")
        _exact(item, _HANDLE_FIELDS, f"IK handle {index}")
        _handle_identity(item, spec)
        _handle_geometry(item)
        result.append(dict(item))
    return result


def _handle_identity(item, spec):
    handle_id, limb, side, proximal_id, distal_id = spec
    expected = {
        "id": handle_id, "limb": limb, "side": side,
        "proximal_bone_id": proximal_id, "distal_bone_id": distal_id,
    }
    for field, value in expected.items():
        if item.get(field) != value:
            raise IkTargetProfileValidationError(
                f"IK handle identity or order is invalid: {handle_id}"
            )


def _handle_geometry(item):
    handle_id = item["id"]
    root = _point(item.get("root_xy"), f"{handle_id}.root_xy")
    hinge = _point(item.get("hinge_xy"), f"{handle_id}.hinge_xy")
    effector = _point(item.get("setup_effector_xy"), f"{handle_id}.setup_effector_xy")
    proximal = _positive(item.get("proximal_length_px"), f"{handle_id}.proximal_length_px")
    distal = _positive(item.get("distal_length_px"), f"{handle_id}.distal_length_px")
    if not _close(_distance(root, hinge), proximal) or \
            not _close(_distance(hinge, effector), distal):
        raise IkTargetProfileValidationError(f"IK handle lengths differ: {handle_id}")
    reach = _object(item.get("kinematic_reach"), f"{handle_id}.kinematic_reach")
    _exact(reach, {"minimum_px", "maximum_px"}, f"{handle_id}.kinematic_reach")
    minimum = _number(reach.get("minimum_px"), f"{handle_id}.minimum_px")
    maximum = _positive(reach.get("maximum_px"), f"{handle_id}.maximum_px")
    if minimum < 0 or not _close(minimum, abs(proximal - distal)) or \
            not _close(maximum, proximal + distal):
        raise IkTargetProfileValidationError(
            f"IK kinematic reach is not derived from bone lengths: {handle_id}"
        )
    fallback = _object(item.get("fallback_direction"), f"{handle_id}.fallback")
    _exact(fallback, {"source", "xy"}, f"{handle_id}.fallback")
    direction = _point(fallback.get("xy"), f"{handle_id}.fallback.xy")
    if fallback.get("source") != FALLBACK_SOURCE or not _close(math.hypot(*direction), 1.0):
        raise IkTargetProfileValidationError(f"IK fallback direction is invalid: {handle_id}")
    aim = (effector[0] - root[0], effector[1] - root[1])
    aim_length = math.hypot(*aim)
    elbow = (hinge[0] - root[0], hinge[1] - root[1])
    cross = aim[0] * elbow[1] - aim[1] * elbow[0]
    if aim_length <= POSITION_TOLERANCE_PX or \
            abs(cross / (aim_length * proximal)) <= COLLINEAR_SINE_EPSILON:
        raise IkTargetProfileValidationError(f"IK setup is collinear: {handle_id}")
    bend = "positive" if cross > 0 else "negative"
    if item.get("bend_direction") != bend or item.get("bend_source") != BEND_SOURCE:
        raise IkTargetProfileValidationError(f"IK bend evidence is invalid: {handle_id}")
    if not _parallel(direction, (aim[0] / aim_length, aim[1] / aim_length)):
        raise IkTargetProfileValidationError(f"IK fallback differs from setup aim: {handle_id}")
    _setup_roundtrip(item, root, hinge, effector, proximal, distal, direction)


def _setup_roundtrip(item, root, hinge, effector, proximal, distal, fallback):
    handle_id = item["id"]
    angles = _object(item.get("setup_angles_deg"), f"{handle_id}.setup_angles")
    fields = {
        "proximal_parent_world", "proximal_world", "distal_world",
        "proximal_local", "distal_local",
    }
    _exact(angles, fields, f"{handle_id}.setup_angles")
    values = {field: _number(angles.get(field), f"{handle_id}.{field}") for field in fields}
    if not _angle_close(
        _normalize(values["proximal_world"] - values["proximal_parent_world"]),
        _normalize(values["proximal_local"]),
    ) or not _angle_close(
        _normalize(values["distal_world"] - values["proximal_world"]),
        _normalize(values["distal_local"]),
    ):
        raise IkTargetProfileValidationError(f"IK setup local angles differ: {handle_id}")
    solved = solve_setup_local_ik(
        root, proximal_length=proximal, distal_length=distal,
        target_xy=effector, bend_direction=item["bend_direction"],
        fallback_direction_xy=fallback,
        setup_proximal_world_rotation_deg=values["proximal_world"],
        setup_distal_local_rotation_deg=values["distal_local"],
    )
    if solved.world.reach_state != "reachable" or \
            _distance(solved.world.elbow_xy, hinge) > POSITION_TOLERANCE_PX or \
            _distance(solved.world.resolved_target_xy, effector) > POSITION_TOLERANCE_PX or \
            abs(solved.proximal_rotation_delta_deg) > ROTATION_TOLERANCE_DEG or \
            abs(solved.distal_rotation_delta_deg) > ROTATION_TOLERANCE_DEG:
        raise IkTargetProfileValidationError(f"IK setup roundtrip failed: {handle_id}")


def _bundle_binding(project_id, source, canvas, handles, bundle):
    if not isinstance(bundle, VerifiedMeshBundle):
        raise IkTargetProfileValidationError("IK source must be a verified P3 bundle")
    expected_source = {field: getattr(bundle, field) for field in SOURCE_IDENTITY_FIELDS}
    rig = bundle.rig
    if project_id != bundle.project_id or source != expected_source or canvas != rig.get("canvas"):
        raise IkTargetProfileValidationError("IK profile source identity or canvas drifted")
    if handles != derive_ik_handles(rig):
        raise IkTargetProfileValidationError("IK handles differ from exact P3 setup")


def _object(value, label):
    if not isinstance(value, Mapping):
        raise IkTargetProfileValidationError(f"{label} must be an object")
    return value


def _exact(value, fields, label):
    if set(value) != fields:
        raise IkTargetProfileValidationError(f"{label} fields are incomplete or unsupported")


def _safe_id(value, label):
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise IkTargetProfileValidationError(f"{label} is invalid")
    return value


def _sha(value, label):
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise IkTargetProfileValidationError(f"{label} SHA-256 is invalid")
    return value


def _point(value, label):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise IkTargetProfileValidationError(f"{label} must contain two finite numbers")
    return _number(value[0], label), _number(value[1], label)


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise IkTargetProfileValidationError(f"{label} must be a finite number")
    return float(value)


def _positive(value, label):
    number = _number(value, label)
    if number <= POSITION_TOLERANCE_PX:
        raise IkTargetProfileValidationError(f"{label} must be positive")
    return number


def _distance(left, right): return math.hypot(left[0] - right[0], left[1] - right[1])
def _close(left, right): return abs(left - right) <= POSITION_TOLERANCE_PX
def _angle_close(left, right): return abs(_normalize(left - right)) <= ROTATION_TOLERANCE_DEG
def _normalize(value): return (value + 180.0) % 360.0 - 180.0
def _parallel(left, right): return _distance(left, right) <= POSITION_TOLERANCE_PX
