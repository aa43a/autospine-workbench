"""Standard-library builders for deterministic synthetic Kimodo NPZ bytes."""

from __future__ import annotations

import io
import math
import struct
import zipfile

from autospine_workbench.kimodo_soma77 import (
    SOMA77_JOINT_NAMES,
    SOMA77_PARENT_INDICES,
)
from tests.fixtures.kimodo_soma77_fixture import _JOINTS


CORE_NAMES = (
    "posed_joints",
    "global_rot_mats",
    "local_rot_mats",
    "foot_contacts",
    "root_positions",
)
COMPLETE_NAMES = (
    "posed_joints",
    "global_rot_mats",
    "local_rot_mats",
    "foot_contacts",
    "smooth_root_pos",
    "root_positions",
    "global_root_heading",
)


def build_npy(
    dtype: str,
    shape: tuple[int, ...],
    payload: bytes,
    *,
    version: tuple[int, int] = (1, 0),
    fortran_order: bool = False,
    header_text: str | None = None,
) -> bytes:
    """Build a canonical enough NPY v1/v2 member for parser tests."""

    prefix_size = 10 if version == (1, 0) else 12
    if header_text is None:
        shape_repr = repr(shape)
        header_text = (
            "{'descr': " + repr(dtype) + ", 'fortran_order': "
            + repr(fortran_order) + ", 'shape': " + shape_repr + ", }"
        )
    raw_header = header_text.encode("ascii")
    padding = (64 - ((prefix_size + len(raw_header) + 1) % 64)) % 64
    header = raw_header + b" " * padding + b"\n"
    length = (
        len(header).to_bytes(2, "little")
        if version == (1, 0) else len(header).to_bytes(4, "little")
    )
    return b"\x93NUMPY" + bytes(version) + length + header + payload


def float_payload(shape: tuple[int, ...], values: list[float] | None = None) -> bytes:
    count = math.prod(shape)
    selected = values if values is not None else [0.0] * count
    if len(selected) != count:
        raise ValueError("float payload value count differs from shape")
    return b"".join(struct.pack("<f", value) for value in selected)


def bool_payload(shape: tuple[int, ...], values: list[bool] | None = None) -> bytes:
    count = math.prod(shape)
    selected = values if values is not None else [False] * count
    if len(selected) != count:
        raise ValueError("boolean payload value count differs from shape")
    return bytes(int(value) for value in selected)


def member_bytes(
    *, frames: int = 3, inventory: str = "complete-v1", contacts: int = 4
) -> dict[str, bytes]:
    names = CORE_NAMES if inventory == "core-v1" else COMPLETE_NAMES
    shapes = {
        "posed_joints": (frames, 77, 3),
        "global_rot_mats": (frames, 77, 3, 3),
        "local_rot_mats": (frames, 77, 3, 3),
        "foot_contacts": (frames, contacts),
        "smooth_root_pos": (frames, 3),
        "root_positions": (frames, 3),
        "global_root_heading": (frames, 2),
    }
    result = {}
    for name in names:
        shape = shapes[name]
        if name == "foot_contacts":
            result[f"{name}.npy"] = build_npy("|b1", shape, bool_payload(shape))
        else:
            result[f"{name}.npy"] = build_npy("<f4", shape, float_payload(shape))
    return result


def build_npz(
    members: dict[str, bytes] | None = None,
    *,
    compression: int = zipfile.ZIP_STORED,
    archive_comment: bytes = b"",
    member_comment: bytes = b"",
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(
        output, "w", compression=compression, allowZip64=False
    ) as archive:
        for name, data in (members or member_bytes()).items():
            info = zipfile.ZipInfo(name)
            info.compress_type = compression
            info.comment = member_comment
            archive.writestr(info, data)
        archive.comment = archive_comment
    return output.getvalue()


def motion_member_bytes(
    *,
    inventory: str = "complete-v1",
    contacts: int = 4,
    loop: bool = False,
    offset_overrides: dict[str, tuple[float, float, float]] | None = None,
    local_overrides: dict[tuple[int, str], tuple[tuple[float, ...], ...]] | None = None,
    global_overrides: dict[tuple[int, str], tuple[tuple[float, ...], ...]] | None = None,
    posed_overrides: dict[tuple[int, str], tuple[float, float, float]] | None = None,
    frame_rotations: tuple[dict[str, float], ...] | None = None,
    contact_rows: tuple[tuple[bool, ...], ...] | None = None,
) -> dict[str, bytes]:
    """Build a three-frame, internally consistent synthetic SOMA77 motion."""

    rotations = frame_rotations or (
        {},
        {"Hips": 10.0, "LeftArm": 20.0, "RightForeArm": -15.0},
        {} if loop else {"Hips": -5.0, "LeftArm": -10.0},
    )
    roots = (
        (0.0, 1.0, 0.0),
        (0.1, 1.0, 0.0),
        (0.0, 1.0, 0.0) if loop else (0.2, 1.0, 0.0),
    )
    offsets = {
        name: tuple(float(value) / 100.0 for value in offset)
        for name, _parent, offset in _JOINTS
    }
    offsets.update(offset_overrides or {})
    local_frames, global_frames, posed_frames = [], [], []
    for frame in range(3):
        local = []
        for name in SOMA77_JOINT_NAMES:
            matrix = _rotate_z(rotations[frame].get(name, 0.0))
            matrix = (local_overrides or {}).get((frame, name), matrix)
            local.append(matrix)
        globals_, points = [], [roots[frame]]
        for joint, (name, parent) in enumerate(zip(
            SOMA77_JOINT_NAMES, SOMA77_PARENT_INDICES
        )):
            global_ = local[joint] if parent is None else _multiply(
                globals_[parent], local[joint]
            )
            global_ = (global_overrides or {}).get((frame, name), global_)
            globals_.append(global_)
            if parent is not None:
                points.append(_add(points[parent], _apply(
                    globals_[parent], offsets[name]
                )))
        for joint, name in enumerate(SOMA77_JOINT_NAMES):
            points[joint] = (posed_overrides or {}).get((frame, name), points[joint])
        local_frames.append(tuple(local))
        global_frames.append(tuple(globals_))
        posed_frames.append(tuple(points))

    selected_contacts = contact_rows or (
        ((True, False, False, False),
         (False, True, True, False),
         (False, False, False, False))
        if contacts == 4 else
        ((True, False, False, False, False, False),
         (False, True, False, True, False, False),
         (False, False, False, False, False, False))
    )
    arrays = {
        "posed_joints": ((3, 77, 3), _flatten_vectors(posed_frames)),
        "global_rot_mats": ((3, 77, 3, 3), _flatten_matrices(global_frames)),
        "local_rot_mats": ((3, 77, 3, 3), _flatten_matrices(local_frames)),
        "root_positions": ((3, 3), [value for row in roots for value in row]),
        "smooth_root_pos": ((3, 3), [value for row in roots for value in row]),
        "global_root_heading": ((3, 2), [0.0, 1.0] * 3),
    }
    names = CORE_NAMES if inventory == "core-v1" else COMPLETE_NAMES
    result = {}
    for name in names:
        if name == "foot_contacts":
            shape = (3, contacts)
            values = [value for row in selected_contacts for value in row]
            result[f"{name}.npy"] = build_npy(
                "|b1", shape, bool_payload(shape, values)
            )
        else:
            shape, values = arrays[name]
            result[f"{name}.npy"] = build_npy(
                "<f4", shape, float_payload(shape, values)
            )
    return result


def _rotate_z(degrees: float) -> tuple[tuple[float, ...], ...]:
    radians = math.radians(degrees)
    cosine, sine = math.cos(radians), math.sin(radians)
    return ((cosine, -sine, 0.0), (sine, cosine, 0.0), (0.0, 0.0, 1.0))


def _multiply(left, right):
    return tuple(tuple(sum(left[row][axis] * right[axis][column]
                           for axis in range(3))
                       for column in range(3)) for row in range(3))


def _apply(matrix, vector):
    return tuple(sum(matrix[row][axis] * vector[axis] for axis in range(3))
                 for row in range(3))


def _add(left, right):
    return tuple(left[index] + right[index] for index in range(3))


def _flatten_vectors(frames):
    return [value for frame in frames for vector in frame for value in vector]


def _flatten_matrices(frames):
    return [
        value
        for frame in frames
        for matrix in frame
        for row in matrix
        for value in row
    ]
