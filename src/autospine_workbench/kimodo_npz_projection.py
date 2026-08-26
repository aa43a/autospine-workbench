"""Deterministic setup-frame SOMA77 segment projection into MotionIR space."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any

from .kimodo_npz_consistency import ValidatedKimodoMotion
from .kimodo_npz_map_validation import (
    kimodo_npz_map_sha256,
    require_kimodo_npz_map,
)
from .kimodo_npz_source import kimodo_npz_source_sha256, require_kimodo_npz_source
from .kimodo_soma77 import SOMA77_INDEX_BY_NAME
from .motion_roles import nearest_mapped_parent_role
from .motion_validation import MAX_DURATION_TICKS, TICKS_PER_SECOND


# Source arrays are float32.  Five decimal places remove compounded FK noise
# while preserving 1e-5 normalized resolution for ordinary rigs.
PRECISION_DECIMALS = 5
_EPSILON = 1e-12
_MIN_PROJECTED_SEGMENT_RATIO = 1e-6
_MIN_REFERENCE_SEGMENT_RATIO = 1e-9


class KimodoNpzProjectionError(ValueError):
    """Raised when validated 3D motion cannot form stable 2D tracks."""


@dataclass(frozen=True, slots=True)
class KimodoProjectedSegment:
    role: str
    source_joint_name: str
    delta_parent_role: str | None
    projected_world_angle_deg: float
    setup_local_additive_delta_deg: float


@dataclass(frozen=True, slots=True)
class KimodoProjectedFrame:
    tick: int
    root_translation_normalized: tuple[float, float]
    segments: tuple[KimodoProjectedSegment, ...]


@dataclass(frozen=True, slots=True)
class KimodoProjectedFrames:
    raw_npz_sha256: str
    source_sha256: str
    map_sha256: str
    map_id: str
    clip_id: str
    loop: bool
    duration_ticks: int
    frames: tuple[KimodoProjectedFrame, ...]


def project_kimodo_frames(
    motion: ValidatedKimodoMotion,
    source: Mapping[str, Any],
    mapping: Mapping[str, Any],
) -> KimodoProjectedFrames:
    """Project matrix-validated positions through one explicit signed basis."""

    try:
        require_kimodo_npz_source(source)
        require_kimodo_npz_map(mapping, source=source)
        if type(motion) is not ValidatedKimodoMotion \
                or motion.source_sha256 != kimodo_npz_source_sha256(source):
            raise KimodoNpzProjectionError(
                "Kimodo validated motion differs from its source"
            )
        ticks = kimodo_frame_ticks(source)
        if len(ticks) != motion.frame_count:
            raise KimodoNpzProjectionError("Kimodo tick count differs from motion")
        basis, bones = mapping["basis"], mapping["bones"]
        reference = float(mapping["root"]["reference_length_meters"])
        angles = {row["role"]: [] for row in bones}
        root_points = []
        for positions in motion.positions:
            root_points.append(_project(positions[0], basis)[:2])
            for row in bones:
                start = positions[SOMA77_INDEX_BY_NAME[row["joint_name"]]]
                end = positions[SOMA77_INDEX_BY_NAME[row["aim_joint_name"]]]
                angles[row["role"]].append(
                    _segment_angle(start, end, basis, reference)
                )
        unwrapped = {role: _unwrap(values) for role, values in angles.items()}
        root_zero = root_points[0]
        frames = []
        for index, root in enumerate(root_points):
            changes = {
                role: values[index] - values[0]
                for role, values in unwrapped.items()
            }
            segments = []
            for row in bones:
                role = row["role"]
                parent = nearest_mapped_parent_role(role, changes)
                delta = changes[role] - (changes[parent] if parent else 0.0)
                segments.append(KimodoProjectedSegment(
                    role=role,
                    source_joint_name=row["joint_name"],
                    delta_parent_role=parent,
                    projected_world_angle_deg=_quantize(unwrapped[role][index]),
                    setup_local_additive_delta_deg=_quantize(delta),
                ))
            frames.append(KimodoProjectedFrame(
                tick=ticks[index],
                root_translation_normalized=(
                    _quantize((root[0] - root_zero[0]) / reference),
                    _quantize((root[1] - root_zero[1]) / reference),
                ),
                segments=tuple(segments),
            ))
        result = KimodoProjectedFrames(
            raw_npz_sha256=motion.raw_npz_sha256,
            source_sha256=motion.source_sha256,
            map_sha256=kimodo_npz_map_sha256(mapping),
            map_id=mapping["map_id"],
            clip_id=mapping["clip"]["clip_id"],
            loop=mapping["clip"]["loop"],
            duration_ticks=ticks[-1],
            frames=tuple(frames),
        )
        if result.loop and _payload(result.frames[0]) != _payload(result.frames[-1]):
            raise KimodoNpzProjectionError(
                "Looping Kimodo projection endpoints differ after quantization"
            )
        return result
    except KimodoNpzProjectionError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise KimodoNpzProjectionError(f"Kimodo projection failed: {exc}") from exc


def kimodo_frame_ticks(source: Mapping[str, Any]) -> tuple[int, ...]:
    """Convert explicit rational fps to exact half-up microsecond ticks."""

    require_kimodo_npz_source(source)
    frames = int(source["raw_npz"]["frame_count"])
    rate = source["raw_npz"]["frames_per_second"]
    numerator, denominator = int(rate["numerator"]), int(rate["denominator"])
    ticks = tuple(
        (2 * index * denominator * TICKS_PER_SECOND + numerator)
        // (2 * numerator)
        for index in range(frames)
    )
    if any(right <= left for left, right in zip(ticks, ticks[1:])) \
            or ticks[-1] > MAX_DURATION_TICKS:
        raise KimodoNpzProjectionError("Kimodo frame rate cannot form valid ticks")
    return ticks


def _project(xyz, basis) -> tuple[float, float, float]:
    axes = {"X": 0, "Y": 1, "Z": 2}
    result = []
    for field in ("screen_x", "screen_y", "depth"):
        token = basis[field]
        result.append((-1.0 if token[0] == "-" else 1.0) * xyz[axes[token[1]]])
    return tuple(result)


def _segment_angle(start, end, basis, reference: float) -> float:
    left, right = _project(start, basis), _project(end, basis)
    dx, dy = right[0] - left[0], right[1] - left[1]
    source_length = math.dist(start, end)
    minimum = max(
        _EPSILON,
        source_length * _MIN_PROJECTED_SEGMENT_RATIO,
        reference * _MIN_REFERENCE_SEGMENT_RATIO,
    )
    if not math.isfinite(source_length) or math.hypot(dx, dy) <= minimum:
        raise KimodoNpzProjectionError(
            "Kimodo mapped segment is degenerate after 2D projection"
        )
    return math.degrees(math.atan2(dy, dx))


def _unwrap(values: list[float]) -> tuple[float, ...]:
    result = [values[0]]
    for value in values[1:]:
        delta = (value - result[-1] + 180.0) % 360.0 - 180.0
        result.append(result[-1] + delta)
    return tuple(result)


def _payload(frame: KimodoProjectedFrame):
    return frame.root_translation_normalized, frame.segments


def _quantize(value: float) -> float:
    if not math.isfinite(value):
        raise KimodoNpzProjectionError("Kimodo projection produced non-finite output")
    result = round(float(value), PRECISION_DECIMALS)
    return 0.0 if result == 0 else result
