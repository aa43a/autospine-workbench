"""Canonical setup evidence inventory for idle-behavior classification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import re
from typing import Any


BODY_BONE_IDS = ("pelvis-spine", "spine-chest", "chest-neck", "neck-head")
_BODY_PARENTS = {
    "pelvis-spine": "root-pelvis",
    "spine-chest": "pelvis-spine",
    "chest-neck": "spine-chest",
    "neck-head": "chest-neck",
}
_BODY_ROLES = {
    "humanoid.spine.lower": "pelvis-spine",
    "humanoid.spine.upper": "spine-chest",
    "humanoid.neck": "chest-neck",
    "humanoid.head": "neck-head",
}
_FEATURES = ("blink", "body_sway", "hair_spring", "mouth")
_SIDES = {"left", "right", "center", "bilateral", "unknown"}
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


class IdleBehaviorInventoryError(ValueError):
    """Raised when setup evidence cannot be inventoried unambiguously."""


@dataclass(frozen=True, slots=True)
class IdleBehaviorInventory:
    """Frozen internal evidence; public output is built by the rule layer."""

    _json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._json)

    @property
    def target_inventory(self) -> list[dict[str, str]]:
        return self.document["target_inventory"]


def derive_idle_behavior_inventory(
    manifest: Mapping[str, Any],
    rig: Mapping[str, Any],
    target_profile: Mapping[str, Any],
    motion_instance_v2: Mapping[str, Any],
) -> IdleBehaviorInventory:
    """Join reviewed layer semantics to current P3 bindings and P9 tracks."""

    try:
        layers = _layers(manifest.get("layers"))
        bones = _bones(rig.get("bones"))
        bindings = _bindings(rig, bones)
        target_inventory = _target_inventory(target_profile.get("bones"))
        tracks = _tracks(motion_instance_v2.get("tracks"))
        feature_rows: dict[str, Any] = {}
        for feature_id in _FEATURES:
            if feature_id == "body_sway":
                evidence = _body_evidence(bones, target_inventory, tracks)
                feature_rows[feature_id] = {
                    "evidence": evidence,
                    "has_layers": True,
                    "all_layers_reviewed": True,
                    "all_layers_bound": True,
                    "hair_mesh_present": False,
                    "body_chain_complete": _body_chain_complete(
                        bones, target_inventory
                    ),
                }
                continue
            selected = [row for row in layers if _matches(feature_id, row["role"])]
            evidence, bound_layer_ids = _layer_evidence(selected, bindings, tracks)
            feature_rows[feature_id] = {
                "evidence": evidence,
                "has_layers": bool(selected),
                "all_layers_reviewed": bool(selected) and all(
                    row["review_state"] == "reviewed" for row in selected
                ),
                "all_layers_bound": bool(selected) and all(
                    row["layer_id"] in bound_layer_ids for row in selected
                ),
                "hair_mesh_present": any(
                    item["type"] == "mesh" for item in evidence["bindings"]
                ),
                "body_chain_complete": False,
            }
        document = {
            "target_inventory": target_inventory,
            "features": feature_rows,
        }
        return IdleBehaviorInventory(_canonical(document))
    except IdleBehaviorInventoryError:
        raise
    except (KeyError, OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise IdleBehaviorInventoryError(
            f"Idle behavior inventory failed: {exc}"
        ) from exc


def _layers(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 4096:
        raise IdleBehaviorInventoryError("Layer inventory is invalid")
    result, seen = [], set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise IdleBehaviorInventoryError("Layer evidence must be an object")
        layer_id = _identifier(raw.get("layer_id"), "layer id")
        if layer_id in seen:
            raise IdleBehaviorInventoryError("Layer ids are duplicated")
        seen.add(layer_id)
        semantic, raster = raw.get("semantic"), raw.get("raster")
        source, qa, hint = raw.get("source"), raw.get("qa"), raw.get("rig_hint")
        if any(not isinstance(item, Mapping) for item in (
                semantic, raster, source, qa, hint)):
            raise IdleBehaviorInventoryError("Layer evidence shape is invalid")
        role = _identifier(semantic.get("canonical_role"), "canonical role")
        side = semantic.get("side")
        if side not in _SIDES or type(source.get("visible")) is not bool:
            raise IdleBehaviorInventoryError("Layer side or visibility is invalid")
        raster_sha = _digest(raster.get("sha256"), "layer raster")
        pivot = hint.get("pivot")
        pivot_reviewed = isinstance(pivot, Mapping) \
            and pivot.get("method") == "manual"
        reviewed = qa.get("status") == "passed" \
            and semantic.get("mapping_method") == "manual" \
            and isinstance(hint.get("candidate_bone"), str) \
            and pivot_reviewed
        result.append({
            "layer_id": layer_id, "role": role, "side": side,
            "raster_sha256": raster_sha,
            "review_state": "reviewed" if reviewed else "unreviewed",
        })
    return sorted(result, key=lambda item: item["layer_id"])


def _bones(value: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) > 4096:
        raise IdleBehaviorInventoryError("P3 bone inventory is invalid")
    result = {}
    for raw in value:
        if not isinstance(raw, Mapping):
            raise IdleBehaviorInventoryError("P3 bone must be an object")
        bone_id = _identifier(raw.get("id"), "P3 bone id")
        if bone_id in result:
            raise IdleBehaviorInventoryError("P3 bone ids are duplicated")
        result[bone_id] = raw
    return result


def _bindings(rig, bones) -> dict[str, list[dict[str, str]]]:
    raw_slots, raw_attachments = rig.get("slots"), rig.get("attachments")
    if not isinstance(raw_slots, list) or not isinstance(raw_attachments, list):
        raise IdleBehaviorInventoryError("P3 setup binding inventory is invalid")
    slots = {}
    for raw in raw_slots:
        if not isinstance(raw, Mapping):
            raise IdleBehaviorInventoryError("P3 slot must be an object")
        slot_id = _identifier(raw.get("id"), "slot id")
        bone_id = _identifier(raw.get("bone"), "slot bone id")
        if slot_id in slots or bone_id not in bones:
            raise IdleBehaviorInventoryError("P3 slot binding is invalid")
        slots[slot_id] = bone_id
    result: dict[str, list[dict[str, str]]] = {}
    seen = set()
    for raw in raw_attachments:
        if not isinstance(raw, Mapping):
            raise IdleBehaviorInventoryError("P3 attachment must be an object")
        attachment_id = _identifier(raw.get("id"), "attachment id")
        slot_id = _identifier(raw.get("slot"), "attachment slot id")
        kind = raw.get("type")
        sources = raw.get("source_layer_ids")
        if attachment_id in seen or slot_id not in slots \
                or kind not in {"region", "mesh"} \
                or not isinstance(sources, list) or not sources:
            raise IdleBehaviorInventoryError("P3 attachment binding is invalid")
        seen.add(attachment_id)
        binding = {
            "attachment_id": attachment_id, "slot_id": slot_id,
            "bone_id": slots[slot_id],
            "image_sha256": _digest(raw.get("image_sha256"), "attachment image"),
            "type": kind,
        }
        for source_id in sources:
            source_id = _identifier(source_id, "attachment source layer id")
            result.setdefault(source_id, []).append(binding)
    return result


def _target_inventory(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise IdleBehaviorInventoryError("P5 target inventory is invalid")
    result, roles, bones = [], set(), set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise IdleBehaviorInventoryError("P5 target bone must be an object")
        role = _identifier(raw.get("role"), "target role")
        bone_id = _identifier(raw.get("bone_id"), "target bone id")
        if role in roles or bone_id in bones:
            raise IdleBehaviorInventoryError("P5 target inventory is duplicated")
        roles.add(role)
        bones.add(bone_id)
        result.append({"role": role, "bone_id": bone_id})
    return result


def _tracks(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise IdleBehaviorInventoryError("P9 track inventory is invalid")
    result = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise IdleBehaviorInventoryError("P9 track must be an object")
        bone_id = _identifier(raw.get("bone_id"), "track bone id")
        prop = raw.get("property")
        if prop not in {"rotation", "translation"}:
            raise IdleBehaviorInventoryError("P9 track property is unsupported")
        result.append({"bone_id": bone_id, "property": prop})
    keys = [(item["bone_id"], item["property"]) for item in result]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise IdleBehaviorInventoryError("P9 tracks are not canonical")
    return result


def _layer_evidence(selected, bindings, tracks):
    layers = [{
        "layer_id": row["layer_id"], "canonical_role": row["role"],
        "side": row["side"], "raster_sha256": row["raster_sha256"],
        "review_state": row["review_state"],
    } for row in selected]
    binding_rows, bound = {}, set()
    for layer in selected:
        for binding in bindings.get(layer["layer_id"], []):
            if binding["image_sha256"] == layer["raster_sha256"]:
                binding_rows[binding["attachment_id"]] = dict(binding)
                bound.add(layer["layer_id"])
    ordered = [binding_rows[key] for key in sorted(binding_rows)]
    bone_ids = sorted({row["bone_id"] for row in ordered})
    existing = [row for row in tracks if row["bone_id"] in bone_ids]
    return {
        "layers": layers, "bindings": ordered, "bone_ids": bone_ids,
        "existing_tracks": existing,
    }, bound


def _body_evidence(bones, target_inventory, tracks):
    target_ids = {row["bone_id"] for row in target_inventory}
    bone_ids = sorted(set(BODY_BONE_IDS) & set(bones) & target_ids)
    return {
        "layers": [], "bindings": [], "bone_ids": bone_ids,
        "existing_tracks": [row for row in tracks if row["bone_id"] in bone_ids],
    }


def _body_chain_complete(bones, target_inventory) -> bool:
    target_by_role = {
        row["role"]: row["bone_id"] for row in target_inventory
    }
    return all(target_by_role.get(role) == bone_id
               for role, bone_id in _BODY_ROLES.items()) and all(
        bone_id in bones
        and bones[bone_id].get("parent") == parent
        for bone_id, parent in _BODY_PARENTS.items()
    )


def _matches(feature_id: str, role: str) -> bool:
    if feature_id == "blink":
        return role in {"face.eyelash", "face.eye.white", "face.eye.iris"}
    if feature_id == "mouth":
        return role == "face.mouth" or role.startswith("face.mouth.")
    return feature_id == "hair_spring" and role.startswith("hair.")


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise IdleBehaviorInventoryError(f"{label} is invalid")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise IdleBehaviorInventoryError(f"{label} is not a SHA-256")
    return value


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
