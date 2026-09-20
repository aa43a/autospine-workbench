"""Read-once ZIP/NPY boundary for content-bound Kimodo SOMA77 snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import io
import json
from pathlib import Path
import zipfile
from typing import Any

from .kimodo_npz_source import (
    MAX_RAW_NPZ_BYTES,
    KimodoNpzSourceError,
    expected_array_names,
    expected_contact_count,
    kimodo_npz_source_sha256,
    require_kimodo_npz_source,
)
from .npy_snapshot import (
    MAX_NPY_MEMBER_BYTES,
    NpyArraySnapshot,
    NpySnapshotError,
    parse_npy_snapshot,
    _decode,
)
from .safe_input_files import SafeInputFileError, read_real_file


MAX_TOTAL_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
_CHUNK_BYTES = 64 * 1024
_COMPRESSION_TYPES = frozenset((zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED))


def inspect_kimodo_npz_profile(raw_npz: bytes) -> tuple[int, str, int]:
    """Discover bounded array dimensions, never infer skeleton identity or FPS."""
    from .kimodo_npz_source import CORE_ARRAY_NAMES, COMPLETE_ARRAY_NAMES, MAX_FRAMES
    if type(raw_npz) is not bytes or not 1 <= len(raw_npz) <= MAX_RAW_NPZ_BYTES:
        raise KimodoNpzReaderError('Kimodo NPZ byte limit exceeded')
    with zipfile.ZipFile(io.BytesIO(raw_npz), allowZip64=False) as archive:
        names = set(archive.namelist())
    complete = names == {name + '.npy' for name in COMPLETE_ARRAY_NAMES}
    members = _read_archive(raw_npz, COMPLETE_ARRAY_NAMES if complete else CORE_ARRAY_NAMES)
    dtype, shape, _ = _decode(members['posed_joints'], 'posed_joints')
    contact_dtype, contacts, _ = _decode(members['foot_contacts'], 'foot_contacts')
    if (dtype != '<f4' or len(shape) != 3 or shape[1:] != (77, 3)
            or not 2 <= shape[0] <= MAX_FRAMES or contact_dtype != '|b1'
            or len(contacts) != 2 or contacts[0] != shape[0] or contacts[1] not in (4, 6)):
        raise KimodoNpzReaderError('Kimodo SOMA77 dimensions are unsupported')
    return shape[0], 'complete-v1' if complete else 'core-v1', contacts[1]


class KimodoNpzReaderError(ValueError):
    """Raised when an NPZ archive cannot form one exact safe snapshot."""


@dataclass(frozen=True, slots=True)
class KimodoNpzSnapshot:
    """Frozen raw archive plus ordered immutable numeric member snapshots."""

    raw_npz_sha256: str
    raw_npz_byte_length: int
    source_sha256: str
    array_inventory_sha256: str
    frame_count: int
    _raw_npz: bytes = field(repr=False)
    _arrays: tuple[NpyArraySnapshot, ...] = field(repr=False)

    @property
    def raw_npz(self) -> bytes:
        return self._raw_npz

    @property
    def arrays(self) -> dict[str, NpyArraySnapshot]:
        return {array.name: array for array in self._arrays}

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(array.name for array in self._arrays)


def read_kimodo_npz(
    path: Path, source: Mapping[str, Any]
) -> KimodoNpzSnapshot:
    """Read one real file exactly once and decode it without extraction."""

    try:
        raw = read_real_file(path, MAX_RAW_NPZ_BYTES, "Kimodo NPZ source")
        return decode_kimodo_npz(raw, source)
    except KimodoNpzReaderError:
        raise
    except SafeInputFileError as exc:
        raise KimodoNpzReaderError("Kimodo NPZ file cannot be safely read") from exc


def decode_kimodo_npz(
    raw_npz: bytes, source: Mapping[str, Any]
) -> KimodoNpzSnapshot:
    """Decode exact bytes through a bounded ZIP and strict NPY profile."""

    try:
        require_kimodo_npz_source(source, raw_npz=raw_npz)
        expected = expected_array_names(source)
        members = _read_archive(raw_npz, expected)
        arrays = _parse_arrays(members, source)
        inventory = _inventory_document(arrays)
        return KimodoNpzSnapshot(
            raw_npz_sha256=hashlib.sha256(raw_npz).hexdigest(),
            raw_npz_byte_length=len(raw_npz),
            source_sha256=kimodo_npz_source_sha256(source),
            array_inventory_sha256=hashlib.sha256(inventory).hexdigest(),
            frame_count=int(source["raw_npz"]["frame_count"]),
            _raw_npz=raw_npz,
            _arrays=arrays,
        )
    except KimodoNpzReaderError:
        raise
    except (
        EOFError,
        KimodoNpzSourceError,
        NpySnapshotError,
        RuntimeError,
        TypeError,
        ValueError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
    ) as exc:
        raise KimodoNpzReaderError(f"Kimodo NPZ decoding failed: {exc}") from exc


def _read_archive(
    raw_npz: bytes, expected_stems: tuple[str, ...]
) -> dict[str, bytes]:
    expected_names = tuple(f"{name}.npy" for name in expected_stems)
    with zipfile.ZipFile(io.BytesIO(raw_npz), "r", allowZip64=False) as archive:
        if archive.comment:
            raise KimodoNpzReaderError("Kimodo NPZ archive comment is unsupported")
        infos = archive.infolist()
        names = tuple(info.filename for info in infos)
        if len(infos) != len(expected_names) or set(names) != set(expected_names) \
                or len({name.casefold() for name in names}) != len(names):
            raise KimodoNpzReaderError(
                "Kimodo NPZ member inventory is incomplete or unexpected"
            )
        total = 0
        by_name: dict[str, zipfile.ZipInfo] = {}
        for info in infos:
            _require_zip_info(info)
            total += info.file_size
            if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise KimodoNpzReaderError(
                    "Kimodo NPZ uncompressed byte budget is exceeded"
                )
            by_name[info.filename] = info
        return {
            stem: _read_member(archive, by_name[f"{stem}.npy"], stem)
            for stem in expected_stems
        }


def _require_zip_info(info: zipfile.ZipInfo) -> None:
    name = info.filename
    if not name.isascii() or "\x00" in name or "/" in name or "\\" in name \
            or info.is_dir() or info.comment or info.flag_bits & 0x1:
        raise KimodoNpzReaderError("Kimodo NPZ member metadata is unsafe")
    if info.compress_type not in _COMPRESSION_TYPES:
        raise KimodoNpzReaderError("Kimodo NPZ compression is unsupported")
    if not 1 <= info.file_size <= MAX_NPY_MEMBER_BYTES \
            or info.compress_size < 0:
        raise KimodoNpzReaderError("Kimodo NPZ member exceeds its byte limit")


def _read_member(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, label: str
) -> bytes:
    chunks, total = [], 0
    with archive.open(info, "r") as member:
        while True:
            chunk = member.read(min(_CHUNK_BYTES, MAX_NPY_MEMBER_BYTES + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_NPY_MEMBER_BYTES:
                raise KimodoNpzReaderError(f"{label} exceeds its byte limit")
            chunks.append(chunk)
        if member.read(1):
            raise KimodoNpzReaderError(f"{label} exceeds its byte limit")
    data = b"".join(chunks)
    if len(data) != info.file_size:
        raise KimodoNpzReaderError(f"{label} changed while it was decoded")
    return data


def _parse_arrays(
    members: dict[str, bytes], source: Mapping[str, Any]
) -> tuple[NpyArraySnapshot, ...]:
    frames = int(source["raw_npz"]["frame_count"])
    joints = int(source["skeleton"]["joint_count"])
    contacts = expected_contact_count(source)
    float_dtype = str(source["array_profile"]["float_dtype"])
    contact_dtype = str(source["array_profile"]["contact_dtype"])
    shapes = {
        "posed_joints": (frames, joints, 3),
        "global_rot_mats": (frames, joints, 3, 3),
        "local_rot_mats": (frames, joints, 3, 3),
        "foot_contacts": (frames, contacts),
        "smooth_root_pos": (frames, 3),
        "root_positions": (frames, 3),
        "global_root_heading": (frames, 2),
    }
    arrays = []
    for name in expected_array_names(source):
        arrays.append(parse_npy_snapshot(
            members[name],
            name=name,
            expected_dtype=contact_dtype if name == "foot_contacts" else float_dtype,
            expected_shape=shapes[name],
        ))
    return tuple(arrays)


def _inventory_document(arrays: tuple[NpyArraySnapshot, ...]) -> bytes:
    document: list[dict[str, Any]] = []
    for array in arrays:
        document.append({
            "name": array.name,
            "dtype": array.dtype,
            "shape": list(array.shape),
            "raw_npy_sha256": array.raw_npy_sha256,
            "payload_sha256": array.payload_sha256,
            "payload_byte_length": len(array.payload),
        })
    return json.dumps(
        document, ensure_ascii=True, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("ascii")
