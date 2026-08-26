"""Strict bounded parser for BVH hierarchy and motion sample syntax."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re

from .bvh_tokens import BvhToken, BvhTokenStream, tokenize_bvh


MAX_BVH_JOINTS = 256
MAX_BVH_DEPTH = 64
MAX_BVH_FRAMES = 20_000
MAX_BVH_TOTAL_SAMPLES = 400_000
MAX_BVH_ABS_VALUE = 1_000_000.0
MAX_BVH_FRAME_TIME_SECONDS = 60.0

_FLOAT = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?")
_INTEGER = re.compile(r"\d+")
_POSITION = frozenset(("Xposition", "Yposition", "Zposition"))
_ROTATION = frozenset(("Xrotation", "Yrotation", "Zrotation"))
_RESERVED_NAMES = frozenset((
    "HIERARCHY", "ROOT", "JOINT", "End", "Site", "OFFSET", "CHANNELS",
    "MOTION", "Frames", "Frames:", "Frame", "Time", "Time:", "{", "}",
))


class BvhParseError(ValueError):
    """Raised when a bounded token stream is not in the supported BVH profile."""


@dataclass(frozen=True, slots=True)
class BvhJoint:
    """One declaration-order joint with setup offset and source channel order."""

    name: str
    parent_index: int | None
    offset: tuple[float, float, float]
    channels: tuple[str, ...]
    rotation_order: tuple[str, str, str]
    end_site_offset: tuple[float, float, float] | None


@dataclass(frozen=True, slots=True)
class BvhDocument:
    """Immutable syntax-only BVH snapshot; no axis or FK semantics are inferred."""

    source_sha256: str
    source_byte_length: int
    joints: tuple[BvhJoint, ...]
    frame_count: int
    frame_time_seconds: float
    channel_count: int
    frames: tuple[tuple[float, ...], ...]

    @property
    def total_sample_count(self) -> int:
        return self.frame_count * self.channel_count


def parse_bvh(raw: bytes) -> BvhDocument:
    """Tokenize and parse one immutable raw BVH byte snapshot."""

    return _parse_bvh_tokens(tokenize_bvh(raw))


def _parse_bvh_tokens(stream: BvhTokenStream) -> BvhDocument:
    """Parse the tokenizer-owned snapshot; public callers must use raw bytes."""

    if not isinstance(stream, BvhTokenStream):
        raise BvhParseError("BVH parser requires a BvhTokenStream")
    return _Parser(stream).parse()


class _Parser:
    def __init__(self, stream: BvhTokenStream) -> None:
        self.stream = stream
        self.tokens = stream.tokens
        self.cursor = 0
        self.joints: list[BvhJoint] = []
        self.names: set[str] = set()

    def parse(self) -> BvhDocument:
        self._expect("HIERARCHY")
        self._expect("ROOT")
        self._joint(parent=None, depth=1, root=True)
        self._expect("MOTION")
        self._label("Frames")
        frame_count = self._integer("frame count")
        if frame_count > MAX_BVH_FRAMES:
            self._fail(f"BVH frame count exceeds {MAX_BVH_FRAMES}")
        self._expect("Frame")
        self._label("Time")
        frame_time = self._number("frame time")
        if frame_time <= 0 or frame_time > MAX_BVH_FRAME_TIME_SECONDS:
            self._fail(
                "BVH frame time must be positive and no greater than "
                f"{MAX_BVH_FRAME_TIME_SECONDS} seconds"
            )
        channel_count = sum(len(joint.channels) for joint in self.joints)
        sample_count = frame_count * channel_count
        if sample_count > MAX_BVH_TOTAL_SAMPLES:
            self._fail(
                f"BVH sample count exceeds {MAX_BVH_TOTAL_SAMPLES}"
            )
        frames = tuple(
            tuple(self._number("motion sample") for _ in range(channel_count))
            for _ in range(frame_count)
        )
        if self.cursor != len(self.tokens):
            self._fail("BVH contains extra tokens after motion samples")
        return BvhDocument(
            source_sha256=self.stream.source_sha256,
            source_byte_length=self.stream.source_byte_length,
            joints=tuple(self.joints),
            frame_count=frame_count,
            frame_time_seconds=frame_time,
            channel_count=channel_count,
            frames=frames,
        )

    def _joint(self, parent: int | None, depth: int, root: bool) -> int:
        if depth > MAX_BVH_DEPTH:
            self._fail(f"BVH hierarchy depth exceeds {MAX_BVH_DEPTH}")
        name_token = self._take("joint name")
        name = name_token.text
        if name in _RESERVED_NAMES or name.endswith(":"):
            self._fail("BVH joint name is invalid", name_token)
        if name in self.names:
            self._fail(f"BVH joint name is duplicated: {name}", name_token)
        if len(self.joints) >= MAX_BVH_JOINTS:
            self._fail(f"BVH joint count exceeds {MAX_BVH_JOINTS}", name_token)
        self.names.add(name)
        index = len(self.joints)
        self.joints.append(BvhJoint(
            name, parent, (0.0, 0.0, 0.0), (), ("", "", ""), None
        ))
        self._expect("{")
        self._expect("OFFSET")
        offset = self._vector("joint offset")
        self._expect("CHANNELS")
        count = self._integer("channel count")
        expected_counts = (6,) if root else (3, 6)
        if count not in expected_counts:
            kind = "root" if root else "non-root"
            self._fail(
                f"BVH {kind} channel count must be "
                f"{'6' if root else '3 or 6'}"
            )
        channels = tuple(self._take("channel").text for _ in range(count))
        rotations = self._channels(channels, root)
        end_site = None
        while self._peek("JOINT"):
            self._expect("JOINT")
            self._joint(index, depth + 1, False)
        if self._peek("End"):
            self._expect("End")
            self._expect("Site")
            self._expect("{")
            self._expect("OFFSET")
            end_site = self._vector("End Site offset")
            self._expect("}")
        self._expect("}")
        self.joints[index] = BvhJoint(
            name, parent, offset, channels, rotations, end_site
        )
        return index

    def _channels(
        self, channels: tuple[str, ...], root: bool
    ) -> tuple[str, str, str]:
        allowed = _POSITION | _ROTATION if len(channels) == 6 else _ROTATION
        if root and len(channels) != 6 or len(channels) not in (3, 6) \
                or set(channels) != allowed:
            kind = "root" if root else "non-root"
            self._fail(
                f"BVH {kind} channels must contain each allowed channel exactly once"
            )
        rotations = tuple(value for value in channels if value in _ROTATION)
        return rotations[0], rotations[1], rotations[2]

    def _vector(self, label: str) -> tuple[float, float, float]:
        return (
            self._number(label), self._number(label), self._number(label)
        )

    def _integer(self, label: str) -> int:
        token = self._take(label)
        if not _INTEGER.fullmatch(token.text):
            self._fail(f"BVH {label} is not a non-negative integer", token)
        return int(token.text)

    def _number(self, label: str) -> float:
        token = self._take(label)
        if not _FLOAT.fullmatch(token.text):
            self._fail(f"BVH {label} is not a number", token)
        value = float(token.text)
        if not math.isfinite(value):
            self._fail(f"BVH {label} is not finite", token)
        if abs(value) > MAX_BVH_ABS_VALUE:
            self._fail(
                f"BVH {label} exceeds absolute limit {MAX_BVH_ABS_VALUE}",
                token,
            )
        return value

    def _label(self, text: str) -> None:
        token = self._take(f"{text}: label")
        if token.text == f"{text}:":
            return
        if token.text != text:
            self._fail(f"Expected BVH label {text}:", token)
        self._expect(":")

    def _peek(self, text: str) -> bool:
        return self.cursor < len(self.tokens) and self.tokens[self.cursor].text == text

    def _expect(self, text: str) -> BvhToken:
        token = self._take(text)
        if token.text != text:
            self._fail(f"Expected BVH token {text}", token)
        return token

    def _take(self, expected: str) -> BvhToken:
        if self.cursor >= len(self.tokens):
            self._fail(f"BVH is truncated; expected {expected}")
        token = self.tokens[self.cursor]
        self.cursor += 1
        return token

    def _fail(self, message: str, token: BvhToken | None = None) -> None:
        if token is None and self.cursor < len(self.tokens):
            token = self.tokens[self.cursor]
        if token is None:
            raise BvhParseError(
                f"{message} at byte {self.stream.source_byte_length} "
                f"(line {self.stream.end_line}, column {self.stream.end_column})"
            )
        raise BvhParseError(
            f"{message} at byte {token.byte_offset} "
            f"(line {token.line}, column {token.column})"
        )
