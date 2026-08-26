"""Deterministic 3D BVH FK and explicit signed-basis 2D projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math
from typing import Any

from .bvh_map_validation import bvh_map_sha256, require_bvh_map
from .bvh_parser import BvhDocument, MAX_BVH_ABS_VALUE, MAX_BVH_FRAMES
from .bvh_parser import MAX_BVH_JOINTS, MAX_BVH_TOTAL_SAMPLES
from .bvh_motion_root import BvhMotionRoot, require_bvh_motion_root
from .motion_roles import nearest_mapped_parent_role
from .motion_validation import MAX_DURATION_TICKS, TICKS_PER_SECOND

PRECISION_DECIMALS = 12
_EPSILON = 1e-12
_MIN_PROJECTED_SEGMENT_RATIO = 1e-6
_MIN_REFERENCE_SEGMENT_RATIO = 1e-9
_ROTATIONS = frozenset(("Xrotation", "Yrotation", "Zrotation"))
_POSITIONS = frozenset(("Xposition", "Yposition", "Zposition"))
Matrix4 = tuple[tuple[float, float, float, float], ...]

class BvhFkError(ValueError):
    """Raised when BVH FK or projection is unsafe or ambiguous."""

@dataclass(frozen=True, slots=True)
class BvhProjectedPoint:
    world_xyz: tuple[float, float, float]
    screen_xy: tuple[float, float]
    depth: float

@dataclass(frozen=True, slots=True)
class BvhProjectedSegment:
    role: str
    source_joint_name: str
    delta_parent_role: str | None
    projected_world_angle_deg: float
    setup_local_additive_delta_deg: float

@dataclass(frozen=True, slots=True)
class BvhProjectedFrame:
    tick: int
    joints: tuple[tuple[str, BvhProjectedPoint], ...]
    end_sites: tuple[tuple[str, BvhProjectedPoint], ...]
    root_translation_normalized: tuple[float, float]
    segments: tuple[BvhProjectedSegment, ...]

@dataclass(frozen=True, slots=True)
class BvhProjectedFrames:
    source_sha256: str
    map_id: str
    map_sha256: str
    clip_id: str
    loop: bool
    duration_ticks: int
    frames: tuple[BvhProjectedFrame, ...]

    @property
    def world_xyz_by_joint(self) -> tuple[tuple[tuple[str, tuple[float, float, float]], ...], ...]:
        return tuple(tuple((name, point.world_xyz) for name, point in frame.joints)
                     for frame in self.frames)

def project_bvh_frames(
    bvh: BvhDocument, bvh_map: Mapping[str, Any]
) -> BvhProjectedFrames:
    """Run declared-channel 3D FK, then project through the explicit map basis."""
    require_bvh_map(bvh_map, bvh=bvh)
    motion_root = require_bvh_motion_root(
        bvh, bvh_map["root"]["joint_name"]
    )
    _require_document(bvh, motion_root)
    ticks = bvh_frame_ticks(bvh)
    basis, bones = bvh_map["basis"], bvh_map["bones"]
    names = {joint.name: index for index, joint in enumerate(bvh.joints)}
    reference = float(bvh_map["root"]["reference_length_source_units"])
    spatial, angles = [], {row["role"]: [] for row in bones}
    for source_frame in bvh.frames:
        frame_world = _world_matrices(bvh, source_frame)
        joints = tuple(
            (joint.name, _point(_origin(frame_world[index]), basis))
            for index, joint in enumerate(bvh.joints)
        )
        end_xyz = {
            joint.name: _origin(_multiply(frame_world[index], _translate(joint.end_site_offset)))
            for index, joint in enumerate(bvh.joints)
            if joint.end_site_offset is not None
        }
        end_sites = tuple(
            (joint.name, _point(end_xyz[joint.name], basis))
            for joint in bvh.joints if joint.name in end_xyz
        )
        for row in bones:
            source = _origin(frame_world[names[row["joint_name"]]])
            aim = row["aim"]
            target = (
                _origin(frame_world[names[aim["joint_name"]]])
                if aim["kind"] == "joint" else end_xyz[row["joint_name"]]
            )
            angles[row["role"]].append(
                _segment_angle(source, target, basis, reference)
            )
        spatial.append((joints, end_sites, _project_raw(
            _origin(frame_world[names[bvh_map["root"]["joint_name"]]]), basis
        )[:2]))
    unwrapped = {role: _unwrap(values) for role, values in angles.items()}
    root_setup = spatial[0][2]
    frames = []
    for index, (joints, end_sites, root_xy) in enumerate(spatial):
        changes = {role: values[index] - values[0] for role, values in unwrapped.items()}
        segments = []
        for row in bones:
            role = row["role"]
            parent = nearest_mapped_parent_role(role, changes)
            delta = changes[role] - (changes[parent] if parent else 0.0)
            segments.append(BvhProjectedSegment(
                role=role, source_joint_name=row["joint_name"],
                delta_parent_role=parent,
                projected_world_angle_deg=_quantize(unwrapped[role][index]),
                setup_local_additive_delta_deg=_quantize(delta),
            ))
        frames.append(BvhProjectedFrame(
            tick=ticks[index], joints=joints, end_sites=end_sites,
            root_translation_normalized=(
                _quantize((root_xy[0] - root_setup[0]) / reference),
                _quantize((root_xy[1] - root_setup[1]) / reference),
            ),
            segments=tuple(segments),
        ))
    result = BvhProjectedFrames(
        source_sha256=bvh.source_sha256, map_id=bvh_map["map_id"],
        map_sha256=bvh_map_sha256(bvh_map),
        clip_id=bvh_map["clip"]["clip_id"], loop=bvh_map["clip"]["loop"],
        duration_ticks=ticks[-1], frames=tuple(frames),
    )
    if result.loop and _payload(result.frames[0]) != _payload(result.frames[-1]):
        raise BvhFkError("Looping BVH projection endpoints differ after quantization")
    return result


def _require_document(bvh: BvhDocument, motion_root: BvhMotionRoot) -> None:
    if type(bvh) is not BvhDocument or not isinstance(bvh.source_sha256, str) or len(bvh.source_sha256) != 64 \
            or any(value not in "0123456789abcdef" for value in bvh.source_sha256):
        raise BvhFkError("BVH projection requires one parsed content-addressed document")
    if not 2 <= bvh.frame_count <= MAX_BVH_FRAMES or len(bvh.frames) != bvh.frame_count:
        raise BvhFkError("BVH projection requires 2..MAX_BVH_FRAMES frames")
    if not 1 <= len(bvh.joints) <= MAX_BVH_JOINTS:
        raise BvhFkError("BVH projection joint resource limit exceeded")
    channel_count = sum(len(joint.channels) for joint in bvh.joints)
    if bvh.channel_count != channel_count or bvh.frame_count * channel_count > MAX_BVH_TOTAL_SAMPLES:
        raise BvhFkError("BVH projection channel/sample count is inconsistent")
    for index, joint in enumerate(bvh.joints):
        expected = (
            _ROTATIONS | _POSITIONS
            if index in {0, motion_root.joint_index} else _ROTATIONS
        )
        if type(joint.channels) is not tuple or len(joint.channels) != len(expected) \
                or set(joint.channels) != expected:
            raise BvhFkError("BVH projection channel profile is unsupported")
        _vector(joint.offset, "joint offset")
        if joint.end_site_offset is not None:
            _vector(joint.end_site_offset, "End Site offset")
    for frame in bvh.frames:
        if type(frame) is not tuple or len(frame) != channel_count:
            raise BvhFkError("BVH projection frame channel slice is inconsistent")
        for value in frame:
            _number(value, "motion sample")


def bvh_frame_ticks(bvh: BvhDocument) -> tuple[int, ...]:
    """Derive the only MotionIR tick schedule admitted for a BVH snapshot."""

    _number(bvh.frame_time_seconds, "frame time")
    if bvh.frame_time_seconds <= 0:
        raise BvhFkError("BVH projection frame time must be positive")
    try:
        step = Decimal(str(bvh.frame_time_seconds)) * TICKS_PER_SECOND
        ticks = tuple(int((step * index).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                      for index in range(bvh.frame_count))
    except (InvalidOperation, ValueError) as exc:
        raise BvhFkError("BVH projection frame time cannot form exact ticks") from exc
    if any(right <= left for left, right in zip(ticks, ticks[1:])):
        raise BvhFkError("BVH projection ticks must be strictly increasing")
    if ticks[-1] > MAX_DURATION_TICKS:
        raise BvhFkError("BVH projection duration exceeds MotionIR v1")
    return ticks


def _world_matrices(bvh: BvhDocument, frame: tuple[float, ...]) -> tuple[Matrix4, ...]:
    cursor, worlds = 0, []
    for joint in bvh.joints:
        local = _translate(joint.offset)
        for channel in joint.channels:
            local = _multiply(local, _channel(channel, float(frame[cursor])))
            cursor += 1
        worlds.append(local if joint.parent_index is None else _multiply(
            worlds[joint.parent_index], local
        ))
    if cursor != len(frame):
        raise BvhFkError("BVH projection did not consume its exact channel slice")
    return tuple(worlds)


def _channel(channel: str, value: float) -> Matrix4:
    if channel.endswith("position"):
        axis = channel[0]
        return _translate(tuple(value if name == axis else 0.0 for name in "XYZ"))
    if channel not in _ROTATIONS:
        raise BvhFkError("BVH projection encountered an unsupported channel")
    angle = math.radians(value)
    cosine, sine = math.cos(angle), math.sin(angle)
    if channel[0] == "X":
        rows = ((1, 0, 0), (0, cosine, -sine), (0, sine, cosine))
    elif channel[0] == "Y":
        rows = ((cosine, 0, sine), (0, 1, 0), (-sine, 0, cosine))
    else:
        rows = ((cosine, -sine, 0), (sine, cosine, 0), (0, 0, 1))
    return tuple(tuple(float(rows[r][c]) if c < 3 else 0.0 for c in range(4))
                 for r in range(3)) + ((0.0, 0.0, 0.0, 1.0),)


def _translate(value) -> Matrix4:
    x, y, z = value
    return ((1.0, 0.0, 0.0, x), (0.0, 1.0, 0.0, y),
            (0.0, 0.0, 1.0, z), (0.0, 0.0, 0.0, 1.0))


def _multiply(left: Matrix4, right: Matrix4) -> Matrix4:
    return tuple(tuple(sum(left[row][k] * right[k][column] for k in range(4))
                       for column in range(4)) for row in range(4))


def _origin(matrix: Matrix4) -> tuple[float, float, float]:
    return matrix[0][3], matrix[1][3], matrix[2][3]


def _project_raw(xyz, basis) -> tuple[float, float, float]:
    axes = {"X": 0, "Y": 1, "Z": 2}
    def component(token):
        return (-1.0 if token[0] == "-" else 1.0) * xyz[axes[token[1]]]
    return tuple(component(basis[name]) for name in ("screen_x", "screen_y", "depth"))


def _point(xyz, basis) -> BvhProjectedPoint:
    x, y, depth = _project_raw(xyz, basis)
    return BvhProjectedPoint(tuple(_quantize(v) for v in xyz),
                             (_quantize(x), _quantize(y)), _quantize(depth))


def _segment_angle(start, end, basis, reference: float) -> float:
    left, right = _project_raw(start, basis), _project_raw(end, basis)
    dx, dy = right[0] - left[0], right[1] - left[1]
    source_length = math.dist(start, end)
    minimum = max(
        _EPSILON,
        source_length * _MIN_PROJECTED_SEGMENT_RATIO,
        reference * _MIN_REFERENCE_SEGMENT_RATIO,
    )
    if not math.isfinite(dx) or not math.isfinite(dy) \
            or not math.isfinite(source_length) or math.hypot(dx, dy) <= minimum:
        raise BvhFkError("BVH mapped segment is degenerate after 2D projection")
    return math.degrees(math.atan2(dy, dx))


def _unwrap(values: list[float]) -> tuple[float, ...]:
    result = [values[0]]
    for value in values[1:]:
        delta = (value - result[-1] + 180.0) % 360.0 - 180.0
        result.append(result[-1] + delta)
    return tuple(result)


def _payload(frame: BvhProjectedFrame):
    return frame.joints, frame.end_sites, frame.root_translation_normalized, frame.segments


def _vector(value, label: str) -> None:
    if type(value) is not tuple or len(value) != 3:
        raise BvhFkError(f"BVH projection {label} must be a source XYZ tuple")
    for number in value:
        _number(number, label)


def _number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or abs(value) > MAX_BVH_ABS_VALUE:
        raise BvhFkError(f"BVH projection {label} must be finite and bounded")
    return float(value)


def _quantize(value: float) -> float:
    if not math.isfinite(value):
        raise BvhFkError("BVH projection produced a non-finite output")
    result = round(float(value), PRECISION_DECIMALS)
    return 0.0 if result == 0 else result
