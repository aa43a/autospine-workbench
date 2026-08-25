"""Pure deterministic compilation from explicit BVH input to MotionIR v1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .bvh_contact import BvhContactError, detect_bvh_contacts
from .bvh_fk import (
    PRECISION_DECIMALS,
    BvhFkError,
    BvhProjectedFrames,
    project_bvh_frames,
)
from .bvh_map_validation import BvhMapValidationError, require_bvh_map
from .bvh_parser import BvhParseError, parse_bvh
from .bvh_tokens import BvhTokenError
from .motion_validation import (
    FORMAT,
    FORMAT_VERSION,
    TICKS_PER_SECOND,
    MotionValidationError,
    motion_coordinate_system,
    motion_ir_sha256,
    require_motion_ir,
)


COMPILER_ID = "bvh-motionir-compiler"
COMPILER_VERSION = "1.0.0"
FK_PROFILE = "declared-channel-postmultiply-3d-affine-v1"
PROJECTION_PROFILE = "explicit-signed-basis-v1"
ROTATION_PROFILE = "projected-setup-local-delta-v1"
CONTACT_PROFILE = "source-world-3d-contact-v1"
CONTACT_VELOCITY_PROFILE = (
    "backward-first-forward-loop-seam-bidirectional-max-v1"
)
CONTACT_INTERVAL_PROFILE = "gap-fill-then-minimum-half-open-v1"
TICK_PROFILE = "decimal-half-up-microsecond-v1"
LOOP_PROFILE = "quantized-full-projection-equality-v1"
DECIMAL_PLACES = PRECISION_DECIMALS


class BvhMotionCompilerError(ValueError):
    """Raised when explicit BVH evidence cannot form safe canonical MotionIR."""


@dataclass(frozen=True, slots=True)
class CompiledBvhMotion:
    """Frozen canonical MotionIR snapshot with isolated JSON access."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_json(self) -> str:
        return self._canonical_json

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def bvh_motion_compiler_config() -> dict[str, Any]:
    """Return a fresh copy of the exact, provenance-safe compiler profile."""

    return {
        "fk": FK_PROFILE,
        "projection": PROJECTION_PROFILE,
        "rotation": ROTATION_PROFILE,
        "contact": CONTACT_PROFILE,
        "contact_velocity": CONTACT_VELOCITY_PROFILE,
        "contact_intervals": CONTACT_INTERVAL_PROFILE,
        "tick_schedule": TICK_PROFILE,
        "loop_closure": LOOP_PROFILE,
        "ticks_per_second": TICKS_PER_SECOND,
        "decimal_places": DECIMAL_PLACES,
    }


def compile_bvh_motion(
    raw_bvh: bytes,
    bvh_map: Mapping[str, Any],
) -> CompiledBvhMotion:
    """Compile immutable bytes and one explicit map without filesystem access."""

    try:
        explicit_map = _snapshot_map(bvh_map)
        bvh = parse_bvh(raw_bvh)
        projected = project_bvh_frames(bvh, explicit_map)
        document = _motion_document(projected, bvh, explicit_map)
        require_motion_ir(document)
        encoded = _canonical(document)
        result = CompiledBvhMotion(encoded)
        if result.sha256 != motion_ir_sha256(result.document):
            raise BvhMotionCompilerError(
                "BVH compiler canonical MotionIR identity is inconsistent"
            )
        return result
    except BvhMotionCompilerError:
        raise
    except (
        BvhContactError,
        BvhFkError,
        BvhMapValidationError,
        BvhParseError,
        BvhTokenError,
        MotionValidationError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise BvhMotionCompilerError(
            f"BVH to MotionIR compilation failed: {exc}"
        ) from exc


def _snapshot_map(value: Mapping[str, Any]) -> dict[str, Any]:
    require_bvh_map(value)
    encoded = _canonical(value)
    snapshot = json.loads(encoded)
    require_bvh_map(snapshot)
    return snapshot


def _motion_document(projected, bvh, bvh_map) -> dict[str, Any]:
    contacts = detect_bvh_contacts(
        bvh,
        bvh_map,
        projected=projected,
    )
    tracks = _rotation_tracks(projected)
    tracks.append({
        "target_kind": "bone_role",
        "target": "humanoid.root",
        "property": "translation",
        "interpolation": "linear",
        "keys": [
            {"tick": frame.tick, "value": list(frame.root_translation_normalized)}
            for frame in projected.frames
        ],
    })
    tracks.sort(key=_track_identity)
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "clip_id": projected.clip_id,
        "ticks_per_second": TICKS_PER_SECOND,
        "duration_ticks": projected.duration_ticks,
        "loop": projected.loop,
        "coordinate_system": motion_coordinate_system(),
        "tracks": tracks,
        "markers": [marker.document for marker in contacts],
    }


def _rotation_tracks(projected: BvhProjectedFrames) -> list[dict[str, Any]]:
    if not projected.frames or not projected.frames[0].segments:
        raise BvhMotionCompilerError("BVH projection contains no mapped motion tracks")
    roles = tuple(segment.role for segment in projected.frames[0].segments)
    tracks = []
    for role_index, role in enumerate(roles):
        keys = []
        for frame in projected.frames:
            current_roles = tuple(segment.role for segment in frame.segments)
            if current_roles != roles:
                raise BvhMotionCompilerError(
                    "BVH projection mapped role inventory changed between frames"
                )
            keys.append({
                "tick": frame.tick,
                "value": frame.segments[role_index].setup_local_additive_delta_deg,
            })
        tracks.append({
            "target_kind": "bone_role",
            "target": role,
            "property": "rotation",
            "interpolation": "linear",
            "keys": keys,
        })
    return tracks


def _track_identity(track: Mapping[str, Any]) -> tuple[str, str, str]:
    return str(track["target_kind"]), str(track["target"]), str(track["property"])


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
