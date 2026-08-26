"""Small fail-closed validators for projected-motion compile runs."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
from typing import Any

from . import kimodo_camera_projection as compiler_impl
from .kimodo_npz_consistency import (
    HEADING_NORM_TOLERANCE, MATRIX_CROSSCHECK_TOLERANCE,
    POSITION_CROSSCHECK_METERS,
)


_SHA256 = re.compile(r"[0-9a-f]{64}")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
SOURCE_FIELDS = {"kind", "motion_ir_sha256", "motion_bundle_sha256",
                 "motion_run_sha256", "raw_npz_sha256", "source_sha256",
                 "map_sha256", "array_inventory_sha256"}
VALIDATION_FIELDS = {
    "max_global_matrix_error", "max_heading_norm_error",
    "max_position_error_meters", "max_root_position_error_meters",
    "collapsed_sample_count", "minimum_foreshortening_ratio",
    "maximum_foreshortening_ratio",
}


class ProjectedMotionCompileRunError(ValueError):
    """Raised when projected-motion provenance is incomplete or stale."""


def source_row(value: Any) -> Mapping[str, Any]:
    source = object_row(value, "Projected compile-run source")
    exact_fields(source, SOURCE_FIELDS, "Projected compile-run source")
    if source.get("kind") != "kimodo_npz":
        raise ProjectedMotionCompileRunError(
            "Projected compile-run source kind is unsupported"
        )
    for field in SOURCE_FIELDS - {"kind"}:
        require_sha(source.get(field), field)
    return source


def camera_row(value: Any) -> Mapping[str, Any]:
    camera = object_row(value, "Projected compile-run camera")
    exact_fields(camera, {"camera_sha256", "camera_id", "depth_positive"},
                 "Projected compile-run camera")
    require_sha(camera.get("camera_sha256"), "camera_sha256")
    camera_id = camera.get("camera_id")
    if not isinstance(camera_id, str) or not _SAFE_ID.fullmatch(camera_id):
        raise ProjectedMotionCompileRunError("Projected camera id is invalid")
    if camera.get("depth_positive") not in {
        "toward_camera", "away_from_camera",
    }:
        raise ProjectedMotionCompileRunError(
            "Projected camera depth direction is invalid"
        )
    return camera


def require_compiler(value: Any) -> None:
    compiler = object_row(value, "Projected compile-run compiler")
    exact_fields(compiler, {"id", "version", "config"},
                 "Projected compile-run compiler")
    config = object_row(compiler.get("config"), "Projected compiler config")
    if compiler.get("id") != compiler_impl.COMPILER_ID \
            or compiler.get("version") != compiler_impl.COMPILER_VERSION \
            or canonical(config) != canonical(
                compiler_impl.projected_motion_compiler_config()
            ):
        raise ProjectedMotionCompileRunError(
            "Projected compiler identity drifted"
        )


def validation_row(value: Any) -> Mapping[str, Any]:
    result = object_row(value, "Projected compile-run validation")
    exact_fields(result, VALIDATION_FIELDS, "Projected compile-run validation")
    limits = {
        "max_global_matrix_error": MATRIX_CROSSCHECK_TOLERANCE,
        "max_heading_norm_error": HEADING_NORM_TOLERANCE,
        "max_position_error_meters": POSITION_CROSSCHECK_METERS,
        "max_root_position_error_meters": POSITION_CROSSCHECK_METERS,
    }
    for field, maximum in limits.items():
        bounded(result.get(field), field, maximum,
                allow_none=field == "max_heading_norm_error")
    count = result.get("collapsed_sample_count")
    if type(count) is not int or not 0 <= count <= 17 * 4096:
        raise ProjectedMotionCompileRunError(
            "Projected collapsed sample count is invalid"
        )
    minimum = bounded(result.get("minimum_foreshortening_ratio"),
                      "minimum foreshortening", 1.001)
    maximum = bounded(result.get("maximum_foreshortening_ratio"),
                      "maximum foreshortening", 1.001)
    if minimum > maximum:
        raise ProjectedMotionCompileRunError(
            "Projected foreshortening bounds are reversed"
        )
    return result


def output_row(value: Any) -> Mapping[str, Any]:
    output = object_row(value, "Projected compile-run output")
    exact_fields(output, {
        "projected_motion_ir_sha256", "legacy_motion_ir_sha256",
    }, "Projected compile-run output")
    for field in output:
        require_sha(output.get(field), field)
    return output


def projection_metrics(document: Mapping[str, Any]) -> dict[str, Any]:
    samples = [sample for track in document["segment_tracks"]
               for sample in track["samples"]]
    ratios = [sample["foreshortening_ratio"] for sample in samples]
    return {
        "collapsed_sample_count": sum(
            sample["projection_state"] == "collapsed" for sample in samples
        ),
        "minimum_foreshortening_ratio": min(ratios),
        "maximum_foreshortening_ratio": max(ratios),
    }


def bounded(value: Any, label: str, maximum: float,
            *, allow_none: bool = False) -> float:
    if value is None and allow_none:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or not 0 <= value <= maximum:
        raise ProjectedMotionCompileRunError(
            f"Projected compile-run {label} is outside its bound"
        )
    return float(value)


def require_sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ProjectedMotionCompileRunError(
            f"Projected compile-run {label} is invalid"
        )


def object_row(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProjectedMotionCompileRunError(f"{label} must be an object")
    return value


def exact_fields(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise ProjectedMotionCompileRunError(
            f"{label} fields are incomplete or unsupported"
        )


def canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")
