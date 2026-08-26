"""Standard-library builders for deterministic synthetic Kimodo NPZ bytes."""

from __future__ import annotations

import io
import math
import struct
import zipfile


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
