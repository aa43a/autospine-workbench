"""Build fresh 4.3 JSON using the audited common geometry and timeline subset.

    Format audit: official spine-runtimes/4.3 spine-core/src/SkeletonJson.ts.
    Slot attachment names and skin attachment maps remain unchanged. Constraints
    moved to a unified root array; no old constraint arrays are ever forwarded.
"""
import json

from ...resolved_project import canonical_sha256
from ...spine42_geometry import project_attachment, project_setup
from .contract import (
    SPINE_JSON_VERSION, Spine43ContractError, canonical_spine43_json,
    require_spine43_inputs, spine43_target_profile,
)


def build_spine43_json(rig, *, motion_instance=None, target_profile=None):
    require_spine43_inputs(rig, motion_instance=motion_instance, target_profile=target_profile)
    try:
        return _build(rig, motion_instance, target_profile)
    except Spine43ContractError:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError, OverflowError) as exc:
        raise Spine43ContractError("spine43_document_invalid") from exc


def _build(rig, motion, target):
    from .validation import require_projected_spine43_document

    setup = project_setup(rig)
    ordered = sorted(rig["slots"], key=lambda row: (row["setup_draw_order"], row["id"]))
    slots = []
    for row in ordered:
        slot = {"name": row["id"], "bone": row["bone"],
                "color": row["color_rgba"].lower(), "blend": row["blend"]}
        if row["setup_attachment"] is not None:
            slot["attachment"] = row["setup_attachment"]
        slots.append(slot)
    attachments = {row["id"]: row for row in rig["attachments"]}
    used, skins = set(), []
    for skin in ["default", *sorted(set(rig["skins"]) - {"default"})]:
        skin_slots = {}
        for slot in ordered:
            if slot["id"] not in rig["skins"][skin]:
                continue
            skin_slots[slot["id"]] = {}
            for name in sorted(rig["skins"][skin][slot["id"]]):
                skin_slots[slot["id"]][name] = project_attachment(
                    attachments[name], slot_bone=slot["bone"], setup=setup,
                )
                used.add(name)
        skins.append({"name": skin, "attachments": skin_slots})
    if used != set(attachments):
        raise Spine43ContractError("spine43_attachment_membership_invalid")
    events, animations = _motion(motion)
    source = {
        "adapter_profile": spine43_target_profile(), "rig_sha256": canonical_sha256(rig),
        "motion_instance_sha256": canonical_sha256(motion) if motion is not None else None,
        "target_profile_sha256": canonical_sha256(target) if target is not None else None,
    }
    document = {
        "skeleton": {"hash": canonical_sha256(source), "spine": SPINE_JSON_VERSION,
                     "x": 0.0, "y": 0.0, "width": float(rig["canvas"]["width"]),
                     "height": float(rig["canvas"]["height"])},
        "bones": [dict(row) for row in setup.bones], "slots": slots,
        "constraints": [], "skins": skins, "events": events, "animations": animations,
    }
    require_projected_spine43_document(document)
    return json.loads(canonical_spine43_json(document))


def _motion(instance):
    if instance is None:
        return {}, {}
    tick_rate = instance["timing"]["ticks_per_second"]
    bones, frames, names = {}, [], set()
    for track in instance["tracks"]:
        keys = []
        rotation = track["property"] == "rotation"
        for key in track["keys"]:
            frame = {"time": _clean(key["tick"] / tick_rate)}
            if rotation:
                frame["value"] = _clean(-float(key["value"]))
            else:
                frame.update(x=_clean(key["value"][0]), y=_clean(-float(key["value"][1])))
            keys.append(frame)
        bones.setdefault(track["bone_id"], {})["rotate" if rotation else "translate"] = keys
    for marker in instance["markers"]:
        for boundary in ("start", "end"):
            name = f"contact.{marker['limb']}.{boundary}"
            names.add(name)
            frames.append({"time": _clean(marker[f"{boundary}_tick"] / tick_rate), "name": name})
    animation = {"bones": bones}
    if frames:
        animation["events"] = sorted(frames, key=lambda row: (row["time"], row["name"]))
    return {name: {} for name in sorted(names)}, {instance["clip_id"]: animation}


def _clean(value):
    value = float(value)
    return 0.0 if abs(value) <= 1e-12 else value


def build_spine43_json_bytes(rig, *, motion_instance=None, target_profile=None):
    return canonical_spine43_json(build_spine43_json(
        rig, motion_instance=motion_instance, target_profile=target_profile,
    ))
