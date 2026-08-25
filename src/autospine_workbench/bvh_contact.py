"""Deterministic contact markers from explicit BVH source-world evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

from .bvh_fk import BvhProjectedFrames, bvh_frame_ticks
from .bvh_map_validation import (
    BvhMapValidationError,
    bvh_map_sha256,
    require_bvh_map,
)
from .bvh_parser import BvhDocument


Point3 = tuple[float, float, float]
WorldFrame = Mapping[str, Sequence[float]] | Sequence[
    tuple[str, Sequence[float]]
]


class BvhContactError(ValueError):
    """Raised when contact evidence is incomplete, non-finite, or ambiguous."""


@dataclass(frozen=True, slots=True)
class BvhContactMarker:
    """One immutable half-open, annotation-only MotionIR contact marker."""

    limb: str
    start_tick: int
    end_tick: int

    @property
    def document(self) -> dict[str, Any]:
        return {
            "kind": "contact",
            "limb": self.limb,
            "start_tick": self.start_tick,
            "end_tick": self.end_tick,
            "mode": "annotation_only",
        }


def detect_bvh_contacts(
    bvh: BvhDocument,
    bvh_map: Mapping[str, Any],
    *,
    projected: BvhProjectedFrames,
) -> tuple[BvhContactMarker, ...]:
    """Detect contacts from one source/map/time-bound FK projection snapshot."""

    try:
        require_bvh_map(bvh_map, bvh=bvh)
        ticks = _projected_ticks(bvh, bvh_map, projected)
        frames = _world_frames(bvh, projected.world_xyz_by_joint)
        contact = bvh_map["contact"]
        if not contact["enabled"]:
            return ()
        settings = _settings(contact, bvh.frame_time_seconds)
        markers: list[BvhContactMarker] = []
        for foot in contact["feet"]:
            raw = _classify(
                frames, foot["foot_joint_name"], bvh_map["basis"]["screen_y"],
                settings, loop=projected.loop,
            )
            filtered = _remove_short(
                _fill_internal_gaps(raw, settings.gap_frames),
                settings.minimum_frames,
            )
            markers.extend(
                _markers(foot["limb"], filtered, ticks, projected.duration_ticks)
            )
        result = tuple(sorted(
            markers, key=lambda item: (item.start_tick, item.end_tick, item.limb)
        ))
        _require_nonoverlap(result)
        return result
    except BvhContactError:
        raise
    except (
        BvhMapValidationError, KeyError, OverflowError, TypeError, ValueError,
    ) as exc:
        raise BvhContactError(f"BVH contact detection failed: {exc}") from exc


@dataclass(frozen=True, slots=True)
class _Settings:
    floor: float
    height: float
    speed: float
    frame_time: float
    minimum_frames: int
    gap_frames: int


def _settings(contact: Mapping[str, Any], frame_time: float) -> _Settings:
    if isinstance(frame_time, bool) or not isinstance(frame_time, (int, float)) \
            or not math.isfinite(frame_time) or frame_time <= 0:
        raise BvhContactError("BVH frame time must be finite and positive")
    return _Settings(
        float(contact["floor_height_source_units"]),
        float(contact["height_threshold_source_units"]),
        float(contact["speed_threshold_source_units_per_second"]),
        float(frame_time),
        contact["minimum_frames"],
        contact["gap_frames"],
    )


def _projected_ticks(
    bvh: BvhDocument,
    bvh_map: Mapping[str, Any],
    projected: BvhProjectedFrames,
) -> tuple[int, ...]:
    if type(bvh) is not BvhDocument or type(bvh.frame_count) is not int \
            or bvh.frame_count < 0 or len(bvh.frames) != bvh.frame_count:
        raise BvhContactError("BVH frame inventory is inconsistent")
    if type(projected) is not BvhProjectedFrames:
        raise BvhContactError("Contact evidence must be an exact BVH projection")
    expected_identity = (
        bvh.source_sha256,
        bvh_map["map_id"],
        bvh_map_sha256(bvh_map),
        bvh_map["clip"]["clip_id"],
        bvh_map["clip"]["loop"],
    )
    actual_identity = (
        projected.source_sha256,
        projected.map_id,
        projected.map_sha256,
        projected.clip_id,
        projected.loop,
    )
    if actual_identity != expected_identity:
        raise BvhContactError("Contact projection source/map identity differs")
    if len(projected.frames) != bvh.frame_count:
        raise BvhContactError("Contact projected frame inventory differs")
    ticks = tuple(frame.tick for frame in projected.frames)
    if ticks != bvh_frame_ticks(bvh) or projected.duration_ticks != ticks[-1]:
        raise BvhContactError("Contact projection time contract differs")
    return ticks


def _world_frames(
    bvh: BvhDocument,
    value: Sequence[WorldFrame],
) -> tuple[dict[str, Point3], ...]:
    if not isinstance(value, (tuple, list)) or len(value) != bvh.frame_count:
        raise BvhContactError("Contact world frames must match the BVH frame count")
    names = tuple(joint.name for joint in bvh.joints)
    expected = set(names)
    result: list[dict[str, Point3]] = []
    for frame in value:
        source = _frame_mapping(frame, names, expected)
        snapshot: dict[str, Point3] = {}
        for name in names:
            point = source[name]
            if not isinstance(point, (tuple, list)) or len(point) != 3:
                raise BvhContactError("Contact world coordinate must be xyz")
            if any(
                isinstance(item, bool) or not isinstance(item, (int, float))
                or not math.isfinite(item)
                for item in point
            ):
                raise BvhContactError("Contact world coordinate must be finite")
            snapshot[name] = tuple(float(item) for item in point)  # type: ignore[assignment]
        result.append(snapshot)
    return tuple(result)


def _frame_mapping(
    frame: WorldFrame, names: tuple[str, ...], expected: set[str]
) -> Mapping[str, Sequence[float]]:
    if isinstance(frame, Mapping):
        if set(frame) != expected:
            raise BvhContactError("Contact world frame joint inventory is incomplete")
        return frame
    if not isinstance(frame, (tuple, list)) or len(frame) != len(names):
        raise BvhContactError("Contact world frame joint inventory is incomplete")
    result: dict[str, Sequence[float]] = {}
    for expected_name, pair in zip(names, frame, strict=True):
        if not isinstance(pair, (tuple, list)) or len(pair) != 2 \
                or pair[0] != expected_name or pair[0] in result:
            raise BvhContactError(
                "Contact world frame pairs must follow BVH joint order"
            )
        result[pair[0]] = pair[1]
    return result


def _classify(
    frames: tuple[dict[str, Point3], ...], joint: str, screen_y: str,
    settings: _Settings, *, loop: bool,
) -> tuple[bool, ...]:
    result = []
    for index, frame in enumerate(frames):
        point = frame[joint]
        height = abs(_signed_axis(point, screen_y) - settings.floor)
        speed = _frame_speed(
            frames, joint, index, settings.frame_time, loop=loop
        )
        result.append(height <= settings.height and speed <= settings.speed)
    return tuple(result)


def _signed_axis(point: Point3, axis: str) -> float:
    index = {"X": 0, "Y": 1, "Z": 2}.get(axis[1:] if len(axis) == 2 else "")
    if axis[:1] not in ("+", "-") or index is None:
        raise BvhContactError("Contact screen-y basis axis is invalid")
    return point[index] if axis[0] == "+" else -point[index]


def _frame_speed(
    frames: tuple[dict[str, Point3], ...], joint: str, index: int,
    frame_time: float, *, loop: bool,
) -> float:
    if len(frames) <= 1:
        return 0.0
    if loop and index in {0, len(frames) - 1}:
        distances = (
            math.dist(frames[index][joint], frames[1][joint]),
            math.dist(frames[index][joint], frames[-2][joint]),
        )
        distance = max(distances)
    else:
        neighbor = 1 if index == 0 else index - 1
        distance = math.dist(frames[index][joint], frames[neighbor][joint])
    speed = distance / frame_time
    if not math.isfinite(speed):
        raise BvhContactError("Contact source-world speed is non-finite")
    return speed


def _fill_internal_gaps(bits: tuple[bool, ...], maximum: int) -> tuple[bool, ...]:
    result, index = list(bits), 0
    while index < len(result):
        if result[index]:
            index += 1
            continue
        start = index
        while index < len(result) and not result[index]:
            index += 1
        if start > 0 and index < len(result) and index - start <= maximum:
            result[start:index] = [True] * (index - start)
    return tuple(result)


def _remove_short(bits: tuple[bool, ...], minimum: int) -> tuple[bool, ...]:
    result, index = list(bits), 0
    while index < len(result):
        if not result[index]:
            index += 1
            continue
        start = index
        while index < len(result) and result[index]:
            index += 1
        if index - start < minimum:
            result[start:index] = [False] * (index - start)
    return tuple(result)


def _markers(
    limb: str, bits: tuple[bool, ...], ticks: tuple[int, ...], duration: int
) -> list[BvhContactMarker]:
    result, index = [], 0
    while index < len(bits):
        if not bits[index]:
            index += 1
            continue
        start = index
        while index < len(bits) and bits[index]:
            index += 1
        end_tick = ticks[index] if index < len(bits) else duration
        if ticks[start] >= end_tick:
            raise BvhContactError(
                "Tail contact cannot form a positive half-open interval"
            )
        result.append(BvhContactMarker(limb, ticks[start], end_tick))
    return result


def _require_nonoverlap(markers: tuple[BvhContactMarker, ...]) -> None:
    previous: dict[str, int] = {}
    for marker in markers:
        if marker.start_tick < previous.get(marker.limb, -1):
            raise BvhContactError("Contact markers overlap for one limb")
        previous[marker.limb] = marker.end_tick
