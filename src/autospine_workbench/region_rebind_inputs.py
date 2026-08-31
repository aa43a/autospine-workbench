"""Strict admission for sampled region rebind candidate compilation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
import re
from types import MappingProxyType
from typing import Any

from .body_sway_probe_geometry_inputs import normalize_body_sway_pose_sample
from .body_sway_probe_math import BodySwayPoseSample
from .region_rebind_profile import (
    MAX_CANDIDATE_BONES,
    MAX_MOTION_SAMPLES,
    MAX_RIG_ENTITIES,
)
from .rig_validation import RigSemanticValidator


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class RegionRebindInputError(ValueError):
    """Raised when region, rig, sample, or candidate inputs are invalid."""


@dataclass(frozen=True, slots=True)
class AdmittedRegionRebindInputs:
    bones: Mapping[str, Mapping[str, Any]]
    attachment: Mapping[str, Any]
    slot_id: str
    current_bone_id: str
    candidate_bone_ids: tuple[str, ...]
    samples: tuple[
        tuple[BodySwayPoseSample, tuple[tuple[str, float], ...], tuple[float, float]],
        ...,
    ]
    corners_xy: tuple[tuple[float, float], ...]
    canvas_size: tuple[float, float]


def admit_region_rebind_inputs(
    rig: Mapping[str, Any],
    motion_samples: Sequence[BodySwayPoseSample],
    attachment_id: str,
    candidate_bone_ids: Sequence[str] | None,
) -> AdmittedRegionRebindInputs:
    """Validate exact RigIR, one region, increasing samples, and one-hop scope."""

    if not isinstance(rig, Mapping):
        raise RegionRebindInputError("rig must be an object")
    RigSemanticValidator(max_influences=2).raise_for_errors(rig)
    bones = _index(rig.get("bones"), "bone")
    slots = _index(rig.get("slots"), "slot")
    attachments = _index(rig.get("attachments"), "attachment")
    attachment = attachments.get(safe_identifier(attachment_id, "attachment_id"))
    if attachment is None or attachment.get("type") != "region":
        raise RegionRebindInputError(
            "attachment_id must identify one region attachment"
        )
    slot = slots.get(attachment.get("slot"))
    if slot is None or slot.get("bone") not in bones:
        raise RegionRebindInputError("region slot binding is invalid")
    current = slot["bone"]
    return AdmittedRegionRebindInputs(
        bones=MappingProxyType(bones),
        attachment=MappingProxyType(dict(attachment)),
        slot_id=slot["id"],
        current_bone_id=current,
        candidate_bone_ids=_candidate_inventory(
            current, bones, candidate_bone_ids,
        ),
        samples=_samples(motion_samples, frozenset(bones)),
        corners_xy=_region_corners(attachment),
        canvas_size=_canvas(rig.get("canvas")),
    )


def safe_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise RegionRebindInputError(f"{label} is invalid")
    return value


def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RegionRebindInputError(f"{label} is invalid")
    return value


def relationship(current: str, candidate: str, bones) -> str:
    if candidate == current:
        return "current"
    if bones[current].get("parent") == candidate:
        return "parent"
    return "child"


def _candidate_inventory(current, bones, requested):
    parent = bones[current].get("parent")
    allowed = {
        current,
        *(bone for bone, row in bones.items() if row.get("parent") == current),
    }
    if isinstance(parent, str):
        allowed.add(parent)
    values = tuple(allowed) if requested is None else requested
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) \
            or not values or len(values) > MAX_CANDIDATE_BONES:
        raise RegionRebindInputError("candidate bone inventory is invalid")
    result = tuple(sorted(safe_identifier(value, "candidate bone") for value in values))
    if len(set(result)) != len(result) or current not in result \
            or not set(result).issubset(allowed):
        raise RegionRebindInputError(
            "candidate bones must include current and be one-hop chain neighbors"
        )
    return result


def _samples(value, bone_ids):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) \
            or not 2 <= len(value) <= MAX_MOTION_SAMPLES:
        raise RegionRebindInputError("motion sample inventory is invalid")
    result, previous = [], -1
    for sample in value:
        rotations, translation = normalize_body_sway_pose_sample(sample, bone_ids)
        if sample.tick <= previous:
            raise RegionRebindInputError("motion sample ticks must increase")
        result.append((sample, rotations, translation))
        previous = sample.tick
    return tuple(result)


def _region_corners(row):
    x, y = _point(row.get("canvas_offset_xy"), "region offset")
    width, height = _point(row.get("size"), "region size")
    if width <= 0 or height <= 0:
        raise RegionRebindInputError("region size must be positive")
    return ((x, y), (x + width, y), (x + width, y + height), (x, y + height))


def _canvas(value):
    if not isinstance(value, Mapping):
        raise RegionRebindInputError("rig canvas is invalid")
    width, height = value.get("width"), value.get("height")
    if type(width) is not int or type(height) is not int or width < 1 or height < 1:
        raise RegionRebindInputError("rig canvas is invalid")
    return float(width), float(height)


def _point(value, label):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) \
            or len(value) != 2:
        raise RegionRebindInputError(f"{label} must contain two numbers")
    try:
        result = tuple(float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise RegionRebindInputError(f"{label} must be numeric") from exc
    if not all(math.isfinite(item) for item in result):
        raise RegionRebindInputError(f"{label} must be finite")
    return result


def _index(value, label):
    if not isinstance(value, list) or len(value) > MAX_RIG_ENTITIES:
        raise RegionRebindInputError(f"rig {label}s must be an array")
    result = {}
    for row in value:
        if not isinstance(row, Mapping):
            raise RegionRebindInputError(f"rig {label} is invalid")
        identifier = safe_identifier(row.get("id"), f"{label} id")
        if identifier in result:
            raise RegionRebindInputError(f"duplicate {label} id")
        result[identifier] = row
    return result
