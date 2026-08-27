"""Detached fixtures for P10.5d dynamic seam locator tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from autospine_workbench.body_sway_probe_geometry_context import (
    PreparedBodySwayMesh,
)
from autospine_workbench.mesh_skinning_prepared import (
    prepare_skinning_binding,
)
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.reviewed_seam_anchor_set_compiler import (
    compile_reviewed_seam_anchor_set,
)
from autospine_workbench.reviewed_seam_anchor_set_validation import (
    require_reviewed_seam_anchor_set,
)
from autospine_workbench.seam_anchor_locators import make_attachment_locator
from tests.body_sway_probe_geometry_helpers import (
    exact_rig_and_target,
    rebound,
)
from tests.reviewed_seam_anchor_set_helpers import reviewed_set_inputs


def four_vertex_fixture():
    rig, target = exact_rig_and_target()
    rig["slots"].append({
        "id": "torso-alt", "bone": "neck-head",
        "setup_attachment": "torso-alt", "setup_draw_order": 2,
    })
    rig["attachments"].append({
        "id": "torso-alt", "slot": "torso-alt", "type": "region",
        "source_layer_ids": ["torso-alt"],
        "canvas_offset_xy": [180.0, 120.0], "pivot_xy": [5.0, 6.0],
        "size": [10.0, 12.0],
    })
    mesh = rig["attachments"][0]
    mesh["weights"][0] = [
        {"bone": "thigh.left", "weight": 0.1},
        {"bone": "calf.left", "weight": 0.9},
    ]
    first, second, third = mesh["vertices"]
    mesh["vertices"].append([
        second[0] + third[0] - first[0],
        second[1] + third[1] - first[1],
    ])
    mesh["uvs"].append([1.0, 1.0])
    mesh["weights"].append([{"bone": "calf.left", "weight": 1.0}])
    mesh["triangles"].extend([1, 3, 2])
    rebound(rig, target)
    return rig, target


def target_for(rig):
    """Rebuild the exact motion target for an already-shaped fixture rig."""

    _unused, target = exact_rig_and_target()
    rebound(rig, target)
    return target


def reviewed_set(rig):
    candidate, decision, candidate_rig = reviewed_set_inputs()
    document = compile_reviewed_seam_anchor_set(
        candidate, decision, candidate_rig
    ).document
    document["source"]["p3_rig_sha256"] = canonical_sha256(rig)
    attachments = {row["id"]: row for row in rig["attachments"]}
    second_kind = attachments["torso-alt"]["type"]
    combinations = (
        (("leg-left" if second_kind == "mesh" else "torso"), "torso-alt"),
        ("torso", "leg-left"),
        ("leg-left", "torso"),
    )
    mesh = attachments["leg-left"]
    first, second, third = mesh["vertices"][:3]
    for index, relationship in enumerate(document["relationships"]):
        parent, child = combinations[index % len(combinations)]
        anchors = []
        for pair_index in range(4):
            t, u = 0.1 + pair_index * 0.15, 0.1
            mesh_point = [
                (1 - t - u) * first[axis] + t * second[axis]
                + u * third[axis] for axis in range(2)
            ]
            points = {
                "torso": [181 + pair_index * 2, 101 + index % 2],
                "torso-alt": (mesh_point if second_kind == "mesh" else
                              [181 + pair_index * 2, 121 + index % 2]),
                "leg-left": mesh_point,
            }
            anchors.append({
                "pair_id": f"anchor.{pair_index:03d}",
                "parent": make_attachment_locator(
                    attachments[parent], points[parent]
                ),
                "child": make_attachment_locator(
                    attachments[child], points[child]
                ),
            })
        relationship["anchors"] = anchors
    require_reviewed_seam_anchor_set(document)
    return document


def second_mesh(source_rig, source_context):
    rig, context = deepcopy(source_rig), source_context
    original = deepcopy(rig["attachments"][0])
    original.update({
        "id": "torso-alt", "slot": "torso-alt",
        "source_layer_ids": ["torso-alt-mesh"],
    })
    rig["attachments"][-1] = original
    source_mesh = next(row for row in context.attachments
                       if row.attachment_id == "leg-left")
    binding = prepare_skinning_binding(
        context.skinning_rig, source_mesh.setup_vertices_xy,
        original["weights"],
    )
    prepared = PreparedBodySwayMesh(
        "torso-alt", "mesh", "torso-alt", "neck-head",
        source_mesh.setup_vertices_xy, binding, source_mesh.deformation,
    )
    rows = tuple(sorted(
        tuple(row for row in context.attachments
              if row.attachment_id != "torso-alt") + (prepared,),
        key=lambda row: row.attachment_id,
    ))
    return rig, replace(context, attachments=rows)
