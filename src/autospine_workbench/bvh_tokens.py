"""Bounded byte tokenizer for the ASCII BVH interchange grammar."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib


MAX_BVH_BYTES = 8 * 1024 * 1024
MAX_BVH_TOKENS = 450_000
MAX_BVH_TOKEN_BYTES = 256

_WHITESPACE = frozenset(b" \t\r\n\f\v")
_BRACES = frozenset(b"{}")


class BvhTokenError(ValueError):
    """Raised when raw BVH bytes cannot form one bounded token stream."""


@dataclass(frozen=True, slots=True)
class BvhToken:
    """One immutable ASCII token with a one-based source location."""

    text: str
    byte_offset: int
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class BvhTokenStream:
    """Immutable token snapshot bound directly to the raw input bytes."""

    source_sha256: str
    source_byte_length: int
    tokens: tuple[BvhToken, ...]
    end_line: int
    end_column: int


def tokenize_bvh(raw: bytes) -> BvhTokenStream:
    """Tokenize one bounded ASCII BVH byte snapshot without retaining it."""

    if not isinstance(raw, bytes):
        raise BvhTokenError("BVH source must be an immutable bytes snapshot")
    if len(raw) > MAX_BVH_BYTES:
        raise BvhTokenError(
            f"BVH source exceeds {MAX_BVH_BYTES} bytes at byte 0 (line 1, column 1)"
        )
    tokens: list[BvhToken] = []
    offset = 0
    line = column = 1
    while offset < len(raw):
        value = raw[offset]
        if value in _WHITESPACE:
            offset, line, column = _skip_space(raw, offset, line, column)
            continue
        if value < 0x21 or value > 0x7E:
            _fail("BVH source contains a non-ASCII or control byte", offset, line, column)
        start, start_line, start_column = offset, line, column
        if value in _BRACES:
            offset += 1
            column += 1
        else:
            while offset < len(raw):
                value = raw[offset]
                if value in _WHITESPACE or value in _BRACES:
                    break
                if value < 0x21 or value > 0x7E:
                    _fail(
                        "BVH token contains a non-ASCII or control byte",
                        offset,
                        line,
                        column,
                    )
                offset += 1
                column += 1
                if offset - start > MAX_BVH_TOKEN_BYTES:
                    _fail(
                        f"BVH token exceeds {MAX_BVH_TOKEN_BYTES} bytes",
                        start,
                        start_line,
                        start_column,
                    )
        tokens.append(BvhToken(
            raw[start:offset].decode("ascii"), start, start_line, start_column
        ))
        if len(tokens) > MAX_BVH_TOKENS:
            _fail(
                f"BVH token count exceeds {MAX_BVH_TOKENS}",
                start,
                start_line,
                start_column,
            )
    return BvhTokenStream(
        source_sha256=hashlib.sha256(raw).hexdigest(),
        source_byte_length=len(raw),
        tokens=tuple(tokens),
        end_line=line,
        end_column=column,
    )


def _skip_space(
    raw: bytes, offset: int, line: int, column: int
) -> tuple[int, int, int]:
    value = raw[offset]
    if value == 0x0D:
        offset += 1
        if offset < len(raw) and raw[offset] == 0x0A:
            offset += 1
        return offset, line + 1, 1
    if value == 0x0A:
        return offset + 1, line + 1, 1
    return offset + 1, line, column + 1


def _fail(message: str, offset: int, line: int, column: int) -> None:
    raise BvhTokenError(
        f"{message} at byte {offset} (line {line}, column {column})"
    )
