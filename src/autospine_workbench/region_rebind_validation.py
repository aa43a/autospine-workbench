"""Strict validation and exact-input binding for region rebind candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
import re
from typing import Any

from .body_sway_probe_math import BodySwayPoseSample
from .region_rebind_inputs import (
    RegionRebindInputError,
    require_digest,
    safe_identifier,
)
from .region_rebind_profile import (
    FORMAT,
    FORMAT_VERSION,
    MAX_CANDIDATE_BONES,
    MAX_MOTION_SAMPLES,
    SETUP_RECONSTRUCTION_TOLERANCE_PX,
    region_rebind_analyzer_profile,
    region_rebind_analyzer_profile_sha256,
    region_rebind_semantics,
)
from .resolved_project import canonical_sha256


MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
_TOP = {
    "format", "format_version", "project_id", "source", "analyzer",
    "semantics", "candidates", "recommendation", "status",
}
_SOURCE = {
    "rig_sha256", "motion_sha256", "motion_samples_sha256",
    "motion_sample_count", "attachment_id", "slot_id", "current_bone_id",
    "candidate_bone_ids_sha256", "analyzer_profile_sha256",
}
_CANDIDATE = {
    "candidate_id", "bone_id", "relationship", "hop_distance", "metrics",
    "evidence_sha256",
}
_METRICS = {
    "sample_count", "fk_status", "setup_reconstruction_max_error_px",
    "root_compensated_centroid_motion_rms_px",
    "root_compensated_max_vertex_motion_px",
    "normalized_centroid_motion_rms", "normalized_max_vertex_motion",
    "setup_subtree_segment_coverage_count",
    "setup_subtree_segment_ids_fully_inside_region",
    "setup_pivot_distance_to_bone_origin_px",
    "setup_pivot_distance_to_bone_endpoint_px",
    "viewport_overflow_sample_count", "viewport_overflow_vertex_count",
    "max_viewport_overflow_px", "sampled_envelope_xyxy",
}
_RECOMMENDATION = {
    "status", "candidate_id", "from_bone_id", "to_bone_id",
    "relative_motion_improvement", "reason_codes", "authority",
    "requires_explicit_review",
}


class RegionRebindValidationError(ValueError):
    """Raised when a candidate document is malformed, stale, or overclaims."""


def require_region_rebind_candidates(document: Mapping[str, Any]) -> None:
    """Validate the standalone zero-authority candidate contract."""

    try:
        root = _object(document, _TOP, "document")
        if root.get("format") != FORMAT \
                or root.get("format_version") != FORMAT_VERSION:
            raise RegionRebindValidationError("candidate format is unsupported")
        safe_identifier(root.get("project_id"), "project_id")
        source = _source(root.get("source"))
        if root.get("analyzer") != region_rebind_analyzer_profile() \
                or source["analyzer_profile_sha256"] \
                != region_rebind_analyzer_profile_sha256():
            raise RegionRebindValidationError("analyzer profile differs")
        if root.get("semantics") != region_rebind_semantics():
            raise RegionRebindValidationError("candidate semantics differ")
        rows = _candidates(root.get("candidates"), source)
        from .region_rebind_candidates import _recommend
        if root.get("recommendation") != _recommend(
            source["current_bone_id"], tuple(rows),
        ):
            raise RegionRebindValidationError("recommendation is inconsistent")
        _recommendation(root.get("recommendation"), rows, source)
        if root.get("status") != "candidate_only":
            raise RegionRebindValidationError("candidate status overclaims")
        if len(_canonical(root)) > MAX_DOCUMENT_BYTES:
            raise RegionRebindValidationError("candidate document is too large")
    except RegionRebindValidationError:
        raise
    except (
        KeyError, OverflowError, RegionRebindInputError, TypeError, ValueError,
    ) as exc:
        raise RegionRebindValidationError(
            f"Region rebind candidate validation failed: {exc}"
        ) from exc


def require_region_rebind_candidate_binding(
    document: Mapping[str, Any],
    rig: Mapping[str, Any],
    motion_samples: Sequence[BodySwayPoseSample],
    *,
    project_id: str,
    motion_sha256: str,
    attachment_id: str,
    candidate_bone_ids: Sequence[str] | None = None,
) -> None:
    """Recompile from exact inputs and require byte-equivalent evidence."""

    require_region_rebind_candidates(document)
    from .region_rebind_candidates import compile_region_rebind_candidates
    expected = compile_region_rebind_candidates(
        rig, motion_samples, project_id=project_id,
        motion_sha256=motion_sha256, attachment_id=attachment_id,
        candidate_bone_ids=candidate_bone_ids,
    ).document
    if _canonical(document) != _canonical(expected):
        raise RegionRebindValidationError(
            "Region rebind candidate differs from exact inputs"
        )


def region_rebind_candidates_sha256(document: Mapping[str, Any]) -> str:
    require_region_rebind_candidates(document)
    return canonical_sha256(document)


def _source(value):
    source = _object(value, _SOURCE, "source")
    for field in (
        "rig_sha256", "motion_sha256", "motion_samples_sha256",
        "candidate_bone_ids_sha256", "analyzer_profile_sha256",
    ):
        require_digest(source.get(field), field)
    for field in ("attachment_id", "slot_id", "current_bone_id"):
        safe_identifier(source.get(field), field)
    count = source.get("motion_sample_count")
    if type(count) is not int or not 2 <= count <= MAX_MOTION_SAMPLES:
        raise RegionRebindValidationError("motion sample count is invalid")
    return source


def _candidates(value, source):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_CANDIDATE_BONES:
        raise RegionRebindValidationError("candidate inventory is invalid")
    rows, bone_ids, candidate_ids = [], [], set()
    for raw in value:
        row = _object(raw, _CANDIDATE, "candidate")
        bone_id = safe_identifier(row.get("bone_id"), "candidate bone")
        candidate_id = row.get("candidate_id")
        if not isinstance(candidate_id, str) \
                or not re.fullmatch(r"region-rebind-[0-9a-f]{64}", candidate_id) \
                or candidate_id in candidate_ids:
            raise RegionRebindValidationError("candidate id is invalid")
        relationship = row.get("relationship")
        hop = row.get("hop_distance")
        if relationship not in {"current", "parent", "child"} \
                or hop != (0 if relationship == "current" else 1):
            raise RegionRebindValidationError("candidate relationship is invalid")
        metrics = _metrics(row.get("metrics"), source["motion_sample_count"])
        require_digest(row.get("evidence_sha256"), "candidate evidence")
        expected_id = "region-rebind-" + canonical_sha256({
            "source": source, "bone_id": bone_id, "metrics": metrics,
        })
        if candidate_id != expected_id:
            raise RegionRebindValidationError("candidate identity differs")
        rows.append(row)
        bone_ids.append(bone_id)
        candidate_ids.add(candidate_id)
    if bone_ids != sorted(bone_ids) or len(set(bone_ids)) != len(bone_ids) \
            or source["current_bone_id"] not in bone_ids \
            or sum(row["relationship"] == "current" for row in rows) != 1 \
            or canonical_sha256({"bone_ids": bone_ids}) \
            != source["candidate_bone_ids_sha256"]:
        raise RegionRebindValidationError("candidate inventory binding differs")
    return rows


def _metrics(value, sample_count):
    metrics = _object(value, _METRICS, "candidate metrics")
    if metrics.get("sample_count") != sample_count \
            or metrics.get("fk_status") != "passed":
        raise RegionRebindValidationError("candidate sample/FK status is invalid")
    numeric = _METRICS - {
        "sample_count", "fk_status", "viewport_overflow_sample_count",
        "viewport_overflow_vertex_count", "sampled_envelope_xyxy",
        "setup_subtree_segment_coverage_count",
        "setup_subtree_segment_ids_fully_inside_region",
    }
    if any(not _nonnegative(metrics.get(field)) for field in numeric):
        raise RegionRebindValidationError("candidate metric is invalid")
    if metrics["setup_reconstruction_max_error_px"] \
            > SETUP_RECONSTRUCTION_TOLERANCE_PX:
        raise RegionRebindValidationError("setup reconstruction is rejected")
    for field in (
        "viewport_overflow_sample_count", "viewport_overflow_vertex_count",
        "setup_subtree_segment_coverage_count",
    ):
        if type(metrics.get(field)) is not int or metrics[field] < 0:
            raise RegionRebindValidationError("candidate count is invalid")
    if metrics["viewport_overflow_sample_count"] > sample_count \
            or metrics["viewport_overflow_vertex_count"] > sample_count * 4:
        raise RegionRebindValidationError("viewport failure count is invalid")
    ids = metrics.get("setup_subtree_segment_ids_fully_inside_region")
    if not isinstance(ids, list) or ids != sorted(ids) \
            or len(ids) != metrics["setup_subtree_segment_coverage_count"] \
            or len(set(ids)) != len(ids) \
            or any(not isinstance(item, str) for item in ids):
        raise RegionRebindValidationError("setup segment coverage is invalid")
    envelope = metrics.get("sampled_envelope_xyxy")
    if not isinstance(envelope, list) or len(envelope) != 4 \
            or not all(_finite(item) for item in envelope) \
            or envelope[0] > envelope[2] or envelope[1] > envelope[3]:
        raise RegionRebindValidationError("sampled envelope is invalid")
    return metrics


def _recommendation(value, rows, source):
    row = _object(value, _RECOMMENDATION, "recommendation")
    if row.get("status") not in {"recommended", "keep_current", "ambiguous"} \
            or row.get("authority") != "none" \
            or row.get("requires_explicit_review") is not True \
            or row.get("from_bone_id") != source["current_bone_id"]:
        raise RegionRebindValidationError("recommendation overclaims")
    selected = {item["candidate_id"]: item for item in rows}.get(row.get("candidate_id"))
    if selected is None or row.get("to_bone_id") != selected["bone_id"] \
            or not _nonnegative(row.get("relative_motion_improvement")):
        raise RegionRebindValidationError("recommendation target is invalid")
    reasons = row.get("reason_codes")
    if not isinstance(reasons, list) or not reasons \
            or len(reasons) > 8 or len(set(reasons)) != len(reasons) \
            or any(not isinstance(item, str) for item in reasons):
        raise RegionRebindValidationError("recommendation reasons are invalid")


def _object(value, fields, label):
    if not isinstance(value, Mapping) or set(value) != fields:
        raise RegionRebindValidationError(f"{label} fields are invalid")
    return value


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value)


def _nonnegative(value):
    return _finite(value) and value >= 0.0


def _canonical(value):
    return json.dumps(
        dict(value) if isinstance(value, Mapping) else value,
        ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
