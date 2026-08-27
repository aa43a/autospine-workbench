"""Exact capture/plan/metric inventory binding for P10.7b review."""
from __future__ import annotations

from .spine42_v3_raster_metrics import (
    METRICS_FORMAT,
    spine42_v3_raster_metrics_sha256,
)
from .spine42_v3_raster_review_values import (
    Spine42V3RasterReviewError,
    object_value,
    rows_value,
    sha_value,
)
from .spine42_v3_runtime_evidence import (
    AUTHORITY as CAPTURE_AUTHORITY,
    FORMAT as CAPTURE_FORMAT,
    FORMAT_VERSION as CAPTURE_FORMAT_VERSION,
    RELEASE_GATE as CAPTURE_RELEASE_GATE,
)
from .spine42_v3_runtime_plan import spine42_v3_runtime_plan_sha256


def verified_spine42_v3_review_inventory(root, report):
    """Bind every planned row to its stored and measured counterpart."""

    plan = object_value(root.get("plan"), "capture plan")
    plan_sha = spine42_v3_runtime_plan_sha256(plan)
    metrics_sha = spine42_v3_raster_metrics_sha256(report)
    source = object_value(root.get("source"), "capture source")
    source_fields = {
        "skeleton_json_sha256", "spine42_v3_bundle_sha256",
        "run_document_sha256", "capture_plan_sha256",
        "runtime_session_set_sha256", "raster_metrics_sha256",
    }
    if set(source) != source_fields:
        raise Spine42V3RasterReviewError("Capture source fields are invalid")
    for key, value in source.items():
        sha_value(value, key)
    expected_source = {
        "project_id": root["project_id"], "clip_id": root["clip_id"],
        "skeleton_json_sha256": source["skeleton_json_sha256"],
        "bundle_sha256": source["spine42_v3_bundle_sha256"],
    }
    sampled = object_value(plan.get("sampled_scope"), "sampled scope")
    metric_semantics = {
        "scope": "bounded-discrete-samples-only",
        "continuous_time_safety_claimed": False,
        "unsampled_ticks_covered": False,
        "human_visual_approval_claimed": False,
    }
    invalid = root.get("format") != CAPTURE_FORMAT \
        or root.get("format_version") != CAPTURE_FORMAT_VERSION \
        or root.get("authority") != CAPTURE_AUTHORITY \
        or root.get("release_gate") != CAPTURE_RELEASE_GATE \
        or plan.get("source") != expected_source \
        or plan_sha != source["capture_plan_sha256"] \
        or sampled.get("kind") != "bounded-discrete-samples-only" \
        or sampled.get("continuous_time_safety_claimed") is not False \
        or sampled.get("unsampled_ticks_covered") is not False \
        or report.get("format") != METRICS_FORMAT \
        or report.get("capture_plan_sha256") != plan_sha \
        or report.get("profile_sha256") != plan.get("profile_sha256") \
        or report.get("source") != expected_source \
        or report.get("sampled_scope") != sampled \
        or report.get("semantics") != metric_semantics \
        or metrics_sha != source["raster_metrics_sha256"]
    if invalid:
        raise Spine42V3RasterReviewError(
            "Capture, plan, and metrics identities are inconsistent"
        )
    planned = _unique(plan.get("artifacts"), "planned artifacts", "artifact_id")
    stored = _unique(root.get("artifacts"), "stored artifacts", "artifact_id")
    measured = _unique(
        report.get("artifact_sha256s"), "metric artifacts", "artifact_id"
    )
    if set(planned) != set(stored) or set(planned) != set(measured):
        raise Spine42V3RasterReviewError("Artifact inventories differ")
    merged = _bind_artifacts(planned, stored, measured)
    cases = _unique(plan.get("cases"), "capture cases", "case_id")
    metric_cases = _unique(report.get("cases"), "metric cases", "case_id")
    attachments = rows_value(plan.get("attachments"), "attachments")
    pairs = [(row.get("slot_id"), row.get("attachment_id")) for row in attachments]
    if set(cases) != set(metric_cases) or len(set(pairs)) != len(pairs) \
            or any(row.get("ordinal") != index for index, row in enumerate(
                attachments
            )):
        raise Spine42V3RasterReviewError("Case or attachment inventory differs")
    bound_ids = [item for case in cases.values() for item in case.get(
        "artifact_ids", [])]
    if len(bound_ids) != len(planned) or set(bound_ids) != set(planned):
        raise Spine42V3RasterReviewError("Case artifacts are not one-to-one")
    for case_id, case in cases.items():
        _bind_case(case, metric_cases[case_id], merged, pairs)
    _require_summary(report, metric_cases, len(planned))
    return plan, merged, metric_cases, metrics_sha


def _bind_artifacts(planned, stored, measured):
    merged = {}
    for identifier, item in planned.items():
        saved, metric = stored[identifier], measured[identifier]
        saved_fields = {
            "artifact_id", "logical_path", "stored_path", "kind", "case_id",
            "sha256", "size_bytes",
        }
        invalid = set(item) != {
            "artifact_id", "path", "kind", "case_id", "slot_id",
            "attachment_id", "background",
        } or item.get("path") != f"{identifier}.png" \
            or set(saved) != saved_fields \
            or set(metric) != {"artifact_id", "png_sha256"} \
            or saved["logical_path"] != item["path"] \
            or saved["stored_path"] != f"captures/{item['path']}" \
            or (saved["kind"], saved["case_id"]) != (
                item["kind"], item["case_id"]) \
            or saved["sha256"] != metric["png_sha256"] \
            or type(saved["size_bytes"]) is not int or saved["size_bytes"] <= 0
        if invalid:
            raise Spine42V3RasterReviewError("Artifact binding is invalid")
        sha_value(saved["sha256"], "stored artifact")
        merged[identifier] = {**item, **saved}
    return merged


def _bind_case(case, metric, artifacts, pairs):
    selected = [artifacts.get(item) for item in case.get("artifact_ids", [])]
    isolates = [row for row in selected if row and row["kind"] ==
                "attachment_isolate"]
    metric_isolates = rows_value(
        metric.get("attachment_isolates"), "metric isolates"
    )
    actual = {(row["slot_id"], row["attachment_id"], row["artifact_id"])
              for row in isolates}
    measured = {(row.get("slot_id"), row.get("attachment_id"),
                 row.get("artifact_id")) for row in metric_isolates}
    kinds = [row["kind"] for row in selected if row]
    invalid = None in selected or len(selected) != 2 + len(pairs) \
        or any(row["case_id"] != case.get("case_id") for row in selected) \
        or kinds.count("opaque_composite") != 1 \
        or kinds.count("transparent_composite") != 1 \
        or len(isolates) != len(pairs) or len(metric_isolates) != len(pairs) \
        or actual != measured \
        or {(row["slot_id"], row["attachment_id"]) for row in isolates} \
        != set(pairs) or metric.get("tick") != case.get("tick") \
        or metric.get("time_seconds") != case.get("time_seconds") \
        or metric.get("passed") is not (not metric.get("reason_codes"))
    if invalid:
        raise Spine42V3RasterReviewError("Case evidence binding is invalid")


def _require_summary(report, metric_cases, artifact_count):
    summary = object_value(report.get("summary"), "metric summary")
    passed = sum(row.get("passed") is True for row in metric_cases.values())
    invalid = summary.get("case_count") != len(metric_cases) \
        or summary.get("artifact_count") != artifact_count \
        or summary.get("passed_case_count") != passed \
        or summary.get("failed_case_count") != len(metric_cases) - passed \
        or summary.get("all_sampled_cases_passed") is not (
            passed == len(metric_cases))
    if invalid:
        raise Spine42V3RasterReviewError("Metric summary is inconsistent")


def _unique(value, label, key):
    rows = rows_value(value, label)
    result = {row.get(key): row for row in rows}
    if None in result or len(result) != len(rows):
        raise Spine42V3RasterReviewError(f"{label} ids are invalid")
    return result


__all__ = ["verified_spine42_v3_review_inventory"]
