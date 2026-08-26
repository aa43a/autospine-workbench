"""Strict admission for one body-sway structural geometry sample."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any, TypeAlias

from .body_sway_probe_math import BodySwayPoseSample
from .body_sway_probe_profile import NUMERIC_PRECISION_DECIMALS
from .idle_behavior_inventory import BODY_BONE_IDS
from .motion_target_validation import require_motion_target_profile
from .resolved_project import canonical_sha256
from .rig_validation import RigSemanticValidator


MAX_ATTACHMENTS = 4_096
MAX_SAMPLE_TICK = 600_000_000
Point: TypeAlias = tuple[float, float]


class BodySwayProbeGeometryError(ValueError):
    """Raised when one structural sample cannot be evaluated exactly."""


@dataclass(frozen=True, slots=True)
class NormalizedBodySwayStaticGeometryInput:
    bones: tuple[Mapping[str, Any], ...]
    slots: tuple[tuple[str, str], ...]
    attachments: tuple[Mapping[str, Any], ...]
    mesh_targets: tuple[tuple[str, Mapping[str, Any]], ...]
    canvas_size: Point


@dataclass(frozen=True, slots=True)
class NormalizedBodySwayGeometryInput:
    bones: tuple[Mapping[str, Any], ...]
    slots: tuple[tuple[str, str], ...]
    attachments: tuple[Mapping[str, Any], ...]
    mesh_targets: tuple[tuple[str, Mapping[str, Any]], ...]
    canvas_size: Point
    rotations: tuple[tuple[str, float], ...]
    root_translation_xy: Point


def normalize_body_sway_geometry_input(
    rig: Mapping[str, Any],
    target: Mapping[str, Any],
    sample: BodySwayPoseSample,
) -> NormalizedBodySwayGeometryInput:
    """Cross-bind the exact rig/profile and admit finite sample values."""

    static = normalize_body_sway_static_geometry_input(rig, target)
    rotations, translation = normalize_body_sway_pose_sample(
        sample, {row["id"] for row in static.bones}
    )
    return NormalizedBodySwayGeometryInput(
        static.bones, static.slots, static.attachments, static.mesh_targets,
        static.canvas_size, rotations, translation,
    )


def normalize_body_sway_static_geometry_input(
    rig: Mapping[str, Any],
    target: Mapping[str, Any],
) -> NormalizedBodySwayStaticGeometryInput:
    """Cross-bind and validate sample-independent RigIR geometry once."""

    if not isinstance(rig, Mapping) or not isinstance(target, Mapping):
        raise BodySwayProbeGeometryError("Rig and target profile must be objects")
    require_motion_target_profile(target)
    if canonical_sha256(rig) != target["source"]["p3"]["rig_sha256"]:
        raise BodySwayProbeGeometryError("Rig and target profile binding differs")
    canvas = _canvas(rig.get("canvas"))
    if canvas != target["target_space"]["canvas"]:
        raise BodySwayProbeGeometryError("Rig and target canvases differ")
    RigSemanticValidator(max_influences=2).raise_for_errors(rig)
    bones = _objects(rig.get("bones"), "bones", 17)
    indexed = _indexed(bones, "bone")
    _require_target_bones(indexed, target["bones"])
    slots = _slots(rig.get("slots"), set(indexed))
    attachments = _attachments(rig.get("attachments"), dict(slots))
    targets = tuple(
        (row["attachment_id"], row)
        for row in target["mesh_evidence"]["target_inventory"]
    )
    mesh_ids = {row["id"] for row in attachments if row["type"] == "mesh"}
    if mesh_ids != {identifier for identifier, _row in targets}:
        raise BodySwayProbeGeometryError(
            "Rig mesh inventory differs from the target profile"
        )
    return NormalizedBodySwayStaticGeometryInput(
        tuple(bones), slots, tuple(attachments), targets,
        (float(canvas["width"]), float(canvas["height"])),
    )


def normalize_body_sway_pose_sample(
    sample: BodySwayPoseSample, bone_ids: set[str] | frozenset[str],
) -> tuple[tuple[tuple[str, float], ...], Point]:
    """Admit one exact sampled pose against a prepared bone inventory."""

    return _sample(sample, bone_ids)


def number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise BodySwayProbeGeometryError(f"{label} must be finite")
    return float(value)


def point(value: Any, label: str) -> Point:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) \
            or len(value) != 2:
        raise BodySwayProbeGeometryError(f"{label} must contain two numbers")
    return number(value[0], label), number(value[1], label)


def points(value: Any, label: str) -> tuple[Point, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise BodySwayProbeGeometryError(f"{label} must be an array")
    return tuple(point(row, label) for row in value)


def _require_target_bones(bones, target_rows) -> None:
    targets = {row["bone_id"]: row for row in target_rows}
    if set(bones) != set(targets):
        raise BodySwayProbeGeometryError("Rig and target bone inventories differ")
    fields = ("x", "y", "rotation_deg", "scale_x", "scale_y", "length")
    target_fields = (*fields[:-1], "length_px")
    for bone_id, bone in bones.items():
        target, setup = targets[bone_id], bone.get("setup")
        if not isinstance(setup, Mapping) \
                or bone.get("parent") != target["parent_bone_id"]:
            raise BodySwayProbeGeometryError("Rig and target bone setup differs")
        actual = tuple(number(setup.get(field), f"bone {bone_id}")
                       for field in fields)
        expected = tuple(float(target["setup_local"][field])
                         for field in target_fields)
        if any(not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-9)
               for left, right in zip(actual, expected, strict=True)):
            raise BodySwayProbeGeometryError("Rig and target bone setup differs")


def _slots(value, bone_ids) -> tuple[tuple[str, str], ...]:
    result: dict[str, str] = {}
    for row in _objects(value, "slots", MAX_ATTACHMENTS):
        identifier, bone_id = row.get("id"), row.get("bone")
        if not isinstance(identifier, str) or not identifier \
                or identifier in result or not isinstance(bone_id, str) \
                or bone_id not in bone_ids:
            raise BodySwayProbeGeometryError("Rig slot inventory is invalid")
        result[identifier] = bone_id
    return tuple(sorted(result.items()))


def _attachments(value, slots) -> list[Mapping[str, Any]]:
    rows = _objects(value, "attachments", MAX_ATTACHMENTS)
    seen = set()
    for row in rows:
        identifier, kind, slot = row.get("id"), row.get("type"), row.get("slot")
        if not isinstance(identifier, str) or not identifier \
                or identifier in seen or kind not in {"region", "mesh"} \
                or not isinstance(slot, str) or slot not in slots:
            raise BodySwayProbeGeometryError(
                "Rig attachment inventory is invalid"
            )
        seen.add(identifier)
    return rows


def _sample(sample, bone_ids):
    if type(sample) is not BodySwayPoseSample or type(sample.tick) is not int \
            or not 0 <= sample.tick <= MAX_SAMPLE_TICK:
        raise BodySwayProbeGeometryError("Body-sway pose sample is invalid")
    base_ids = _rotation_rows(sample.base_rotation_deg, bone_ids, "base")
    overlay_ids = _rotation_rows(
        sample.overlay_rotation_deg, bone_ids, "overlay"
    )
    combined_ids = _rotation_rows(
        sample.combined_rotation_deg, bone_ids, "combined"
    )
    if base_ids != tuple(sorted(base_ids)) or combined_ids != base_ids \
            or overlay_ids != BODY_BONE_IDS \
            or not set(overlay_ids).issubset(base_ids):
        raise BodySwayProbeGeometryError(
            "Body-sway rotation inventories are inconsistent"
        )
    base, overlay = dict(sample.base_rotation_deg), dict(sample.overlay_rotation_deg)
    for bone_id, combined in sample.combined_rotation_deg:
        expected = round(
            base[bone_id] + overlay.get(bone_id, 0.0),
            NUMERIC_PRECISION_DECIMALS,
        )
        expected = 0.0 if expected == 0.0 else expected
        if combined != expected:
            raise BodySwayProbeGeometryError(
                "Body-sway combined rotations differ from base plus overlay"
            )
    translation = point(sample.root_translation_xy, "root translation")
    for value in translation:
        _sample_number(value, "root translation")
    return (
        tuple((bone, float(value)) for bone, value
              in sample.combined_rotation_deg),
        translation,
    )


def _rotation_rows(value, bone_ids, label):
    if type(value) is not tuple:
        raise BodySwayProbeGeometryError(
            f"Body-sway {label} rotations are invalid"
        )
    seen = set()
    for item in value:
        if type(item) is not tuple or len(item) != 2:
            raise BodySwayProbeGeometryError(
                f"Body-sway {label} rotations are invalid"
            )
        bone_id, numeric = item
        if not isinstance(bone_id, str) or bone_id not in bone_ids \
                or bone_id in seen:
            raise BodySwayProbeGeometryError(f"Body-sway {label} bone is invalid")
        _sample_number(numeric, f"{label} rotation")
        seen.add(bone_id)
    return tuple(item[0] for item in value)


def _sample_number(value, label):
    numeric = number(value, label)
    if round(numeric, NUMERIC_PRECISION_DECIMALS) != numeric \
            or numeric == 0.0 and math.copysign(1.0, numeric) < 0.0:
        raise BodySwayProbeGeometryError(
            f"Body-sway {label} is not canonical 9-decimal input"
        )
    return numeric


def _canvas(value):
    fields = {"width", "height", "origin", "x_axis", "y_axis", "units"}
    if not isinstance(value, Mapping) or set(value) != fields \
            or type(value.get("width")) is not int \
            or type(value.get("height")) is not int \
            or value["width"] < 1 or value["height"] < 1:
        raise BodySwayProbeGeometryError("Rig canvas is invalid")
    return dict(value)


def _objects(value, label, maximum):
    if not isinstance(value, list) or not 0 <= len(value) <= maximum \
            or any(not isinstance(row, Mapping) for row in value):
        raise BodySwayProbeGeometryError(f"Rig {label} inventory is invalid")
    return list(value)


def _indexed(rows, label):
    result = {}
    for row in rows:
        identifier = row.get("id")
        if not isinstance(identifier, str) or not identifier \
                or identifier in result:
            raise BodySwayProbeGeometryError(f"Rig {label} ids are invalid")
        result[identifier] = row
    return result
