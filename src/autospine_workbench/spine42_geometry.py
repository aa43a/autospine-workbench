"""Coordinate and attachment projection for the pinned Spine 4.2 adapter."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
from typing import Any, Mapping, Sequence

from .rig_fk import evaluate_world_setup, world_to_local_point
from .spine42_contract import Spine42ContractError


@dataclass(frozen=True, slots=True)
class Spine42Setup:
    """Canonical bone order plus setup data needed by attachment conversion."""

    bones: tuple[dict[str, Any], ...]
    bone_ids: tuple[str, ...]
    world: Mapping[str, Mapping[str, Any]]

    @property
    def bone_index(self) -> dict[str, int]:
        return {bone_id: index for index, bone_id in enumerate(self.bone_ids)}


def project_setup(rig: Mapping[str, Any]) -> Spine42Setup:
    """Reflect RigIR y-down/cw setup into deterministic Spine y-up/ccw."""

    source = _ordered_bones(rig["bones"])
    height = float(rig["canvas"]["height"])
    projected: list[dict[str, Any]] = []
    for bone in source:
        setup = bone["setup"]
        parent = bone["parent"]
        result: dict[str, Any] = {
            "name": bone["id"],
            "x": _clean(setup["x"]),
            "y": _clean(height - float(setup["y"]) if parent is None else -float(setup["y"])),
            "rotation": _clean(-float(setup["rotation_deg"])),
            "scaleX": 1.0,
            "scaleY": 1.0,
            "length": _clean(setup["length"]),
        }
        if parent is not None:
            result["parent"] = parent
        projected.append(result)
    try:
        world = evaluate_world_setup(rig["bones"])
    except (KeyError, TypeError, ValueError) as exc:
        raise Spine42ContractError(f"P3 setup FK failed: {exc}") from exc
    return Spine42Setup(
        bones=tuple(projected),
        bone_ids=tuple(item["id"] for item in source),
        world=world,
    )


def project_attachment(
    attachment: Mapping[str, Any],
    *,
    slot_bone: str,
    setup: Spine42Setup,
) -> dict[str, Any]:
    """Project a region or weighted mesh attachment without atlas assumptions."""

    if attachment["type"] == "region":
        return _project_region(attachment, slot_bone=slot_bone, setup=setup)
    if attachment["type"] == "mesh":
        return _project_mesh(attachment, setup=setup)
    raise Spine42ContractError("Unsupported attachment type")


def _project_region(attachment, *, slot_bone, setup) -> dict[str, Any]:
    width, height = (float(value) for value in attachment["size"])
    offset_x, offset_y = (float(value) for value in attachment["canvas_offset_xy"])
    local_x, local_y = _bone_local(
        (offset_x + width / 2.0, offset_y + height / 2.0),
        slot_bone,
        setup,
    )
    return {
        "type": "region",
        "path": attachment["id"],
        "x": _clean(local_x),
        "y": _clean(-local_y),
        "rotation": _clean(setup.world[slot_bone]["rotation_deg"]),
        "width": _clean(width),
        "height": _clean(height),
    }


def _project_mesh(attachment, *, setup) -> dict[str, Any]:
    offset_x, offset_y = (float(value) for value in attachment["canvas_offset_xy"])
    bone_index = setup.bone_index
    encoded: list[int | float] = []
    for vertex, influences in zip(attachment["vertices"], attachment["weights"]):
        world_xy = (offset_x + float(vertex[0]), offset_y + float(vertex[1]))
        ordered = sorted(influences, key=lambda item: bone_index[item["bone"]])
        encoded.append(len(ordered))
        for influence in ordered:
            local_x, local_y = _bone_local(world_xy, influence["bone"], setup)
            encoded.extend((
                bone_index[influence["bone"]],
                _clean(local_x),
                _clean(-local_y),
                _clean(influence["weight"]),
            ))
    return {
        "type": "mesh",
        "path": attachment["id"],
        "uvs": [
            _clean(value)
            for point in attachment["uvs"]
            for value in point
        ],
        "triangles": list(attachment["triangles"]),
        "vertices": encoded,
    }


def _bone_local(
    world_xy: Sequence[float],
    bone_id: str,
    setup: Spine42Setup,
) -> tuple[float, float]:
    try:
        frame = setup.world[bone_id]
        return world_to_local_point(
            world_xy,
            frame["origin_xy"],
            frame["rotation_deg"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise Spine42ContractError(
            f"Attachment references unusable setup bone '{bone_id}'"
        ) from exc


def _ordered_bones(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise Spine42ContractError("Bones must be an array")
    by_id = {item["id"]: item for item in value}
    children = {bone_id: [] for bone_id in by_id}
    indegree = {bone_id: 0 for bone_id in by_id}
    for bone_id, bone in by_id.items():
        parent = bone["parent"]
        if parent is not None:
            if parent not in by_id:
                raise Spine42ContractError(f"Bone '{bone_id}' has a missing parent")
            children[parent].append(bone_id)
            indegree[bone_id] += 1
    ready = [bone_id for bone_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        bone_id = heapq.heappop(ready)
        order.append(bone_id)
        for child in sorted(children[bone_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    if len(order) != len(by_id):
        raise Spine42ContractError("Bone hierarchy contains a cycle")
    return [by_id[bone_id] for bone_id in order]


def _clean(value: Any) -> float:
    result = float(value)
    return 0.0 if abs(result) <= 1e-12 else result
