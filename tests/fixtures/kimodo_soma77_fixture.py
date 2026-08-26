"""Deterministic, synthetic Kimodo SOMA77 BVH fixture builder.

The fixture preserves Kimodo's unusual BVH shape exactly: a zero-motion,
six-channel ``Root`` wrapper owns a second six-channel ``Hips`` joint, followed
by the public 77-joint SOMA hierarchy.  Names, hierarchy shape, channel order,
centimetre scale, and 30 Hz timing follow Kimodo; offsets and motion values are
deliberately synthetic so no upstream character asset is copied.
"""

from __future__ import annotations

import json
from pathlib import Path


_HERE = Path(__file__).resolve().parent
MAP_PATH = _HERE / "kimodo_soma77_front.map.json"
ROOT_CHANNELS = (
    "Xposition", "Yposition", "Zposition",
    "Zrotation", "Yrotation", "Xrotation",
)
JOINT_CHANNELS = ("Zrotation", "Yrotation", "Xrotation")


# Declaration order matches the public SOMA77 hierarchy.  Synthetic offsets
# retain a readable T-pose and keep every mapped segment non-degenerate in XY.
_JOINTS = (
    ("Hips", None, (0, 100, 0)),
    ("Spine1", "Hips", (0, 5, 0)),
    ("Spine2", "Spine1", (0, 7, 0)),
    ("Chest", "Spine2", (0, 8, 0)),
    ("Neck1", "Chest", (0, 10, 0)),
    ("Neck2", "Neck1", (0, 7, 0)),
    ("Head", "Neck2", (0, 6, 0)),
    ("HeadEnd", "Head", (0, 12, 0)),
    ("Jaw", "Head", (0, -1, 3)),
    ("LeftEye", "Head", (3, 4, 5)),
    ("RightEye", "Head", (-3, 4, 5)),
    ("LeftShoulder", "Chest", (5, 5, 0)),
    ("LeftArm", "LeftShoulder", (12, 0, 0)),
    ("LeftForeArm", "LeftArm", (20, 0, 0)),
    ("LeftHand", "LeftForeArm", (18, 0, 0)),
    ("LeftHandThumb1", "LeftHand", (2, -1, 2)),
    ("LeftHandThumb2", "LeftHandThumb1", (3, -1, 1)),
    ("LeftHandThumb3", "LeftHandThumb2", (2, 0, 0)),
    ("LeftHandThumbEnd", "LeftHandThumb3", (2, 0, 0)),
    ("LeftHandIndex1", "LeftHand", (2, 1, 2)),
    ("LeftHandIndex2", "LeftHandIndex1", (4, 0, 0)),
    ("LeftHandIndex3", "LeftHandIndex2", (3, 0, 0)),
    ("LeftHandIndex4", "LeftHandIndex3", (2, 0, 0)),
    ("LeftHandIndexEnd", "LeftHandIndex4", (2, 0, 0)),
    ("LeftHandMiddle1", "LeftHand", (2, 0, 1)),
    ("LeftHandMiddle2", "LeftHandMiddle1", (4, 0, 0)),
    ("LeftHandMiddle3", "LeftHandMiddle2", (3, 0, 0)),
    ("LeftHandMiddle4", "LeftHandMiddle3", (2, 0, 0)),
    ("LeftHandMiddleEnd", "LeftHandMiddle4", (2, 0, 0)),
    ("LeftHandRing1", "LeftHand", (2, -1, 0)),
    ("LeftHandRing2", "LeftHandRing1", (4, 0, 0)),
    ("LeftHandRing3", "LeftHandRing2", (3, 0, 0)),
    ("LeftHandRing4", "LeftHandRing3", (2, 0, 0)),
    ("LeftHandRingEnd", "LeftHandRing4", (2, 0, 0)),
    ("LeftHandPinky1", "LeftHand", (2, -2, -1)),
    ("LeftHandPinky2", "LeftHandPinky1", (3, 0, 0)),
    ("LeftHandPinky3", "LeftHandPinky2", (2, 0, 0)),
    ("LeftHandPinky4", "LeftHandPinky3", (1, 0, 0)),
    ("LeftHandPinkyEnd", "LeftHandPinky4", (1, 0, 0)),
    ("RightShoulder", "Chest", (-5, 5, 0)),
    ("RightArm", "RightShoulder", (-12, 0, 0)),
    ("RightForeArm", "RightArm", (-20, 0, 0)),
    ("RightHand", "RightForeArm", (-18, 0, 0)),
    ("RightHandThumb1", "RightHand", (-2, -1, 2)),
    ("RightHandThumb2", "RightHandThumb1", (-3, -1, 1)),
    ("RightHandThumb3", "RightHandThumb2", (-2, 0, 0)),
    ("RightHandThumbEnd", "RightHandThumb3", (-2, 0, 0)),
    ("RightHandIndex1", "RightHand", (-2, 1, 2)),
    ("RightHandIndex2", "RightHandIndex1", (-4, 0, 0)),
    ("RightHandIndex3", "RightHandIndex2", (-3, 0, 0)),
    ("RightHandIndex4", "RightHandIndex3", (-2, 0, 0)),
    ("RightHandIndexEnd", "RightHandIndex4", (-2, 0, 0)),
    ("RightHandMiddle1", "RightHand", (-2, 0, 1)),
    ("RightHandMiddle2", "RightHandMiddle1", (-4, 0, 0)),
    ("RightHandMiddle3", "RightHandMiddle2", (-3, 0, 0)),
    ("RightHandMiddle4", "RightHandMiddle3", (-2, 0, 0)),
    ("RightHandMiddleEnd", "RightHandMiddle4", (-2, 0, 0)),
    ("RightHandRing1", "RightHand", (-2, -1, 0)),
    ("RightHandRing2", "RightHandRing1", (-4, 0, 0)),
    ("RightHandRing3", "RightHandRing2", (-3, 0, 0)),
    ("RightHandRing4", "RightHandRing3", (-2, 0, 0)),
    ("RightHandRingEnd", "RightHandRing4", (-2, 0, 0)),
    ("RightHandPinky1", "RightHand", (-2, -2, -1)),
    ("RightHandPinky2", "RightHandPinky1", (-3, 0, 0)),
    ("RightHandPinky3", "RightHandPinky2", (-2, 0, 0)),
    ("RightHandPinky4", "RightHandPinky3", (-1, 0, 0)),
    ("RightHandPinkyEnd", "RightHandPinky4", (-1, 0, 0)),
    ("LeftLeg", "Hips", (10, -10, 0)),
    ("LeftShin", "LeftLeg", (0, -40, 0)),
    ("LeftFoot", "LeftShin", (0, -40, 0)),
    ("LeftToeBase", "LeftFoot", (0, -5, 10)),
    ("LeftToeEnd", "LeftToeBase", (0, 0, 5)),
    ("RightLeg", "Hips", (-10, -10, 0)),
    ("RightShin", "RightLeg", (0, -40, 0)),
    ("RightFoot", "RightShin", (0, -40, 0)),
    ("RightToeBase", "RightFoot", (0, -5, 10)),
    ("RightToeEnd", "RightToeBase", (0, 0, 5)),
)

SOMA77_JOINT_NAMES = tuple(row[0] for row in _JOINTS)
BVH_JOINT_NAMES = ("Root",) + SOMA77_JOINT_NAMES
_BY_NAME = {name: (parent, offset) for name, parent, offset in _JOINTS}
_CHILDREN = {
    name: tuple(row[0] for row in _JOINTS if row[1] == name)
    for name in SOMA77_JOINT_NAMES
}
_POSE_ONE = {
    "Hips": (10, 0, 0),
    "Spine1": (5, 0, 0),
    "Spine2": (-2, 0, 0),
    "Neck1": (1, 0, 0),
    "Head": (-1, 0, 0),
    "LeftShoulder": (3, 0, 0),
    "LeftArm": (10, 0, 0),
    "LeftForeArm": (-20, 0, 0),
    "RightShoulder": (-3, 0, 0),
    "RightArm": (-10, 0, 0),
    "RightForeArm": (20, 0, 0),
}


def build_soma77_bvh() -> bytes:
    """Return a fresh two-frame Kimodo double-root SOMA77 BVH snapshot."""

    lines = [
        "HIERARCHY",
        "ROOT Root",
        "{",
        "  OFFSET 0 0 0",
        f"  CHANNELS {len(ROOT_CHANNELS)} {' '.join(ROOT_CHANNELS)}",
    ]
    _emit_joint(lines, "Hips", depth=1)
    lines.append("}")
    lines.extend((
        "MOTION",
        "Frames: 2",
        "Frame Time: 0.03333333333333333",
        _frame(root_x=0, pose={}),
        _frame(root_x=2, pose=_POSE_ONE),
    ))
    return ("\n".join(lines) + "\n").encode("ascii")


def load_soma77_map() -> dict:
    """Load a fresh mutable copy of the checked-in explicit smoke map."""

    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def _emit_joint(lines: list[str], name: str, *, depth: int) -> None:
    _, offset = _BY_NAME[name]
    indent = "  " * depth
    channels = ROOT_CHANNELS if name == "Hips" else JOINT_CHANNELS
    lines.extend((
        f"{indent}JOINT {name}",
        f"{indent}{{",
        f"{indent}  OFFSET {' '.join(str(value) for value in offset)}",
        f"{indent}  CHANNELS {len(channels)} {' '.join(channels)}",
    ))
    for child in _CHILDREN[name]:
        _emit_joint(lines, child, depth=depth + 1)
    lines.append(f"{indent}}}")


def _frame(*, root_x: int, pose: dict[str, tuple[int, int, int]]) -> str:
    values: list[int] = [0] * len(ROOT_CHANNELS)
    for name, parent, _ in _JOINTS:
        rotation = pose.get(name, (0, 0, 0))
        values.extend((root_x, 0, 0, *rotation) if parent is None else rotation)
    return " ".join(str(value) for value in values)
