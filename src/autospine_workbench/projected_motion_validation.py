"""Strict semantic validation for target-independent ProjectedMotionIR v1."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
from typing import Any

from .motion_roles import (
    CONTACT_LIMBS,
)
from .motion_validation import MAX_DURATION_TICKS, TICKS_PER_SECOND
from .projected_motion_geometry_validation import (
    ProjectedMotionValidationError,
    require_projected_segment_tracks,
)
from .resolved_project import canonical_sha256


FORMAT = "autospine-projected-motion-ir"
FORMAT_VERSION = 1
MAX_FRAMES = 4096
MAX_MARKERS = 256
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
MAX_ABS_NORMALIZED = 1024.0
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOP = {
    "format", "format_version", "clip_id", "timing", "source",
    "camera_sha256", "frames", "root_samples", "segment_tracks", "markers",
}
_TIMING = {
    "ticks_per_second", "duration_ticks", "loop", "frame_count",
}
_SOURCE = {
    "kind", "motion_ir_sha256", "motion_bundle_sha256", "motion_run_sha256",
    "raw_npz_sha256", "source_sha256", "map_sha256",
    "array_inventory_sha256",
}
_FRAME = {"source_frame_index", "tick"}
_ROOT_SAMPLE = {
    "source_frame_index", "tick", "screen_translation_normalized",
    "depth_translation_normalized",
}
_MARKER = {"kind", "limb", "start_tick", "end_tick", "mode"}


def require_projected_motion_ir(document: Mapping[str, Any]) -> None:
    """Fail closed on ProjectedMotionIR shape, order, geometry, and resources."""

    try:
        root = _object(document, "ProjectedMotionIR")
        _exact(root, _TOP, "ProjectedMotionIR")
        _identity(root)
        duration, loop, frame_count = _timing(root.get("timing"))
        _source(root.get("source"))
        _sha(root.get("camera_sha256"), "camera_sha256")
        frames = _frames(root.get("frames"), duration, frame_count)
        _root_samples(root.get("root_samples"), frames, loop)
        require_projected_segment_tracks(root.get("segment_tracks"), frames, loop)
        _markers(root.get("markers"), duration)
        encoded = json.dumps(
            dict(root), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise ProjectedMotionValidationError(
                "ProjectedMotionIR document byte limit exceeded"
            )
    except ProjectedMotionValidationError:
        raise
    except (KeyError, OverflowError, TypeError, ValueError) as exc:
        raise ProjectedMotionValidationError(
            f"ProjectedMotionIR validation failed: {exc}"
        ) from exc


def projected_motion_ir_sha256(document: Mapping[str, Any]) -> str:
    """Return canonical identity only after complete semantic validation."""

    require_projected_motion_ir(document)
    try:
        return canonical_sha256(document)
    except (TypeError, ValueError) as exc:
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR is not canonical JSON"
        ) from exc


def _identity(root: Mapping[str, Any]) -> None:
    if root.get("format") != FORMAT \
            or type(root.get("format_version")) is not int \
            or root.get("format_version") != FORMAT_VERSION:
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR format version is unsupported"
        )
    _safe_id(root.get("clip_id"), "clip_id")


def _timing(value: Any) -> tuple[int, bool, int]:
    timing = _object(value, "ProjectedMotionIR timing")
    _exact(timing, _TIMING, "ProjectedMotionIR timing")
    if type(timing.get("ticks_per_second")) is not int \
            or timing.get("ticks_per_second") != TICKS_PER_SECOND:
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR tick rate is unsupported"
        )
    duration = _tick(timing.get("duration_ticks"), "duration_ticks")
    if not 1 <= duration <= MAX_DURATION_TICKS:
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR duration exceeds its resource limit"
        )
    if type(timing.get("loop")) is not bool:
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR loop must be boolean"
        )
    frame_count = timing.get("frame_count")
    if type(frame_count) is not int or not 2 <= frame_count <= MAX_FRAMES:
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR frame count exceeds its resource limit"
        )
    return duration, timing["loop"], frame_count


def _source(value: Any) -> None:
    source = _object(value, "ProjectedMotionIR source")
    _exact(source, _SOURCE, "ProjectedMotionIR source")
    if source.get("kind") != "kimodo_npz":
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR source kind is unsupported"
        )
    for field in _SOURCE - {"kind"}:
        _sha(source.get(field), field)


def _frames(value: Any, duration: int, count: int) -> tuple[tuple[int, int], ...]:
    rows = _array(value, "ProjectedMotionIR frames")
    if len(rows) != count:
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR frame count differs from timing"
        )
    result = []
    previous_tick = -1
    for index, raw in enumerate(rows):
        row = _object(raw, "ProjectedMotionIR frame")
        _exact(row, _FRAME, "ProjectedMotionIR frame")
        tick = _tick(row.get("tick"), "frame tick")
        if row.get("source_frame_index") != index or tick <= previous_tick:
            raise ProjectedMotionValidationError(
                "ProjectedMotionIR frames must be consecutive and increasing"
            )
        previous_tick = tick
        result.append((index, tick))
    if result[0][1] != 0 or result[-1][1] != duration:
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR frames must span tick 0 through duration"
        )
    return tuple(result)


def _root_samples(value: Any, frames, loop: bool) -> None:
    rows = _array(value, "ProjectedMotionIR root samples")
    if len(rows) != len(frames):
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR root samples differ from frames"
        )
    payloads = []
    for expected, raw in zip(frames, rows):
        row = _object(raw, "ProjectedMotionIR root sample")
        _exact(row, _ROOT_SAMPLE, "ProjectedMotionIR root sample")
        _sample_identity(row, expected, "root sample")
        screen = _vector2(row.get("screen_translation_normalized"), "root screen")
        depth = _number(
            row.get("depth_translation_normalized"), "root depth",
            MAX_ABS_NORMALIZED,
        )
        payloads.append((screen, depth))
    if payloads[0] != ((0.0, 0.0), 0.0):
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR root frame zero must be its origin"
        )
    if loop and payloads[0] != payloads[-1]:
        raise ProjectedMotionValidationError(
            "Looping ProjectedMotionIR root endpoints must match"
        )


def _markers(value: Any, duration: int) -> None:
    rows = _array(value, "ProjectedMotionIR markers")
    if len(rows) > MAX_MARKERS:
        raise ProjectedMotionValidationError(
            "ProjectedMotionIR marker resource limit exceeded"
        )
    previous, seen, limb_ends = None, set(), {}
    for raw in rows:
        row = _object(raw, "ProjectedMotionIR marker")
        _exact(row, _MARKER, "ProjectedMotionIR marker")
        start = _tick(row.get("start_tick"), "marker start")
        end = _tick(row.get("end_tick"), "marker end")
        limb = row.get("limb")
        identity = (start, end, str(limb))
        if row.get("kind") != "contact" or limb not in CONTACT_LIMBS \
                or row.get("mode") != "annotation_only" \
                or start >= end or end > duration:
            raise ProjectedMotionValidationError(
                "ProjectedMotionIR marker semantics are unsupported"
            )
        if identity in seen or (previous is not None and identity <= previous) \
                or start < limb_ends.get(limb, -1):
            raise ProjectedMotionValidationError(
                "ProjectedMotionIR markers must be sorted and non-overlapping"
            )
        seen.add(identity)
        previous = identity
        limb_ends[limb] = end


def _sample_identity(row: Mapping[str, Any], expected, label: str) -> None:
    if row.get("source_frame_index") != expected[0] \
            or row.get("tick") != expected[1]:
        raise ProjectedMotionValidationError(
            f"ProjectedMotionIR {label} differs from frames"
        )


def _vector2(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ProjectedMotionValidationError(
            f"ProjectedMotionIR {label} must contain x and y"
        )
    return (
        _number(value[0], f"{label} x", MAX_ABS_NORMALIZED),
        _number(value[1], f"{label} y", MAX_ABS_NORMALIZED),
    )


def _number(value: Any, label: str, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or abs(float(value)) > maximum:
        raise ProjectedMotionValidationError(
            f"ProjectedMotionIR {label} must be finite and bounded"
        )
    return float(value)


def _tick(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ProjectedMotionValidationError(
            f"ProjectedMotionIR {label} must be a non-negative integer tick"
        )
    return value


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ProjectedMotionValidationError(
            f"ProjectedMotionIR {label} must be a lowercase SHA-256"
        )
    return value


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ProjectedMotionValidationError(
            f"ProjectedMotionIR {label} is invalid"
        )
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProjectedMotionValidationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProjectedMotionValidationError(f"{label} must be an array")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise ProjectedMotionValidationError(
            f"{label} fields are incomplete or unsupported"
        )
