"""Deterministic target-independent MotionIR v1 built-in clips."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable

from .motion_validation import (
    FORMAT,
    FORMAT_VERSION,
    TICKS_PER_SECOND,
    MotionValidationError,
    motion_coordinate_system,
    require_motion_ir,
)


DURATION = 2 * TICKS_PER_SECOND
SUPPORTED_BUILTIN_CLIPS = ("idle", "wave.left")


class BuiltinMotionError(ValueError):
    """Raised when a requested built-in clip is unknown or internally invalid."""


@dataclass(frozen=True, slots=True)
class BuiltinMotion:
    """Frozen canonical MotionIR snapshot with isolated JSON access."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_json(self) -> str:
        return self._canonical_json

    @property
    def clip_id(self) -> str:
        return self.document["clip_id"]

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self._canonical_json.encode("utf-8")).hexdigest()


def build_builtin_motion(clip_id: str) -> BuiltinMotion:
    """Build one exact reusable clip without randomness or target-rig input."""
    builders: dict[str, Callable[[], dict[str, Any]]] = {
        "idle": _idle,
        "wave.left": _wave_left,
    }
    if type(clip_id) is not str or clip_id not in builders:
        raise BuiltinMotionError(f"Unsupported built-in MotionIR clip: {clip_id!r}")
    document = builders[clip_id]()
    try:
        require_motion_ir(document)
        encoded = json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        )
    except (MotionValidationError, TypeError, ValueError) as exc:
        raise BuiltinMotionError("Built-in MotionIR failed its frozen contract") from exc
    return BuiltinMotion(encoded)


def _base(clip_id: str, *, loop: bool, tracks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "clip_id": clip_id,
        "ticks_per_second": TICKS_PER_SECOND,
        "duration_ticks": DURATION,
        "loop": loop,
        "coordinate_system": motion_coordinate_system(),
        "tracks": tracks,
        "markers": [_contact("leg.left"), _contact("leg.right")],
    }


def _rotation(target: str, ticks: tuple[int, ...], values: tuple[float, ...]):
    return _track("bone_role", target, "rotation", ticks, values)


def _track(kind: str, target: str, prop: str, ticks, values):
    return {
        "target_kind": kind,
        "target": target,
        "property": prop,
        "interpolation": "linear",
        "keys": [
            {"tick": tick, "value": value}
            for tick, value in zip(ticks, values, strict=True)
        ],
    }


def _contact(limb: str) -> dict[str, Any]:
    return {
        "kind": "contact",
        "limb": limb,
        "start_tick": 0,
        "end_tick": DURATION,
        "mode": "annotation_only",
    }


def _idle() -> dict[str, Any]:
    half = TICKS_PER_SECOND // 2
    full = TICKS_PER_SECOND
    return _base("idle", loop=True, tracks=[
        _rotation("humanoid.head", (0, half, full, full + half, DURATION),
                  (0.0, -1.0, 0.0, 1.0, 0.0)),
        _track("bone_role", "humanoid.root", "translation",
               (0, full, DURATION), ([0.0, 0.0], [0.0, -0.005], [0.0, 0.0])),
        _rotation("humanoid.spine.lower", (0, full, DURATION), (0.0, 0.75, 0.0)),
        _rotation("humanoid.spine.upper", (0, full, DURATION), (0.0, -1.5, 0.0)),
    ])


def _wave_left() -> dict[str, Any]:
    return _base("wave.left", loop=False, tracks=[
        _rotation("humanoid.clavicle.left", (0, 500_000, 1_500_000, DURATION),
                  (0.0, -5.0, -5.0, 0.0)),
        _track("ik_handle", "arm.left", "target",
               (0, 400_000, 800_000, 1_200_000, 1_600_000, DURATION),
               ("setup", [0.35, 0.65], [0.55, 0.65], [0.35, 0.75],
                [0.55, 0.65], "setup")),
    ])
