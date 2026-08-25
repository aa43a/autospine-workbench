"""Generate and gate the fixed numerical cases for one P4 IK handle."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .ik_probe_math import (
    distance as _distance,
    mapping as _mapping,
    nonnegative as _nonnegative,
    point as _point,
    positive as _positive,
    quantize as _q,
    quantize_point as _q_point,
    radial as _radial,
    unit as _unit,
)
from .ik_setup_local import solve_setup_local_ik


CASE_ORDER = (
    "setup",
    "reachable-mid",
    "unreachable-far",
    "unreachable-near",
    "coincident-target",
)
REACHABLE_RADIUS_FRACTION = 0.5
FAR_RADIUS_MULTIPLIER = 1.25
NEAR_RADIUS_MULTIPLIER = 0.5
GEOMETRY_TOLERANCE_PX = 1e-6
ROTATION_TOLERANCE_DEG = 1e-6
VISUAL_SAFETY_REASON = (
    "P4 probes kinematic reach only; P3 mesh safe-angle evidence remains authoritative"
)


def probe_handle(handle: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate the five pinned cases for one already validated handle."""

    root = _point(handle.get("root_xy"), "handle root")
    setup_effector = _point(
        handle.get("setup_effector_xy"), "setup effector"
    )
    fallback_value = _mapping(
        handle.get("fallback_direction"), "fallback direction"
    ).get("xy")
    fallback = _unit(_point(fallback_value, "fallback direction"))
    proximal = _positive(handle.get("proximal_length_px"), "proximal length")
    distal = _positive(handle.get("distal_length_px"), "distal length")
    reach = _mapping(handle.get("kinematic_reach"), "kinematic reach")
    minimum = _nonnegative(reach.get("minimum_px"), "minimum reach")
    maximum = _positive(reach.get("maximum_px"), "maximum reach")
    cases = [
        _not_applicable(case_id)
        if target is None
        else _evaluate_case(
            case_id, target, expected, handle, root, proximal, distal,
            minimum, maximum, fallback,
        )
        for case_id, target, expected in _case_specs(
            root, setup_effector, fallback, minimum, maximum
        )
    ]
    gate = "rejected" if any(
        case["status"] == "rejected" for case in cases
    ) else "passed"
    return {
        "handle_id": handle["id"],
        "limb": handle["limb"],
        "side": handle["side"],
        "proximal_bone_id": handle["proximal_bone_id"],
        "distal_bone_id": handle["distal_bone_id"],
        "kinematic_reach": {
            "minimum_px": minimum,
            "maximum_px": maximum,
        },
        "mesh_visual_safety": {
            "status": "not_evaluated",
            "reason": VISUAL_SAFETY_REASON,
        },
        "cases": cases,
        "gate": {"status": gate},
    }


def _case_specs(root, setup_effector, fallback, minimum, maximum):
    midpoint = minimum + (
        maximum - minimum
    ) * REACHABLE_RADIUS_FRACTION
    near_target = None if minimum == 0.0 else _radial(
        root, fallback, minimum * NEAR_RADIUS_MULTIPLIER
    )
    near_state = None if near_target is None else "unreachable_too_near"
    coincident_state = (
        "reachable" if minimum == 0.0 else "unreachable_too_near"
    )
    return (
        ("setup", setup_effector, "reachable"),
        ("reachable-mid", _radial(root, fallback, midpoint), "reachable"),
        (
            "unreachable-far",
            _radial(root, fallback, maximum * FAR_RADIUS_MULTIPLIER),
            "unreachable_too_far",
        ),
        ("unreachable-near", near_target, near_state),
        ("coincident-target", root, coincident_state),
    )


def _evaluate_case(
    case_id, target, expected_state, handle, root, proximal, distal,
    minimum, maximum, fallback,
):
    angles = _mapping(handle.get("setup_angles_deg"), "setup angles")
    solved = solve_setup_local_ik(
        root,
        proximal_length=proximal,
        distal_length=distal,
        target_xy=target,
        bend_direction=handle["bend_direction"],
        fallback_direction_xy=fallback,
        setup_proximal_world_rotation_deg=angles["proximal_world"],
        setup_distal_local_rotation_deg=angles["distal_local"],
    )
    world = solved.world
    elbow = world.elbow_xy
    effector = world.resolved_target_xy
    setup = case_id == "setup"
    metrics = _metrics(
        root, elbow, effector, world.resolved_distance, proximal, distal,
        minimum, maximum, handle if setup else None,
    )
    passed = world.reach_state == expected_state and _case_passes(
        case_id, world, solved, metrics, minimum, maximum
    )
    return {
        "id": case_id,
        "applicability": "evaluated",
        "requested_target_xy": _q_point(world.requested_target_xy),
        "resolved_target_xy": _q_point(effector),
        "reach_state": world.reach_state,
        "hinge_xy": _q_point(elbow),
        "effector_xy": _q_point(effector),
        "used_fallback_direction": world.used_fallback_direction,
        "setup_local_deltas_deg": {
            "proximal": _q(solved.proximal_rotation_delta_deg),
            "distal": _q(solved.distal_rotation_delta_deg),
        },
        "metrics": {
            key: None if value is None else _q(value)
            for key, value in metrics.items()
        },
        "status": "passed" if passed else "rejected",
    }


def _metrics(
    root, elbow, effector, resolved_distance, proximal, distal,
    minimum, maximum, setup_handle,
):
    result = {
        "proximal_length_error_px": abs(_distance(root, elbow) - proximal),
        "distal_length_error_px": abs(_distance(elbow, effector) - distal),
        "resolved_distance_error_px": abs(
            _distance(root, effector) - resolved_distance
        ),
        "annulus_violation_px": max(
            0.0,
            minimum - resolved_distance,
            resolved_distance - maximum,
        ),
        "setup_hinge_error_px": None,
        "setup_effector_error_px": None,
    }
    if setup_handle is not None:
        result["setup_hinge_error_px"] = _distance(
            elbow, _point(setup_handle["hinge_xy"], "setup hinge")
        )
        result["setup_effector_error_px"] = _distance(
            effector,
            _point(setup_handle["setup_effector_xy"], "setup effector"),
        )
    return result


def _case_passes(case_id, world, solved, metrics, minimum, maximum):
    segment_fields = (
        "proximal_length_error_px",
        "distal_length_error_px",
        "resolved_distance_error_px",
    )
    if any(
        metrics[field] > GEOMETRY_TOLERANCE_PX for field in segment_fields
    ):
        return False
    if metrics["annulus_violation_px"] > GEOMETRY_TOLERANCE_PX:
        return False
    if case_id == "setup" and any(
        metrics[field] is None
        or metrics[field] > GEOMETRY_TOLERANCE_PX
        for field in ("setup_hinge_error_px", "setup_effector_error_px")
    ):
        return False
    if case_id in {"setup", "reachable-mid"} and abs(
        world.requested_distance - world.resolved_distance
    ) > GEOMETRY_TOLERANCE_PX:
        return False
    if case_id == "unreachable-far" and abs(
        world.resolved_distance - maximum
    ) > GEOMETRY_TOLERANCE_PX:
        return False
    if case_id in {"unreachable-near", "coincident-target"} \
            and minimum > 0.0 and abs(
                world.resolved_distance - minimum
            ) > GEOMETRY_TOLERANCE_PX:
        return False
    if case_id == "coincident-target" and not world.used_fallback_direction:
        return False
    if case_id == "setup" and any(
        abs(value) > ROTATION_TOLERANCE_DEG
        for value in (
            solved.proximal_rotation_delta_deg,
            solved.distal_rotation_delta_deg,
        )
    ):
        return False
    return True


def _not_applicable(case_id):
    return {
        "id": case_id,
        "applicability": "not_applicable",
        "reason": "minimum_kinematic_reach_is_zero",
        "status": "not_applicable",
    }
