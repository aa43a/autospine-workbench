"""Deterministic parameterized weights for a reviewed two-bone hinge."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
import re
from typing import Any


UINT16_MAX = 65535
CHAIN_JOIN_TOLERANCE_PX = 1e-6
MAX_HALF_BAND_FRACTION = 0.45
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class TwoBoneWeightError(ValueError):
    """Raised when a hinge or its mesh cannot produce safe two-bone weights."""


@dataclass(frozen=True, slots=True)
class TwoBoneWeights:
    """Quantized distal weights and deterministic projection evidence."""

    proximal_bone_id: str
    distal_bone_id: str
    proximal_length_px: float
    distal_length_px: float
    half_band_px: float
    grid_step_px: int
    blend_fraction: float
    segment_indices: tuple[int, ...]
    arc_lengths_px: tuple[float, ...]
    distal_weights_u16: tuple[int, ...]


def build_two_bone_weights(
    vertices_xy: Sequence[Sequence[int | float]],
    *,
    proximal_bone_id: str,
    distal_bone_id: str,
    proximal_origin_xy: Sequence[int | float],
    proximal_endpoint_xy: Sequence[int | float],
    distal_origin_xy: Sequence[int | float],
    distal_endpoint_xy: Sequence[int | float],
    grid_step_px: int = 8,
    blend_fraction: float = 0.20,
) -> TwoBoneWeights:
    """Weight setup-canvas vertices by arc length along two setup bones."""

    proximal_id = _bone_id(proximal_bone_id, "proximal bone")
    distal_id = _bone_id(distal_bone_id, "distal bone")
    if proximal_id == distal_id:
        raise TwoBoneWeightError("proximal and distal bones must differ")
    step = _positive_integer(grid_step_px, "grid step")
    fraction = _fraction(blend_fraction)
    p0 = _point(proximal_origin_xy, "proximal origin")
    p1 = _point(proximal_endpoint_xy, "proximal endpoint")
    distal_origin = _point(distal_origin_xy, "distal origin")
    p2 = _point(distal_endpoint_xy, "distal endpoint")
    if math.dist(p1, distal_origin) > CHAIN_JOIN_TOLERANCE_PX:
        raise TwoBoneWeightError(
            "proximal endpoint must equal distal origin within 1e-6 pixels"
        )
    length0 = _length(p0, p1, "proximal bone")
    length1 = _length(distal_origin, p2, "distal bone")
    minimum_length = min(length0, length1)
    half_band = max(2.0 * step, fraction * minimum_length)
    if half_band > MAX_HALF_BAND_FRACTION * minimum_length:
        raise TwoBoneWeightError(
            "blend half-band exceeds 45 percent of the shorter bone"
        )
    vertices = _vertices(vertices_xy)
    projections = tuple(
        _project_to_chain(
            point, p0, p1, distal_origin, p2, length0, length1
        )
        for point in vertices
    )
    arc_lengths = tuple(item[1] for item in projections)
    distal_weights = tuple(
        _quantize_distal_weight(arc, length0, half_band)
        for arc in arc_lengths
    )
    _require_weight_classes(distal_weights, arc_lengths, step)
    return TwoBoneWeights(
        proximal_bone_id=proximal_id,
        distal_bone_id=distal_id,
        proximal_length_px=length0,
        distal_length_px=length1,
        half_band_px=half_band,
        grid_step_px=step,
        blend_fraction=fraction,
        segment_indices=tuple(item[0] for item in projections),
        arc_lengths_px=arc_lengths,
        distal_weights_u16=distal_weights,
    )


def to_rigir_weights(weights: TwoBoneWeights) -> list[list[dict[str, Any]]]:
    """Convert quantized weights to positive, canonical-sum RigIR influences."""

    if not isinstance(weights, TwoBoneWeights):
        raise TwoBoneWeightError("weights must be a TwoBoneWeights value")
    result: list[list[dict[str, Any]]] = []
    for distal_q16 in weights.distal_weights_u16:
        if distal_q16 == 0:
            result.append([{"bone": weights.proximal_bone_id, "weight": 1.0}])
        elif distal_q16 == UINT16_MAX:
            result.append([{"bone": weights.distal_bone_id, "weight": 1.0}])
        else:
            proximal = (UINT16_MAX - distal_q16) / UINT16_MAX
            result.append(
                [
                    {"bone": weights.proximal_bone_id, "weight": proximal},
                    {"bone": weights.distal_bone_id, "weight": 1.0 - proximal},
                ]
            )
    return result


def require_direct_child(
    bones: Sequence[Mapping[str, Any]],
    *,
    proximal_bone_id: str,
    distal_bone_id: str,
) -> None:
    """Require the distal bone to be the proximal bone's direct child."""

    proximal_id = _bone_id(proximal_bone_id, "proximal bone")
    distal_id = _bone_id(distal_bone_id, "distal bone")
    if not isinstance(bones, Sequence) or isinstance(bones, (str, bytes)):
        raise TwoBoneWeightError("bones must be an array")
    indexed: dict[str, Mapping[str, Any]] = {}
    for index, bone in enumerate(bones):
        if not isinstance(bone, Mapping):
            raise TwoBoneWeightError(f"bone {index} must be an object")
        bone_id = _bone_id(bone.get("id"), f"bone {index}")
        if bone_id in indexed:
            raise TwoBoneWeightError(f"duplicate bone id: {bone_id}")
        indexed[bone_id] = bone
    if proximal_id not in indexed or distal_id not in indexed:
        raise TwoBoneWeightError("two-bone chain references a missing bone")
    if indexed[distal_id].get("parent") != proximal_id:
        raise TwoBoneWeightError("distal bone must be a direct child of proximal bone")


def _project_to_chain(point, p0, p1, distal_origin, p2, length0, length1):
    candidates = []
    for index, (start, end, offset, length) in enumerate(
        (
            (p0, p1, 0.0, length0),
            (distal_origin, p2, length0, length1),
        )
    ):
        dx, dy = end[0] - start[0], end[1] - start[1]
        t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (
            length * length
        )
        t = min(1.0, max(0.0, t))
        projected = (start[0] + t * dx, start[1] + t * dy)
        distance_sq = (point[0] - projected[0]) ** 2 + (
            point[1] - projected[1]
        ) ** 2
        candidates.append((distance_sq, index, offset + t * length))
    _, segment_index, arc_length = min(candidates)
    return segment_index, arc_length


def _quantize_distal_weight(arc_length: float, length0: float, half_band: float) -> int:
    value = (arc_length - (length0 - half_band)) / (2.0 * half_band)
    value = min(1.0, max(0.0, value))
    smooth = value * value * (3.0 - 2.0 * value)
    return int(math.floor(smooth * UINT16_MAX + 0.5))


def _require_weight_classes(weights, arc_lengths, step):
    blended = [
        arc for arc, weight in zip(arc_lengths, weights)
        if 0 < weight < UINT16_MAX
    ]
    if 0 not in weights or UINT16_MAX not in weights or not blended:
        raise TwoBoneWeightError(
            "mesh must include proximal-only, blended, and distal-only weights"
        )
    if max(blended) - min(blended) + 1e-9 < 2.0 * step:
        raise TwoBoneWeightError("mesh blend must span at least two grid steps")


def _vertices(value):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise TwoBoneWeightError("vertices must be a non-empty array")
    return tuple(_point(point, f"vertex {index}") for index, point in enumerate(value))


def _point(value, label):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise TwoBoneWeightError(f"{label} must contain two finite numbers")
    return (_number(value[0], label), _number(value[1], label))


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise TwoBoneWeightError(f"{label} must contain two finite numbers")
    return float(value)


def _length(start, end, label):
    length = math.dist(start, end)
    if not math.isfinite(length) or length <= 1e-9:
        raise TwoBoneWeightError(f"{label} length must be finite and positive")
    return length


def _bone_id(value, label):
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise TwoBoneWeightError(f"{label} id is invalid")
    return value


def _positive_integer(value, label):
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise TwoBoneWeightError(f"{label} must be a positive integer")
    return value


def _fraction(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 < value <= MAX_HALF_BAND_FRACTION
    ):
        raise TwoBoneWeightError("blend fraction must be in (0, 0.45]")
    return float(value)
