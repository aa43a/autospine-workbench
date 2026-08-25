"""Region, pivot, and draw-order checks used by the setup probe runner."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .rig_fk import RigFkError, evaluate_world_setup, local_to_world_point, world_to_local_point


TOLERANCE = 1e-6


def run_region_checks(
    rig: Mapping[str, Any],
    manifest: Mapping[str, Any],
    resolved: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        _binding_check(rig, manifest, resolved),
        _pivot_check(rig, manifest),
        _draw_order_check(rig, manifest),
    ]


def region_layers(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        _text(layer.get("layer_id")): layer
        for layer in _objects(manifest.get("layers"))
        if (layer.get("rig_hint") or {}).get("attachment_kind") == "region"
        and _text(layer.get("layer_id"))
    }


def _binding_check(rig, manifest, resolved) -> dict[str, Any]:
    errors: list[str] = []
    bones = _by_id(rig.get("bones"), "bone", errors)
    slots = _by_id(rig.get("slots"), "slot", errors)
    attachments = _by_id(rig.get("attachments"), "attachment", errors)
    source_bones, bones_by_end_joint = _resolved_bones(resolved, errors)
    expected_layers = region_layers(manifest)
    found_layers: dict[str, str] = {}
    capabilities = rig.get("capabilities") or []
    if "region_attachment" not in capabilities or "mesh_attachment" in capabilities:
        errors.append("capabilities do not declare a region-only rig")
    for attachment_id, attachment in sorted(attachments.items()):
        if attachment.get("type") != "region":
            errors.append(f"attachment {attachment_id} is not region-only")
        source_ids = attachment.get("source_layer_ids")
        if not isinstance(source_ids, list) or len(source_ids) != 1 or not isinstance(source_ids[0], str):
            errors.append(f"attachment {attachment_id} must bind exactly one source layer")
            continue
        layer_id = source_ids[0]
        if layer_id in found_layers:
            errors.append(f"source layer {layer_id} is bound more than once")
        found_layers[layer_id] = attachment_id
        layer = expected_layers.get(layer_id)
        if layer is None:
            errors.append(f"attachment {attachment_id} binds a non-region layer")
        else:
            _compare_raster(attachment_id, attachment, layer, errors)
        slot_id = attachment.get("slot")
        slot = slots.get(slot_id)
        expected_setup = (
            attachment_id
            if layer is not None and bool((layer.get("source") or {}).get("visible"))
            else None
        )
        if slot is None or slot.get("setup_attachment") != expected_setup:
            errors.append(f"attachment {attachment_id} slot binding is inconsistent")
        else:
            if slot.get("bone") not in bones:
                errors.append(f"slot {slot_id} references a missing bone")
            if layer is not None:
                expected_bone = _resolve_manifest_bone(
                    layer_id, layer, source_bones, bones_by_end_joint, errors
                )
                if expected_bone is not None and slot.get("bone") != expected_bone:
                    errors.append(
                        f"slot {slot_id} bone does not match manifest layer {layer_id}"
                    )
                _compare_slot_style(slot_id, slot, layer, errors)
        skin_items = ((rig.get("skins") or {}).get("default") or {}).get(slot_id)
        if not isinstance(skin_items, list) or attachment_id not in skin_items:
            errors.append(f"attachment {attachment_id} is missing from default skin")
    if set(found_layers) != set(expected_layers):
        errors.append("region attachment layers do not exactly match manifest")
    if set(slots) != {item.get("slot") for item in attachments.values()}:
        errors.append("slots and attachments are not one-to-one")
    return _check(
        "attachments.region-bindings",
        errors,
        metrics={"attachment_count": len(attachments), "region_count": len(expected_layers)},
    )


def _pivot_check(rig: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    max_error = 0.0
    layers = region_layers(manifest)
    slots = _by_id(rig.get("slots"), "slot", errors)
    try:
        worlds = evaluate_world_setup(rig.get("bones"))
    except (RigFkError, TypeError, ValueError) as exc:
        worlds = {}
        errors.append(f"FK evaluation failed: {exc}")
    for attachment in _objects(rig.get("attachments")):
        attachment_id = _text(attachment.get("id"))
        source_ids = attachment.get("source_layer_ids") or []
        layer = layers.get(source_ids[0]) if len(source_ids) == 1 else None
        expected = ((layer or {}).get("rig_hint") or {}).get("pivot") or {}
        pivot = attachment.get("pivot_xy")
        try:
            pivot_error = _distance(pivot, expected.get("xy"))
            max_error = max(max_error, pivot_error)
            if pivot_error > TOLERANCE:
                errors.append(f"attachment {attachment_id} pivot does not match manifest")
            slot = slots.get(attachment.get("slot")) or {}
            world = worlds[slot.get("bone")]
            local = world_to_local_point(pivot, world["origin_xy"], world["rotation_deg"])
            restored = local_to_world_point(local, world["origin_xy"], world["rotation_deg"])
            roundtrip = _distance(restored, pivot)
            max_error = max(max_error, roundtrip)
            if roundtrip > TOLERANCE:
                errors.append(f"attachment {attachment_id} pivot round-trip failed")
        except (KeyError, RigFkError, TypeError, ValueError, IndexError) as exc:
            errors.append(f"attachment {attachment_id} pivot cannot be evaluated: {exc}")
    return _check("attachments.pivot-roundtrip", errors, metrics={"max_error_px": max_error})


def _draw_order_check(rig: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    attachments = _by_id(rig.get("attachments"), "attachment", errors)
    attachments_by_slot: dict[str, Mapping[str, Any]] = {}
    for attachment in attachments.values():
        slot_id = _text(attachment.get("slot"))
        if slot_id in attachments_by_slot:
            errors.append(f"slot {slot_id} has multiple attachments")
        attachments_by_slot[slot_id] = attachment
    actual: list[tuple[int, str]] = []
    seen: set[int] = set()
    expected: list[tuple[int, str]] = []
    expected_by_layer: dict[str, int] = {}
    expected_orders: set[int] = set()
    for layer_id, layer in region_layers(manifest).items():
        order = (layer.get("rig_hint") or {}).get("setup_draw_order")
        if isinstance(order, bool) or not isinstance(order, int):
            errors.append(f"layer {layer_id} has invalid setup draw order")
            continue
        if order in expected_orders:
            errors.append(f"manifest setup draw order is ambiguous at {order}")
        expected_orders.add(order)
        expected_by_layer[layer_id] = order
        expected.append((order, layer_id))
    for slot in _objects(rig.get("slots")):
        order = slot.get("setup_draw_order")
        attachment = attachments_by_slot.get(_text(slot.get("id"))) or {}
        source_ids = attachment.get("source_layer_ids") or []
        if isinstance(order, bool) or not isinstance(order, int) or len(source_ids) != 1:
            errors.append(f"slot {_text(slot.get('id'))} has invalid draw-order binding")
            continue
        if order in seen:
            errors.append(f"duplicate setup draw order: {order}")
        seen.add(order)
        layer_id = source_ids[0]
        actual.append((order, layer_id))
        expected_order = expected_by_layer.get(layer_id)
        if expected_order is not None and order != expected_order:
            errors.append(
                f"slot {_text(slot.get('id'))} draw order does not match "
                f"manifest layer {layer_id}"
            )
    if [item[1] for item in sorted(actual)] != [item[1] for item in sorted(expected)]:
        errors.append("slot draw order does not preserve manifest relative order")
    return _check("slots.draw-order", errors, metrics={"slot_count": len(actual)})


def _resolved_bones(resolved, errors: list[str]):
    skeleton = resolved.get("skeleton") if isinstance(resolved, Mapping) else None
    source_bones = _by_id((skeleton or {}).get("bones"), "resolved bone", errors)
    by_end_joint: dict[str, list[str]] = {}
    for bone_id, bone in source_bones.items():
        end_joint = _text(bone.get("end_joint_id"))
        if not end_joint:
            errors.append(f"resolved bone {bone_id} has an invalid end joint")
            continue
        by_end_joint.setdefault(end_joint, []).append(bone_id)
    return source_bones, by_end_joint


def _resolve_manifest_bone(
    layer_id: str,
    layer: Mapping[str, Any],
    source_bones: Mapping[str, Mapping[str, Any]],
    bones_by_end_joint: Mapping[str, list[str]],
    errors: list[str],
) -> str | None:
    hint = (layer.get("rig_hint") or {}).get("candidate_bone")
    if hint is None:
        return None
    if isinstance(hint, str) and hint in source_bones:
        return hint
    matches = bones_by_end_joint.get(hint, []) if isinstance(hint, str) else []
    if len(matches) == 1:
        return matches[0]
    reason = "ambiguous legacy joint" if len(matches) > 1 else "missing or unknown"
    errors.append(f"manifest layer {layer_id} candidate_bone is {reason}")
    return None


def _compare_slot_style(
    slot_id: Any,
    slot: Mapping[str, Any],
    layer: Mapping[str, Any],
    errors: list[str],
) -> None:
    source = layer.get("source") or {}
    if slot.get("blend") != source.get("blend_mode"):
        errors.append(f"slot {slot_id} blend does not match manifest")
    opacity = source.get("opacity")
    if (
        isinstance(opacity, bool)
        or not isinstance(opacity, (int, float))
        or not math.isfinite(float(opacity))
        or not 0 <= float(opacity) <= 1
    ):
        errors.append(f"slot {slot_id} cannot derive color from manifest opacity")
        return
    alpha = math.floor(float(opacity) * 255 + 0.5)
    if slot.get("color_rgba") != f"ffffff{alpha:02x}":
        errors.append(f"slot {slot_id} color does not match manifest opacity")


def _compare_raster(
    attachment_id: str,
    attachment: Mapping[str, Any],
    layer: Mapping[str, Any],
    errors: list[str],
) -> None:
    raster = layer.get("raster") or {}
    bbox = raster.get("crop_bbox_xywh") or []
    expected = {
        "image_path": raster.get("artifact_path"),
        "image_sha256": raster.get("sha256"),
        "canvas_offset_xy": raster.get("canvas_offset_xy"),
    }
    for field, value in expected.items():
        if attachment.get(field) != value:
            errors.append(f"attachment {attachment_id}.{field} does not match manifest")
    size, offset = attachment.get("size"), attachment.get("canvas_offset_xy")
    canvas = raster.get("canvas_size")
    cropped = len(bbox) == 4 and size == bbox[2:4] and offset == bbox[:2]
    full_canvas = size == canvas and offset == [0, 0]
    if not cropped and not full_canvas:
        errors.append(f"attachment {attachment_id}.size is not aligned to manifest raster")


def _by_id(value: Any, label: str, errors: list[str]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in _objects(value):
        item_id = _text(item.get("id"))
        if not item_id:
            errors.append(f"{label} has an invalid id")
        elif item_id in result:
            errors.append(f"duplicate {label} id: {item_id}")
        else:
            result[item_id] = item
    return result


def _objects(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _distance(first: Any, second: Any) -> float:
    if not isinstance(first, Sequence) or not isinstance(second, Sequence) or len(first) != 2 or len(second) != 2:
        raise ValueError("point must contain two numbers")
    values = [first[0], first[1], second[0], second[1]]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise ValueError("point must contain finite numbers")
    if any(not math.isfinite(float(value)) for value in values):
        raise ValueError("point must contain finite numbers")
    return math.hypot(float(first[0]) - float(second[0]), float(first[1]) - float(second[1]))


def _check(check_id: str, messages: Sequence[str], *, metrics: Mapping[str, Any]) -> dict[str, Any]:
    unique = sorted(set(messages))
    result: dict[str, Any] = {"id": check_id, "status": "rejected" if unique else "passed"}
    if unique:
        result["message"] = "; ".join(unique)
    result["metrics"] = dict(metrics)
    return result


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""
