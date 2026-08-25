"""Resource-bounded standalone shape contract for P5 mesh regressions."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import re
from typing import Any

from .mesh_action_probe import MAX_AREA_RATIO, MAX_EDGE_STRETCH, MIN_AREA_RATIO
from .motion_instance_sampling import SAMPLE_STEP_TICKS


FORMAT, FORMAT_VERSION = "autospine-motion-mesh-regression", 1
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_ATTACHMENTS, MAX_SAMPLE_COUNT = 1024, 50_000
MAX_TRIANGLE_COUNT, MAX_TICK = 65_536, 600_000_000
MAX_ABS_RATIO, MAX_CRACK_GAP_PX = 1_000_000_000_000.0, 10_000_000.0
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TOP = {
    "format", "format_version", "clip_id", "source", "prober",
    "status", "summary", "sample_count", "attachments",
}
_SOURCE = {
    "instance_sha256", "target_profile_sha256",
    "p3_rig_sha256", "p3_bundle_sha256",
}
_ATTACHMENT = {
    "attachment_id", "source_layer_id", "side", "proximal_bone_id",
    "distal_bone_id", "status", "failed_tick_count",
    "first_failure_tick", "worst",
}
_WORST = {
    "max_flipped_count", "max_degenerate_count", "min_signed_area_ratio",
    "max_signed_area_ratio", "max_edge_stretch_ratio",
    "max_interior_crack_gap_px",
}
_PROBER = {
    "id": "motion-mesh-regression",
    "version": "1.0.0",
    "config": {
        "sample_step_ticks": SAMPLE_STEP_TICKS,
        "min_area_ratio": MIN_AREA_RATIO,
        "max_area_ratio": MAX_AREA_RATIO,
        "max_edge_stretch": MAX_EDGE_STRETCH,
        "root_translation_deformation_invariant": True,
    },
}


class MotionMeshRegressionShapeError(ValueError):
    """Raised when mesh regression JSON is malformed or resource-unsafe."""


def require_motion_mesh_regression_shape(document: Mapping[str, Any]) -> None:
    """Validate complete diagnostic shape without rebuilding its exact inputs."""

    root = _object(document, "report")
    _strict_json_tree(root)
    _exact(root, _TOP, "report")
    if root.get("format") != FORMAT or type(root.get("format_version")) is not int \
            or root.get("format_version") != FORMAT_VERSION:
        raise MotionMeshRegressionShapeError("Mesh regression format is unsupported")
    _safe_id(root.get("clip_id"), "clip id")
    _source(root.get("source"))
    if root.get("prober") != _PROBER:
        raise MotionMeshRegressionShapeError("Mesh regression prober drifted")
    samples = _count(root.get("sample_count"), 1, MAX_SAMPLE_COUNT, "sample count")
    attachments = root.get("attachments")
    if not isinstance(attachments, list) or len(attachments) > MAX_ATTACHMENTS:
        raise MotionMeshRegressionShapeError("Mesh attachment inventory is invalid")
    identifiers, source_ids, rejected = [], set(), False
    for index, raw in enumerate(attachments):
        identifier, source_id, failed = _attachment(raw, samples, index)
        identifiers.append(identifier)
        if source_id in source_ids:
            raise MotionMeshRegressionShapeError("Mesh source layers are duplicated")
        source_ids.add(source_id)
        rejected |= failed
    if identifiers != sorted(identifiers) or len(identifiers) != len(set(identifiers)):
        raise MotionMeshRegressionShapeError("Mesh attachments must be sorted and unique")
    expected_status = "rejected" if rejected else "passed"
    expected_summary = f"attachments={len(attachments)}" if attachments else "reviewed-noop"
    if root.get("status") != expected_status or root.get("summary") != expected_summary:
        raise MotionMeshRegressionShapeError("Mesh regression aggregate differs")
    if len(_canonical(root)) > MAX_REPORT_BYTES:
        raise MotionMeshRegressionShapeError("Mesh regression byte limit exceeded")


def _source(value: Any) -> None:
    source = _object(value, "source")
    _exact(source, _SOURCE, "source")
    if any(not isinstance(source.get(field), str)
           or not _SHA256.fullmatch(source[field]) for field in _SOURCE):
        raise MotionMeshRegressionShapeError("Mesh regression source SHA is invalid")


def _attachment(value: Any, samples: int, index: int) -> tuple[str, str, bool]:
    row = _object(value, f"attachment {index}")
    _exact(row, _ATTACHMENT, f"attachment {index}")
    identifier = _safe_id(row.get("attachment_id"), "attachment id")
    source_id = _safe_id(row.get("source_layer_id"), "source layer id")
    side = row.get("side")
    if side not in {"left", "right"} or \
            row.get("proximal_bone_id") != f"thigh.{side}" or \
            row.get("distal_bone_id") != f"calf.{side}":
        raise MotionMeshRegressionShapeError("Mesh attachment chain is invalid")
    failed = _count(row.get("failed_tick_count"), 0, samples, "failure count")
    first = row.get("first_failure_tick")
    status = row.get("status")
    if failed == 0:
        if status != "passed" or first is not None:
            raise MotionMeshRegressionShapeError("Passed mesh attachment is inconsistent")
    elif status != "rejected" or type(first) is not int or not 0 <= first <= MAX_TICK:
        raise MotionMeshRegressionShapeError("Rejected mesh attachment is inconsistent")
    metrics_rejected = _worst(row.get("worst"))
    if metrics_rejected != (failed > 0):
        raise MotionMeshRegressionShapeError(
            "Mesh attachment status differs from its worst metrics"
        )
    return identifier, source_id, failed > 0


def _worst(value: Any) -> bool:
    worst = _object(value, "worst metrics")
    _exact(worst, _WORST, "worst metrics")
    flipped = _count(
        worst.get("max_flipped_count"), 0, MAX_TRIANGLE_COUNT, "flipped count"
    )
    degenerate = _count(
        worst.get("max_degenerate_count"), 0, MAX_TRIANGLE_COUNT,
        "degenerate count",
    )
    minimum = _bounded(
        worst.get("min_signed_area_ratio"), -MAX_ABS_RATIO, MAX_ABS_RATIO,
        "minimum area ratio",
    )
    maximum = _bounded(
        worst.get("max_signed_area_ratio"), -MAX_ABS_RATIO, MAX_ABS_RATIO,
        "maximum area ratio",
    )
    stretch = _bounded(
        worst.get("max_edge_stretch_ratio"), 0.0, MAX_ABS_RATIO,
        "edge stretch",
    )
    crack = _bounded(
        worst.get("max_interior_crack_gap_px"), 0.0, MAX_CRACK_GAP_PX,
        "crack gap",
    )
    if minimum > maximum:
        raise MotionMeshRegressionShapeError(
            "Mesh regression area ratio range is inverted"
        )
    return bool(
        flipped or degenerate or minimum <= MIN_AREA_RATIO
        or maximum >= MAX_AREA_RATIO or stretch >= MAX_EDGE_STRETCH
        or crack > 0.0
    )


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MotionMeshRegressionShapeError(f"Mesh regression {label} must be an object")
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise MotionMeshRegressionShapeError(
            f"Mesh regression {label} fields are unsupported"
        )


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise MotionMeshRegressionShapeError(f"Mesh regression {label} is invalid")
    return value


def _count(value: Any, minimum: int, maximum: int, label: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise MotionMeshRegressionShapeError(f"Mesh regression {label} is invalid")
    return value


def _bounded(value: Any, minimum: float, maximum: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or not minimum <= float(value) <= maximum:
        raise MotionMeshRegressionShapeError(f"Mesh regression {label} is invalid")
    return float(value)


def _strict_json_tree(value: Any) -> None:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise MotionMeshRegressionShapeError("Mesh regression keys must be strings")
        for item in value.values():
            _strict_json_tree(item)
    elif isinstance(value, list):
        for item in value:
            _strict_json_tree(item)
    elif isinstance(value, tuple):
        raise MotionMeshRegressionShapeError("Mesh regression arrays must be lists")
    elif isinstance(value, float) and not math.isfinite(value):
        raise MotionMeshRegressionShapeError("Mesh regression numbers must be finite")


def _canonical(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(value), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (OverflowError, TypeError, ValueError) as exc:
        raise MotionMeshRegressionShapeError(
            "Mesh regression is not finite canonical JSON"
        ) from exc
