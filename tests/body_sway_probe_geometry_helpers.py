"""Small exact fixtures for body-sway structural geometry tests."""

from __future__ import annotations

from copy import deepcopy

from autospine_workbench.body_sway_probe_math import BodySwayPoseSample
from autospine_workbench.idle_behavior_inventory import BODY_BONE_IDS
from autospine_workbench.motion_target_profile import compile_motion_target_profile
from autospine_workbench.rig_fk import evaluate_world_setup
from tests.test_motion_target_profile import full_rig, pair


def exact_rig_and_target(*, failing_mesh: bool = False):
    rig = full_rig()
    rig["slots"] = [
        {
            "id": "leg-left", "bone": "thigh.left",
            "setup_attachment": "leg-left", "setup_draw_order": 0,
        },
        {
            "id": "torso", "bone": "neck-head",
            "setup_attachment": "torso", "setup_draw_order": 1,
        },
    ]
    rig["attachments"] = [
        _mesh(rig, failing=failing_mesh),
        {
            "id": "torso", "slot": "torso", "type": "region",
            "source_layer_ids": ["torso"],
            "canvas_offset_xy": [180.0, 100.0],
            "pivot_xy": [5.0, 6.0], "size": [10.0, 12.0],
        },
    ]
    rig["capabilities"] = ["mesh_attachment", "region_attachment"]
    ik, mesh_bundle = pair(converted=True, rig=rig)
    target = compile_motion_target_profile(ik, mesh_bundle).document
    return rig, target


def sample(*, base=None, overlay=None, translation=(0.0, 0.0), tick=0):
    base_values = {bone_id: 0.0 for bone_id in BODY_BONE_IDS}
    base_values.update(base or {})
    overlay_values = {bone_id: 0.0 for bone_id in BODY_BONE_IDS}
    overlay_values.update(overlay or {})
    combined = {
        bone_id: round(value + overlay_values.get(bone_id, 0.0), 9)
        for bone_id, value in base_values.items()
    }
    return BodySwayPoseSample(
        tick=tick,
        base_rotation_deg=tuple(sorted(base_values.items())),
        overlay_rotation_deg=tuple(
            (bone_id, overlay_values[bone_id]) for bone_id in BODY_BONE_IDS
        ),
        combined_rotation_deg=tuple(sorted(combined.items())),
        root_translation_xy=translation,
    )


def rebound(rig, target):
    """Recompile a target after an intentional rig mutation."""

    ik, mesh_bundle = pair(converted=True, rig=deepcopy(rig))
    rebuilt = compile_motion_target_profile(ik, mesh_bundle).document
    target.clear()
    target.update(rebuilt)


def attachment(result, identifier):
    return next(row for row in result.attachments
                if row.attachment_id == identifier)


def _mesh(rig, *, failing):
    world = evaluate_world_setup(rig["bones"])
    hinge = world["calf.left"]["origin_xy"]
    if failing:
        vertices = [
            hinge, [hinge[0] + 1000.0, hinge[1]],
            [hinge[0] + 1000.0, hinge[1] + 0.001],
        ]
        weights = [
            [{"bone": "thigh.left", "weight": 1.0}],
            [{"bone": "thigh.left", "weight": 1.0}],
            [{"bone": "calf.left", "weight": 1.0}],
        ]
    else:
        import math
        angle = math.radians(world["calf.left"]["rotation_deg"])
        direction = math.cos(angle), math.sin(angle)
        normal = -direction[1], direction[0]
        vertices = [
            hinge,
            [hinge[0] + 4 * direction[0], hinge[1] + 4 * direction[1]],
            [hinge[0] + 4 * normal[0], hinge[1] + 4 * normal[1]],
        ]
        weights = [
            [
                {"bone": "thigh.left", "weight": 0.5},
                {"bone": "calf.left", "weight": 0.5},
            ],
            [{"bone": "calf.left", "weight": 1.0}],
            [{"bone": "calf.left", "weight": 1.0}],
        ]
    return {
        "id": "leg-left", "slot": "leg-left", "type": "mesh",
        "source_layer_ids": ["leg-left"], "canvas_offset_xy": [0.0, 0.0],
        "pivot_xy": [0.0, 0.0],
        "vertices": [list(point) for point in vertices],
        "uvs": [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
        "triangles": [0, 1, 2], "weights": weights,
    }
