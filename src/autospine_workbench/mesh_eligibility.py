"""Fail-closed selection of reviewed region attachments eligible for P3 meshes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SIDES = frozenset({"left", "right"})


class MeshEligibilityError(ValueError):
    """Raised when a reviewed hinge cannot be bound without guessing."""


@dataclass(frozen=True, slots=True)
class HingeTarget:
    """One region attachment and the two-bone chain that may deform it."""

    attachment_id: str
    source_layer_id: str
    side: str
    proximal_bone_id: str
    distal_bone_id: str


def resolve_hinge_targets(
    manifest: Mapping[str, Any],
    base_rig: Mapping[str, Any],
) -> tuple[HingeTarget, ...]:
    """Resolve profile-v1 leg hinges from reviewed P2 inputs.

    The caller supplies an already verified, region-only base RigIR.  This
    function validates only the cross-document relationships needed to decide
    which visible reviewed regions can safely become two-bone meshes.
    """

    manifest = _mapping(manifest, "Layer Manifest")
    base_rig = _mapping(base_rig, "base RigIR")
    _passed_qa(manifest.get("qa"), "Layer Manifest")
    layers = _objects(manifest.get("layers"), "Layer Manifest layers")

    seen_layer_ids: set[str] = set()
    candidates: list[tuple[str, str, str, str]] = []
    for index, layer in enumerate(layers):
        layer_id = _safe_id(layer.get("layer_id"), f"layer {index} id")
        if layer_id in seen_layer_ids:
            raise MeshEligibilityError(f"duplicate Layer Manifest id: {layer_id}")
        seen_layer_ids.add(layer_id)
        _passed_qa(layer.get("qa"), f"layer {layer_id}")

        hint = _mapping(layer.get("rig_hint"), f"layer {layer_id} rig hint")
        if hint.get("attachment_kind") == "excluded":
            continue
        if not (
            hint.get("attachment_kind") == "region"
            and hint.get("deform_class") == "hinge"
        ):
            continue

        source = _mapping(layer.get("source"), f"layer {layer_id} source")
        if source.get("visible") is not True:
            raise MeshEligibilityError(f"hinge layer {layer_id} must be visible")
        semantic = _mapping(layer.get("semantic"), f"layer {layer_id} semantic")
        role = semantic.get("canonical_role")
        if role != "body.leg":
            raise MeshEligibilityError(
                f"hinge layer {layer_id} has unsupported profile-v1 role: {role}"
            )
        side = semantic.get("side")
        if side not in _SIDES:
            raise MeshEligibilityError(
                f"hinge layer {layer_id} must have left or right side"
            )
        proximal, distal = f"thigh.{side}", f"calf.{side}"
        if hint.get("candidate_bone") != proximal:
            raise MeshEligibilityError(
                f"hinge layer {layer_id} candidate bone must be {proximal}"
            )
        candidates.append((layer_id, side, proximal, distal))

    if not candidates:
        return ()

    bones = _index_by_id(base_rig.get("bones"), "base RigIR bones")
    slots = _index_by_id(base_rig.get("slots"), "base RigIR slots")
    attachments = _index_by_id(
        base_rig.get("attachments"), "base RigIR attachments"
    )
    default_skin = _mapping(
        _mapping(base_rig.get("skins"), "base RigIR skins").get("default"),
        "base RigIR default skin",
    )
    candidate_ids = {item[0] for item in candidates}
    attachments_by_source: dict[str, list[Mapping[str, Any]]] = {
        layer_id: [] for layer_id in candidate_ids
    }
    for attachment in attachments.values():
        source_ids = attachment.get("source_layer_ids")
        if not _sequence(source_ids):
            continue
        for source_id in source_ids:
            if isinstance(source_id, str) and source_id in attachments_by_source:
                attachments_by_source[source_id].append(attachment)

    targets: list[HingeTarget] = []
    for layer_id, side, proximal, distal in candidates:
        if proximal not in bones:
            raise MeshEligibilityError(
                f"hinge layer {layer_id} references missing proximal bone: {proximal}"
            )
        distal_bone = bones.get(distal)
        if distal_bone is None:
            raise MeshEligibilityError(
                f"hinge layer {layer_id} has no distal child bone: {distal}"
            )
        if distal_bone.get("parent") != proximal:
            raise MeshEligibilityError(
                f"hinge distal bone {distal} is not a direct child of {proximal}"
            )

        matches = attachments_by_source[layer_id]
        if len(matches) != 1:
            raise MeshEligibilityError(
                f"source layer {layer_id} must bind exactly one base attachment"
            )
        attachment = matches[0]
        attachment_id = _safe_id(
            attachment.get("id"), f"source layer {layer_id} attachment id"
        )
        if (
            attachment_id != layer_id
            or attachment.get("type") != "region"
            or attachment.get("source_layer_ids") != [layer_id]
        ):
            raise MeshEligibilityError(
                f"source layer {layer_id} base attachment binding is inconsistent"
            )
        slot_id = _safe_id(
            attachment.get("slot"), f"attachment {attachment_id} slot id"
        )
        if slot_id != attachment_id:
            raise MeshEligibilityError(
                f"hinge attachment {attachment_id} slot id is inconsistent"
            )
        slot = slots.get(slot_id)
        if slot is None:
            raise MeshEligibilityError(
                f"attachment {attachment_id} references missing slot: {slot_id}"
            )
        if slot.get("bone") != proximal:
            raise MeshEligibilityError(
                f"hinge slot {slot_id} bone must be {proximal}"
            )
        if slot.get("setup_attachment") != attachment_id:
            raise MeshEligibilityError(
                f"hinge slot {slot_id} setup attachment is inconsistent"
            )
        if default_skin.get(slot_id) != [attachment_id]:
            raise MeshEligibilityError(
                f"hinge slot {slot_id} default skin binding is inconsistent"
            )
        targets.append(
            HingeTarget(
                attachment_id=attachment_id,
                source_layer_id=layer_id,
                side=side,
                proximal_bone_id=proximal,
                distal_bone_id=distal,
            )
        )
    return tuple(sorted(targets, key=lambda item: (item.source_layer_id, item.attachment_id)))


def _index_by_id(value: Any, label: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(_objects(value, label)):
        item_id = _safe_id(item.get("id"), f"{label} item {index} id")
        if item_id in result:
            raise MeshEligibilityError(f"{label} contains duplicate id: {item_id}")
        result[item_id] = item
    return result


def _passed_qa(value: Any, label: str) -> None:
    if not isinstance(value, Mapping) or value.get("status") != "passed":
        raise MeshEligibilityError(f"{label} QA must be passed")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MeshEligibilityError(f"{label} must be an object")
    return value


def _objects(value: Any, label: str) -> tuple[Mapping[str, Any], ...]:
    if not _sequence(value):
        raise MeshEligibilityError(f"{label} must be an array")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise MeshEligibilityError(f"{label} item {index} must be an object")
        result.append(item)
    return tuple(result)


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise MeshEligibilityError(f"{label} must be a safe id")
    return value


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    )
