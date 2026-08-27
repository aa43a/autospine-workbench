"""Bounded materialization for supported static attachment seam pairs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def materialize_supported_attachment_pairs(
    parents: Sequence[Any], children: Sequence[Any], maximum: int,
) -> tuple[list[dict[str, Any]], set[str]]:
    """Skip mesh-mesh in O(P+C+supported) and enforce before allocation."""

    nonmesh_children = tuple(
        child for child in children if child.kind != "mesh"
    )
    mesh_parent_count = sum(parent.kind == "mesh" for parent in parents)
    mesh_child_count = len(children) - len(nonmesh_children)
    supported_count = sum(
        len(nonmesh_children) if parent.kind == "mesh" else len(children)
        for parent in parents
    )
    reasons = set()
    if mesh_parent_count and mesh_child_count:
        reasons.add("MESH_MESH_UNSUPPORTED")
    if supported_count > maximum:
        reasons.add("RELATION_CANDIDATE_PAIR_BUDGET_EXCEEDED")
        return [], reasons
    pairs = []
    for parent in parents:
        eligible = nonmesh_children if parent.kind == "mesh" else children
        for child in eligible:
            pairs.append({
                "parent_attachment_id": parent.identifier,
                "child_attachment_id": child.identifier,
                "parent_attachment_type": parent.kind,
                "child_attachment_type": child.kind,
                "parent_source_layer_ids": list(parent.sources),
                "child_source_layer_ids": list(child.sources),
            })
    return pairs, reasons
