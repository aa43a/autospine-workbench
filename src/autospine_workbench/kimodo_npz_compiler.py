"""Pure deterministic compiler from formal Kimodo NPZ to MotionIR v1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .kimodo_npz_consistency import (
    HEADING_NORM_TOLERANCE,
    MATRIX_CROSSCHECK_TOLERANCE,
    MATRIX_ORTHONORMAL_TOLERANCE,
    POSITION_CROSSCHECK_METERS,
    KimodoNpzConsistencyError,
    validate_kimodo_consistency,
)
from .kimodo_npz_contact import KimodoNpzContactError, kimodo_contact_markers
from .kimodo_npz_map_validation import KimodoNpzMapError, require_kimodo_npz_map
from .kimodo_npz_projection import (
    PRECISION_DECIMALS,
    KimodoNpzProjectionError,
    project_kimodo_frames,
)
from .kimodo_npz_reader import (
    KimodoNpzReaderError,
    decode_kimodo_npz,
)
from .kimodo_npz_source import KimodoNpzSourceError, require_kimodo_npz_source
from .kimodo_soma77 import SOMA77_DEFINITION_SHA256
from .motion_validation import (
    FORMAT,
    FORMAT_VERSION,
    TICKS_PER_SECOND,
    MotionValidationError,
    motion_coordinate_system,
    motion_ir_sha256,
    require_motion_ir,
)


COMPILER_ID = "kimodo-npz-motionir-compiler"
COMPILER_VERSION = "1.1.0"
READER_PROFILE = "stdlib-zip-npy-v1-v2-primitive-c-order-v1"
CONSISTENCY_PROFILE = "soma77-local-root-matrix-fk-crosscheck-v1"
PROJECTION_PROFILE = "explicit-signed-basis-projected-segment-v1"
BASELINE_PROFILE = "source-frame0-setup-local-v1"
ROOT_PROFILE = "root-positions-frame0-normalized-reference-v1"
CONTACT_PROFILE = "source-boolean-any-limb-half-open-v1"
TICK_PROFILE = "rational-half-up-microsecond-v1"


class KimodoNpzCompilerError(ValueError):
    """Raised when formal Kimodo evidence cannot form canonical MotionIR."""


@dataclass(frozen=True, slots=True)
class CompiledKimodoMotion:
    """Frozen canonical MotionIR and consistency evidence."""

    _canonical_json: str
    array_inventory_sha256: str
    consistency_metrics: tuple[tuple[str, float | None], ...]

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


def kimodo_npz_compiler_config() -> dict[str, Any]:
    """Return the exact algorithm and tolerance identity for P7 v1."""

    return {
        "reader": READER_PROFILE,
        "skeleton_definition_sha256": SOMA77_DEFINITION_SHA256,
        "skeleton_definition_scope": "joint_names_and_parents",
        "rest_geometry": "source-frame0-unverified-v1",
        "consistency": CONSISTENCY_PROFILE,
        "matrix_orthonormal_tolerance": MATRIX_ORTHONORMAL_TOLERANCE,
        "matrix_crosscheck_tolerance": MATRIX_CROSSCHECK_TOLERANCE,
        "position_crosscheck_meters": POSITION_CROSSCHECK_METERS,
        "heading_norm_tolerance": HEADING_NORM_TOLERANCE,
        "smooth_root_evidence": "bounded-finite-only-v1",
        "global_heading_evidence": "unit-norm-only-v1",
        "projection": PROJECTION_PROFILE,
        "baseline": BASELINE_PROFILE,
        "root": ROOT_PROFILE,
        "contact": CONTACT_PROFILE,
        "tick_schedule": TICK_PROFILE,
        "ticks_per_second": TICKS_PER_SECOND,
        "decimal_places": PRECISION_DECIMALS,
    }


def compile_kimodo_npz_motion(
    raw_npz: bytes,
    source: Mapping[str, Any],
    mapping: Mapping[str, Any],
) -> CompiledKimodoMotion:
    """Compile exact raw bytes, source sidecar, and projection map."""

    try:
        source_snapshot = _json_snapshot(source)
        map_snapshot = _json_snapshot(mapping)
        require_kimodo_npz_source(source_snapshot, raw_npz=raw_npz)
        require_kimodo_npz_map(map_snapshot, source=source_snapshot)
        snapshot = decode_kimodo_npz(raw_npz, source_snapshot)
        validated = validate_kimodo_consistency(snapshot, source_snapshot)
        projected = project_kimodo_frames(validated, source_snapshot, map_snapshot)
        tracks = _tracks(projected)
        markers = kimodo_contact_markers(snapshot, projected, map_snapshot)
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "clip_id": projected.clip_id,
            "ticks_per_second": TICKS_PER_SECOND,
            "duration_ticks": projected.duration_ticks,
            "loop": projected.loop,
            "coordinate_system": motion_coordinate_system(),
            "tracks": tracks,
            "markers": markers,
        }
        require_motion_ir(document)
        result = CompiledKimodoMotion(
            _canonical(document).decode("utf-8"),
            array_inventory_sha256=validated.array_inventory_sha256,
            consistency_metrics=(
                ("max_global_matrix_error", validated.max_global_matrix_error),
                ("max_heading_norm_error", validated.max_heading_norm_error),
                ("max_position_error_meters", validated.max_position_error_meters),
                ("max_root_position_error_meters",
                 validated.max_root_position_error_meters),
            ),
        )
        if result.sha256 != motion_ir_sha256(result.document):
            raise KimodoNpzCompilerError("Kimodo MotionIR identity is inconsistent")
        return result
    except KimodoNpzCompilerError:
        raise
    except (
        KimodoNpzConsistencyError,
        KimodoNpzContactError,
        KimodoNpzMapError,
        KimodoNpzProjectionError,
        KimodoNpzReaderError,
        KimodoNpzSourceError,
        MotionValidationError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise KimodoNpzCompilerError(f"Kimodo NPZ compilation failed: {exc}") from exc


def _tracks(projected) -> list[dict[str, Any]]:
    roles = tuple(segment.role for segment in projected.frames[0].segments)
    tracks = []
    for role_index, role in enumerate(roles):
        tracks.append({
            "target_kind": "bone_role",
            "target": role,
            "property": "rotation",
            "interpolation": "linear",
            "keys": [
                {
                    "tick": frame.tick,
                    "value": frame.segments[role_index].setup_local_additive_delta_deg,
                }
                for frame in projected.frames
            ],
        })
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
    tracks.sort(key=lambda track: (
        track["target_kind"], track["target"], track["property"]
    ))
    return tracks


def _json_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_canonical(value))


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
