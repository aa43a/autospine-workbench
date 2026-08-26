"""Small fail-closed NPY v1/v2 decoder for immutable numeric snapshots."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
import hashlib
import math
import struct
from typing import Iterator


MAX_NPY_MEMBER_BYTES = 64 * 1024 * 1024
MAX_NPY_HEADER_BYTES = 10_000
_MAGIC = b"\x93NUMPY"
_ITEM_SIZES = {"<f4": 4, "|b1": 1}


class NpySnapshotError(ValueError):
    """Raised when an NPY member is ambiguous, executable, or malformed."""


@dataclass(frozen=True, slots=True)
class NpyArraySnapshot:
    """Frozen C-order primitive array backed by immutable payload bytes."""

    name: str
    dtype: str
    shape: tuple[int, ...]
    raw_npy_sha256: str
    _payload: bytes = field(repr=False)

    @property
    def payload(self) -> bytes:
        return self._payload

    @property
    def payload_sha256(self) -> str:
        return hashlib.sha256(self._payload).hexdigest()

    @property
    def item_count(self) -> int:
        return len(self._payload) // _ITEM_SIZES[self.dtype]

    def float_at(self, *indices: int) -> float:
        """Read one little-endian float without exposing mutable storage."""

        if self.dtype != "<f4":
            raise NpySnapshotError(f"{self.name} is not a float32 array")
        offset = self._flat_index(indices) * 4
        return struct.unpack_from("<f", self._payload, offset)[0]

    def bool_at(self, *indices: int) -> bool:
        """Read one canonical NPY boolean value."""

        if self.dtype != "|b1":
            raise NpySnapshotError(f"{self.name} is not a boolean array")
        return bool(self._payload[self._flat_index(indices)])

    def iter_floats(self) -> Iterator[float]:
        """Iterate immutable float32 payload values in C order."""

        if self.dtype != "<f4":
            raise NpySnapshotError(f"{self.name} is not a float32 array")
        return (value[0] for value in struct.iter_unpack("<f", self._payload))

    def _flat_index(self, indices: tuple[int, ...]) -> int:
        if len(indices) != len(self.shape):
            raise NpySnapshotError(f"{self.name} index rank differs from its shape")
        flat = 0
        for index, extent in zip(indices, self.shape):
            if type(index) is not int or not 0 <= index < extent:
                raise NpySnapshotError(f"{self.name} index is outside its shape")
            flat = flat * extent + index
        return flat


def parse_npy_snapshot(
    raw: bytes,
    *,
    name: str,
    expected_dtype: str,
    expected_shape: tuple[int, ...],
) -> NpyArraySnapshot:
    """Parse one exact NPY member without NumPy or pickle support."""

    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_NPY_MEMBER_BYTES:
            raise NpySnapshotError(f"{name} NPY member exceeds its byte limit")
        if not isinstance(name, str) or not name:
            raise NpySnapshotError("NPY member name is invalid")
        dtype, shape, payload = _decode(raw, name)
        if dtype != expected_dtype or shape != expected_shape:
            raise NpySnapshotError(f"{name} NPY dtype or shape differs from profile")
        return NpyArraySnapshot(
            name=name,
            dtype=dtype,
            shape=shape,
            raw_npy_sha256=hashlib.sha256(raw).hexdigest(),
            _payload=payload,
        )
    except NpySnapshotError:
        raise
    except (MemoryError, OverflowError, struct.error, TypeError, ValueError) as exc:
        raise NpySnapshotError(f"{name} NPY decoding failed: {exc}") from exc


def _decode(raw: bytes, name: str) -> tuple[str, tuple[int, ...], bytes]:
    if len(raw) < 10 or raw[:6] != _MAGIC:
        raise NpySnapshotError(f"{name} is not an NPY member")
    version = tuple(raw[6:8])
    if version == (1, 0):
        length_size, header_start = 2, 10
    elif version == (2, 0):
        length_size, header_start = 4, 12
    else:
        raise NpySnapshotError(f"{name} NPY version is unsupported")
    if len(raw) < header_start:
        raise NpySnapshotError(f"{name} NPY header is truncated")
    header_length = int.from_bytes(raw[8:8 + length_size], "little")
    if not 1 <= header_length <= MAX_NPY_HEADER_BYTES:
        raise NpySnapshotError(f"{name} NPY header exceeds its byte limit")
    payload_start = header_start + header_length
    if payload_start > len(raw):
        raise NpySnapshotError(f"{name} NPY header is truncated")
    header = raw[header_start:payload_start]
    if not header.endswith(b"\n") or not header.isascii():
        raise NpySnapshotError(f"{name} NPY header encoding is unsupported")
    dtype, fortran_order, shape = _parse_header(header, name)
    if dtype not in _ITEM_SIZES:
        raise NpySnapshotError(f"{name} NPY dtype is unsafe or unsupported")
    if fortran_order:
        raise NpySnapshotError(f"{name} NPY Fortran order is unsupported")
    expected = _payload_size(shape, _ITEM_SIZES[dtype], name)
    payload = raw[payload_start:]
    if len(payload) != expected:
        raise NpySnapshotError(f"{name} NPY payload length differs from its shape")
    _require_values(payload, dtype, name)
    return dtype, shape, payload


def _parse_header(header: bytes, name: str) -> tuple[str, bool, tuple[int, ...]]:
    try:
        expression = ast.parse(header.decode("ascii").strip(), mode="eval").body
    except (SyntaxError, UnicodeError, ValueError) as exc:
        raise NpySnapshotError(f"{name} NPY header literal is invalid") from exc
    if not isinstance(expression, ast.Dict) or len(expression.keys) != 3:
        raise NpySnapshotError(f"{name} NPY header fields are unsupported")
    fields = {}
    for key_node, value_node in zip(expression.keys, expression.values):
        if not isinstance(key_node, ast.Constant) or type(key_node.value) is not str:
            raise NpySnapshotError(f"{name} NPY header key is invalid")
        key = key_node.value
        if key in fields:
            raise NpySnapshotError(f"{name} NPY header contains a duplicate key")
        fields[key] = value_node
    if set(fields) != {"descr", "fortran_order", "shape"}:
        raise NpySnapshotError(f"{name} NPY header fields are unsupported")
    descr_node = fields["descr"]
    order_node = fields["fortran_order"]
    if not isinstance(descr_node, ast.Constant) \
            or type(descr_node.value) is not str \
            or not isinstance(order_node, ast.Constant) \
            or type(order_node.value) is not bool:
        raise NpySnapshotError(f"{name} NPY scalar header fields are invalid")
    shape = _shape(fields["shape"], name)
    return descr_node.value, order_node.value, shape


def _shape(node: ast.AST, name: str) -> tuple[int, ...]:
    if not isinstance(node, ast.Tuple) or not 1 <= len(node.elts) <= 5:
        raise NpySnapshotError(f"{name} NPY shape is invalid")
    result = []
    for item in node.elts:
        if not isinstance(item, ast.Constant) or type(item.value) is not int \
                or item.value < 1:
            raise NpySnapshotError(f"{name} NPY shape is invalid")
        result.append(item.value)
    return tuple(result)


def _payload_size(shape: tuple[int, ...], item_size: int, name: str) -> int:
    count = 1
    for extent in shape:
        count *= extent
        if count > MAX_NPY_MEMBER_BYTES:
            raise NpySnapshotError(f"{name} NPY shape exceeds its resource limit")
    size = count * item_size
    if size > MAX_NPY_MEMBER_BYTES:
        raise NpySnapshotError(f"{name} NPY payload exceeds its byte limit")
    return size


def _require_values(payload: bytes, dtype: str, name: str) -> None:
    if dtype == "|b1":
        if any(value not in (0, 1) for value in payload):
            raise NpySnapshotError(f"{name} NPY booleans are not canonical")
        return
    if any(not math.isfinite(value[0]) for value in struct.iter_unpack("<f", payload)):
        raise NpySnapshotError(f"{name} NPY contains a non-finite float")
