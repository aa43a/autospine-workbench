"""Exact fixtures for the P10.5d adaptive dynamic seam driver."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math

from autospine_workbench.body_sway_dynamic_seam_interval_geometry import (
    BodySwayDynamicSeamIntervalBoxAssessment,
    BodySwayDynamicSeamPairIntervalBound,
    BodySwayDynamicSeamRelationshipIntervalBound,
)
from autospine_workbench.body_sway_dynamic_seam_evidence_profile import (
    MAX_SQUARED_ANCHOR_GAP_PX2,
)
from autospine_workbench.body_sway_dynamic_seam_locator import (
    prepare_body_sway_dynamic_seam_locators,
)
from autospine_workbench.body_sway_interval_arithmetic import OutwardInterval
from autospine_workbench.body_sway_interval_pose import (
    prepare_body_sway_interval_pose,
)
from autospine_workbench.body_sway_probe_geometry_context import (
    prepare_body_sway_geometry_context,
)
from autospine_workbench.body_sway_probe_math import BodySwayPoseSample
from autospine_workbench.idle_behavior_inventory import BODY_BONE_IDS
from autospine_workbench.mesh_skinning_prepared import evaluate_skinning_pose
from autospine_workbench.reviewed_seam_anchor_set_validation import (
    require_reviewed_seam_anchor_set,
)
from autospine_workbench.seam_anchor_locators import (
    make_attachment_locator,
    resolve_attachment_locator_exact,
)
from tests.body_sway_dynamic_seam_locator_helpers import (
    four_vertex_fixture,
    reviewed_set,
    target_for,
)


def dynamic_seam_driver_fixture():
    rig, _target = four_vertex_fixture()
    torso = next(row for row in rig["attachments"] if row["id"] == "torso")
    torso["size"] = [100.0, 400.0]
    context = prepare_body_sway_geometry_context(rig, target_for(rig))
    document = reviewed_set(rig)
    attachments = {row["id"]: row for row in rig["attachments"]}
    source = document["relationships"][1]["anchors"]
    anchors = []
    for index, pair in enumerate(source):
        mesh_locator = deepcopy(pair["child"])
        point = resolve_attachment_locator_exact(
            mesh_locator, attachments["leg-left"]
        )
        anchors.append({
            "pair_id": f"anchor.{index:03d}",
            "parent": make_attachment_locator(
                attachments["torso"], [float(point[0]), float(point[1])]
            ),
            "child": mesh_locator,
        })
    for relationship in document["relationships"]:
        relationship["anchors"] = deepcopy(anchors)
    require_reviewed_seam_anchor_set(document)
    locators = prepare_body_sway_dynamic_seam_locators(
        rig, context, document
    )
    return rig, context, locators


def full_sample(context, *, tick, base=None, overlay=None, translation=(0, 0)):
    base_values = {bone_id: 0.0 for bone_id in context.skinning_rig.bone_ids}
    base_values.update(base or {})
    overlay_values = {bone_id: 0.0 for bone_id in BODY_BONE_IDS}
    overlay_values.update(overlay or {})
    combined = {
        bone_id: _q9(value + overlay_values.get(bone_id, 0.0))
        for bone_id, value in base_values.items()
    }
    return BodySwayPoseSample(
        tick=tick,
        base_rotation_deg=tuple(sorted(
            (bone_id, _q9(value)) for bone_id, value in base_values.items()
        )),
        overlay_rotation_deg=tuple(
            (bone_id, _q9(overlay_values[bone_id]))
            for bone_id in BODY_BONE_IDS
        ),
        combined_rotation_deg=tuple(sorted(combined.items())),
        root_translation_xy=tuple(_q9(value) for value in translation),
    )


def interval_assessment(
    locators, value=0.5, *, status="certified", reasons=(), vary=False,
):
    relationships = []
    all_values = []
    for relationship_index, relationship in enumerate(locators.relationships):
        pairs = []
        for pair_index, pair in enumerate(relationship.anchors):
            requested = float(value + (
                relationship_index * 0.1 + pair_index * 0.01
                if vary else 0.0
            ))
            delta_x = OutwardInterval.point(math.sqrt(requested)) \
                if math.isfinite(requested) else OutwardInterval(
                    math.inf, math.inf
                )
            delta_y = OutwardInterval.point(0.0)
            upper = (delta_x.square() + delta_y.square()).upper
            all_values.append(upper)
            pairs.append(BodySwayDynamicSeamPairIntervalBound(
                pair.pair_id, delta_x, delta_y, upper,
            ))
        relationships.append(BodySwayDynamicSeamRelationshipIntervalBound(
            relationship.relationship_id, tuple(pairs),
            max(row.squared_distance_upper_px2 for row in pairs),
        ))
    return BodySwayDynamicSeamIntervalBoxAssessment(
        status=status, reason_codes=tuple(reasons),
        relationships=tuple(relationships),
        max_squared_distance_upper_px2=max(all_values),
        relationship_count=len(relationships),
        pair_count=len(all_values),
        threshold_squared_px2=MAX_SQUARED_ANCHOR_GAP_PX2,
    )


def identical_locator_set(locators):
    relationships = tuple(
        replace(relationship, anchors=tuple(
            replace(pair, child=pair.parent)
            for pair in relationship.anchors[:2]
        ))
        for relationship in locators.relationships
    )
    return replace(locators, relationships=relationships)


def interval_pose(context, left, right):
    return prepare_body_sway_interval_pose(
        context,
        left_base_rotation_deg=dict(left.base_rotation_deg),
        right_base_rotation_deg=dict(right.base_rotation_deg),
        left_overlay_rotation_deg=dict(left.overlay_rotation_deg),
        right_overlay_rotation_deg=dict(right.overlay_rotation_deg),
        left_root_translation_xy=left.root_translation_xy,
        right_root_translation_xy=right.root_translation_xy,
        time_fraction=OutwardInterval(0.0, 1.0),
        gain=OutwardInterval(0.0, 1.0),
    )


def invalid_locator_inventories(locators):
    first = locators.relationships[0]
    yield replace(locators, relationships=locators.relationships[:-1])
    yield replace(locators, relationships=(
        replace(first, relationship_id="seam.changed"),
        *locators.relationships[1:],
    ))
    yield replace(locators, relationships=(
        replace(first, anchors=first.anchors[:1]),
        *locators.relationships[1:],
    ))
    yield replace(locators, relationships=(
        replace(first, anchors=(
            replace(first.anchors[0], pair_id="anchor.999"),
            *first.anchors[1:],
        )),
        *locators.relationships[1:],
    ))


def overlapping_region_mesh_locators():
    rig, _target = four_vertex_fixture()
    torso = next(row for row in rig["attachments"] if row["id"] == "torso")
    torso["size"] = [100.0, 400.0]
    context = prepare_body_sway_geometry_context(rig, target_for(rig))
    document = reviewed_set(rig)
    attachments = {row["id"]: row for row in rig["attachments"]}
    anchors = [{
        "pair_id": f"anchor.{index:03d}",
        "parent": make_attachment_locator(
            attachments["torso"], point
        ),
        "child": make_attachment_locator(
            attachments["leg-left"], point
        ),
    } for index, point in enumerate(
        attachments["leg-left"]["vertices"]
    )]
    for relationship in document["relationships"]:
        relationship["anchors"] = deepcopy(anchors)
    require_reviewed_seam_anchor_set(document)
    return prepare_body_sway_dynamic_seam_locators(
        rig, context, document
    ), context


def point_matrices(context, left, right, time, gain):
    left_base, right_base = map(dict, (
        left.base_rotation_deg, right.base_rotation_deg,
    ))
    left_overlay, right_overlay = map(dict, (
        left.overlay_rotation_deg, right.overlay_rotation_deg,
    ))
    deltas = {}
    for bone_id in context.skinning_rig.bone_ids:
        base = left_base.get(bone_id, 0.0) + (
            right_base.get(bone_id, 0.0)
            - left_base.get(bone_id, 0.0)
        ) * time
        overlay = left_overlay.get(bone_id, 0.0) + (
            right_overlay.get(bone_id, 0.0)
            - left_overlay.get(bone_id, 0.0)
        ) * time
        deltas[bone_id] = base + gain * overlay
    return evaluate_skinning_pose(
        context.skinning_rig, deltas
    )._skin_matrices


def project_locator(moments, matrices):
    x = y = 0.0
    for moment in moments:
        a, b, c, d, tx, ty = matrices[moment.bone_index]
        weight = float(moment.affine_weight)
        setup_x = float(moment.setup_x_moment)
        setup_y = float(moment.setup_y_moment)
        x += a * setup_x + c * setup_y + tx * weight
        y += b * setup_x + d * setup_y + ty * weight
    return x, y


def _q9(value):
    result = round(float(value), 9)
    return 0.0 if result == 0.0 else result
