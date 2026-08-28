"""Deterministic camera-aware evidence compiler for verified Kimodo motion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any

from .camera_model_validation import (
    CameraModelError,
    camera_model_sha256,
    require_camera_matches_kimodo_map,
)
from .kimodo_npz_consistency import (
    KimodoNpzConsistencyError,
    validate_kimodo_consistency,
)
from .kimodo_npz_map_validation import kimodo_npz_map_sha256
from .kimodo_npz_projection import kimodo_frame_ticks
from .kimodo_npz_reader import KimodoNpzReaderError, decode_kimodo_npz
from .kimodo_npz_source import kimodo_npz_source_sha256
from .kimodo_soma77 import SOMA77_INDEX_BY_NAME
from .motion_bundle_integrity import VerifiedMotionBundle
from .motion_roles import nearest_mapped_parent_role
from .motion_validation import motion_ir_sha256, require_motion_ir
from .projected_motion_validation import (
    FORMAT,
    FORMAT_VERSION,
    ProjectedMotionValidationError,
    projected_motion_ir_sha256,
    require_projected_motion_ir,
)


COMPILER_ID = "kimodo-projected-motion-compiler"
COMPILER_VERSION = "1.0.1"
EVIDENCE_DECIMALS = 9
LEGACY_DECIMALS = 5
MIN_SOURCE_LENGTH_NORMALIZED = 1e-9
MIN_PROJECTED_SEGMENT_RATIO = 1e-6
MIN_PROJECTED_REFERENCE_RATIO = 1e-9


class KimodoCameraProjectionError(ValueError):
    """Raised when verified Kimodo geometry cannot form camera evidence."""


@dataclass(frozen=True, slots=True)
class CompiledProjectedMotion:
    """Frozen canonical ProjectedMotionIR and reproducibility metrics."""

    _canonical_json: str
    consistency_metrics: tuple[tuple[str, float | None], ...]
    projection_metrics: tuple[tuple[str, float | int], ...]

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def projected_motion_compiler_config() -> dict[str, Any]:
    """Return the complete algorithm identity for ProjectedMotionIR v1."""

    return {
        "projection": "static-orthographic-signed-basis-v1",
        "geometry_source": "verified-soma77-matrix-fk-positions-v1",
        "normalization": "kimodo-map-reference-length-v1",
        "root_baseline": "source-root-frame0-v1",
        "angle_unwrap": "shortest-signed-delta-v1",
        "collapse_state": "normalized-l2-threshold-v1",
        "minimum_source_length_normalized": MIN_SOURCE_LENGTH_NORMALIZED,
        "minimum_projected_segment_ratio": MIN_PROJECTED_SEGMENT_RATIO,
        "minimum_projected_reference_ratio": MIN_PROJECTED_REFERENCE_RATIO,
        "evidence_decimal_places": EVIDENCE_DECIMALS,
        "legacy_decimal_places": LEGACY_DECIMALS,
        "depth_use": "evidence-only-no-ordering-v1",
    }


def compile_verified_kimodo_projection(
    bundle: VerifiedMotionBundle,
    camera: Mapping[str, Any],
) -> CompiledProjectedMotion:
    """Rebuild matrix-FK positions from one exact P7 bundle and project them."""

    try:
        if type(bundle) is not VerifiedMotionBundle \
                or bundle.source_kind != "kimodo_npz":
            raise KimodoCameraProjectionError(
                "Projected motion requires a verified Kimodo NPZ bundle"
            )
        raw, source, mapping = (
            bundle.raw_npz, bundle.kimodo_source, bundle.kimodo_map
        )
        if raw is None or source is None or mapping is None:
            raise KimodoCameraProjectionError(
                "Verified Kimodo bundle inputs are incomplete"
            )
        require_camera_matches_kimodo_map(camera, mapping)
        source_hash = kimodo_npz_source_sha256(source)
        map_hash = kimodo_npz_map_sha256(mapping)
        snapshot = decode_kimodo_npz(raw, source)
        validated = validate_kimodo_consistency(snapshot, source)
        motion = bundle.motion
        require_motion_ir(motion)
        run = bundle.run_manifest
        run_source = run.get("source")
        if not isinstance(run_source, Mapping):
            raise KimodoCameraProjectionError(
                "Verified Kimodo run source is unavailable"
            )
        _require_upstream_identity(
            bundle, motion, run_source, validated, source_hash, map_hash
        )
        document, metrics = _project_document(
            validated.positions,
            source,
            mapping,
            camera,
            motion["markers"],
            {
                "kind": "kimodo_npz",
                "motion_ir_sha256": bundle.clip_sha256,
                "motion_bundle_sha256": bundle.bundle_sha256,
                "motion_run_sha256": bundle.run_sha256,
                "raw_npz_sha256": validated.raw_npz_sha256,
                "source_sha256": source_hash,
                "map_sha256": map_hash,
                "array_inventory_sha256": validated.array_inventory_sha256,
            },
        )
        require_projected_motion_ir(document)
        result = CompiledProjectedMotion(
            _canonical(document).decode("utf-8"),
            consistency_metrics=(
                ("max_global_matrix_error", validated.max_global_matrix_error),
                ("max_heading_norm_error", validated.max_heading_norm_error),
                ("max_position_error_meters", validated.max_position_error_meters),
                ("max_root_position_error_meters",
                 validated.max_root_position_error_meters),
            ),
            projection_metrics=tuple(metrics.items()),
        )
        if result.sha256 != projected_motion_ir_sha256(result.document):
            raise KimodoCameraProjectionError(
                "Projected motion canonical identity is inconsistent"
            )
        return result
    except KimodoCameraProjectionError:
        raise
    except (
        CameraModelError,
        KimodoNpzConsistencyError,
        KimodoNpzReaderError,
        ProjectedMotionValidationError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise KimodoCameraProjectionError(
            f"Kimodo camera projection failed: {exc}"
        ) from exc


def _require_upstream_identity(
    bundle, motion, run_source, validated, source_hash, map_hash
) -> None:
    expected = {
        "raw_npz_sha256": validated.raw_npz_sha256,
        "source_sha256": source_hash,
        "map_sha256": map_hash,
        "array_inventory_sha256": validated.array_inventory_sha256,
    }
    if motion_ir_sha256(motion) != bundle.clip_sha256 \
            or motion["clip_id"] != bundle.clip_id \
            or any(run_source.get(field) != value for field, value in expected.items()):
        raise KimodoCameraProjectionError(
            "Verified Kimodo identities differ from rebuilt geometry"
        )


def _project_document(positions, source, mapping, camera, markers, binding):
    ticks = kimodo_frame_ticks(source)
    basis = camera["basis"]
    reference = float(camera["reference_length_meters"])
    root_points = [_project(frame[0], basis) for frame in positions]
    roots = _root_samples(root_points, ticks, reference)
    tracks, ratios, collapsed = [], [], 0
    by_role = {row["role"]: row for row in mapping["bones"]}
    for row in mapping["bones"]:
        samples, track_ratios = _segment_samples(
            positions, root_points, ticks, row, basis, reference
        )
        ratios.extend(track_ratios)
        collapsed += sum(
            sample["projection_state"] == "collapsed" for sample in samples
        )
        tracks.append({
            "role": row["role"],
            "source_joint_name": row["joint_name"],
            "aim_joint_name": row["aim_joint_name"],
            "delta_parent_role": nearest_mapped_parent_role(row["role"], by_role),
            "setup_source_length_normalized":
                samples[0]["source_length_normalized"],
            "setup_projected_length_normalized":
                samples[0]["projected_length_normalized"],
            "samples": samples,
        })
    document = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "clip_id": mapping["clip"]["clip_id"],
        "timing": {
            "ticks_per_second": 1_000_000,
            "duration_ticks": ticks[-1],
            "loop": mapping["clip"]["loop"],
            "frame_count": len(ticks),
        },
        "source": dict(binding),
        "camera_sha256": camera_model_sha256(camera),
        "frames": [
            {"source_frame_index": index, "tick": tick}
            for index, tick in enumerate(ticks)
        ],
        "root_samples": roots,
        "segment_tracks": tracks,
        "markers": json.loads(json.dumps(markers)),
    }
    metrics = {
        "collapsed_sample_count": collapsed,
        "minimum_foreshortening_ratio": _q(min(ratios), EVIDENCE_DECIMALS),
        "maximum_foreshortening_ratio": _q(max(ratios), EVIDENCE_DECIMALS),
    }
    return document, metrics


def _root_samples(points, ticks, reference):
    origin = points[0]
    return [
        {
            "source_frame_index": index,
            "tick": tick,
            "screen_translation_normalized": [
                _q((point[0] - origin[0]) / reference, LEGACY_DECIMALS),
                _q((point[1] - origin[1]) / reference, LEGACY_DECIMALS),
            ],
            "depth_translation_normalized":
                _q((point[2] - origin[2]) / reference, EVIDENCE_DECIMALS),
        }
        for index, (tick, point) in enumerate(zip(ticks, points))
    ]


def _segment_samples(positions, roots, ticks, row, basis, reference):
    start_index = SOMA77_INDEX_BY_NAME[row["joint_name"]]
    end_index = SOMA77_INDEX_BY_NAME[row["aim_joint_name"]]
    geometry, raw_angles = [], []
    for frame, root in zip(positions, roots):
        start, end = _project(frame[start_index], basis), _project(
            frame[end_index], basis
        )
        dx, dy, dz = (end[index] - start[index] for index in range(3))
        source_length = math.sqrt(dx * dx + dy * dy + dz * dz)
        source_normalized = source_length / reference
        if not math.isfinite(source_normalized) \
                or source_normalized <= MIN_SOURCE_LENGTH_NORMALIZED:
            raise KimodoCameraProjectionError(
                f"Kimodo segment source length is degenerate: {row['role']}"
            )
        projected = math.hypot(dx, dy)
        raw_angles.append(math.degrees(math.atan2(dy, dx)))
        geometry.append((start, end, root, dx, dy, dz, source_length, projected))
    angles = _unwrap(raw_angles)
    samples, ratios = [], []
    for index, (tick, values, angle) in enumerate(zip(ticks, geometry, angles)):
        start, end, root, dx, dy, dz, source_length, projected = values
        source_n = _q(source_length / reference, EVIDENCE_DECIMALS)
        projected_n = _q(projected / reference, EVIDENCE_DECIMALS)
        ratio = _q(projected / source_length, EVIDENCE_DECIMALS)
        cosine = _q(dz / source_length, EVIDENCE_DECIMALS)
        start_depth = _q((start[2] - root[2]) / reference, EVIDENCE_DECIMALS)
        end_depth = _q((end[2] - root[2]) / reference, EVIDENCE_DECIMALS)
        minimum = max(
            source_n * MIN_PROJECTED_SEGMENT_RATIO,
            MIN_PROJECTED_REFERENCE_RATIO,
        )
        state = "observable" if projected_n > minimum else "collapsed"
        samples.append({
            "source_frame_index": index,
            "tick": tick,
            "projected_vector_normalized": [
                _q(dx / reference, EVIDENCE_DECIMALS),
                _q(dy / reference, EVIDENCE_DECIMALS),
            ],
            "source_length_normalized": source_n,
            "projected_length_normalized": projected_n,
            "foreshortening_ratio": ratio,
            "depth_cosine": cosine,
            "projected_world_angle_deg": _q(angle, EVIDENCE_DECIMALS),
            "start_depth_root_relative_normalized": start_depth,
            "end_depth_root_relative_normalized": end_depth,
            "midpoint_depth_root_relative_normalized":
                _q((start_depth + end_depth) / 2.0, EVIDENCE_DECIMALS),
            "projection_state": state,
        })
        ratios.append(ratio)
    return samples, ratios


def _project(xyz, basis) -> tuple[float, float, float]:
    axes = {"X": 0, "Y": 1, "Z": 2}
    return tuple(
        (-1.0 if basis[field][0] == "-" else 1.0)
        * float(xyz[axes[basis[field][1]]])
        for field in ("screen_x", "screen_y", "depth")
    )


def _unwrap(values):
    result = [values[0]]
    for value in values[1:]:
        delta = (value - result[-1] + 180.0) % 360.0 - 180.0
        result.append(result[-1] + delta)
    return result


def _q(value: float, places: int) -> float:
    if not math.isfinite(value):
        raise KimodoCameraProjectionError(
            "Kimodo camera projection produced non-finite evidence"
        )
    result = round(float(value), places)
    return 0.0 if result == 0 else result


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
