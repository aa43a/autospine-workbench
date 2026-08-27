"""Pure PNG-byte raster metrics for bounded Spine v3 runtime captures."""
from __future__ import annotations
from collections.abc import Mapping
import hashlib
import json
from typing import Any
from .png_rgba import RgbaImage, RgbaPngError, decode_rgba_png
from .resolved_project import canonical_sha256
from .spine42_v3_runtime_plan import (
    Spine42V3RuntimePlanError,
    spine42_v3_runtime_plan_sha256,
)
from .spine42_v3_runtime_profile import (
    ALPHA_THRESHOLD,
    MAX_CAPTURE_ARTIFACTS,
    METRICS_HASH_DOMAIN,
    spine42_v3_runtime_profile_sha256,
)
METRICS_FORMAT = "autospine-spine42-v3-runtime-raster-metrics"
METRICS_VERSION = 1
class Spine42V3RasterMetricsError(ValueError):
    """Raised when capture PNG inventory or pixels are not exact."""
def compute_spine42_v3_raster_metrics(
    plan: Mapping[str, Any],
    artifact_png_bytes: Mapping[str, bytes],
) -> dict[str, Any]:
    """Recompute alpha masks and attachment coverage only from PNG bytes."""
    try:
        plan_sha = spine42_v3_runtime_plan_sha256(plan)
        if plan.get("profile_sha256") != spine42_v3_runtime_profile_sha256():
            raise Spine42V3RasterMetricsError(
                "Runtime capture plan uses an unknown profile"
            )
        cases, rows = _inventory(plan)
        snapshots = _snapshot_artifacts(rows, artifact_png_bytes)
        width, height = _expected_dimensions(plan)
        decoded = {
            artifact_id: _decode(data, artifact_id, width, height)
            for artifact_id, data in snapshots.items()
        }
        metrics = [
            _case_metrics(case, rows, decoded) for case in cases
        ]
        artifacts = [{
            "artifact_id": artifact_id,
            "png_sha256": hashlib.sha256(data).hexdigest(),
        } for artifact_id, data in snapshots.items()]
        body = {
            "format": METRICS_FORMAT,
            "format_version": METRICS_VERSION,
            "capture_plan_sha256": plan_sha,
            "profile_sha256": plan["profile_sha256"],
            "source": _json_copy(plan["source"]),
            "alpha_threshold_inclusive": ALPHA_THRESHOLD,
            "sampled_scope": _json_copy(plan["sampled_scope"]),
            "artifact_sha256s": artifacts,
            "cases": metrics,
            "summary": {
                "case_count": len(metrics),
                "artifact_count": len(artifacts),
                "passed_case_count": sum(row["passed"] for row in metrics),
                "failed_case_count": sum(not row["passed"] for row in metrics),
                "all_sampled_cases_passed": all(row["passed"] for row in metrics),
            },
            "semantics": {
                "scope": "bounded-discrete-samples-only",
                "continuous_time_safety_claimed": False,
                "unsampled_ticks_covered": False,
                "human_visual_approval_claimed": False,
            },
        }
        return {
            **body,
            "raster_metrics_sha256": canonical_sha256({
                "domain": METRICS_HASH_DOMAIN, **body,
            }),
        }
    except Spine42V3RasterMetricsError:
        raise
    except (
        KeyError, OverflowError, RgbaPngError, Spine42V3RuntimePlanError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42V3RasterMetricsError(
            f"Spine v3 raster metric computation failed: {exc}"
        ) from exc
def canonical_spine42_v3_raster_metrics_bytes(
    value: Mapping[str, Any],
) -> bytes:
    """Serialize metrics as stable strict JSON bytes."""
    if not isinstance(value, Mapping):
        raise Spine42V3RasterMetricsError("Raster metrics must be an object")
    try:
        return json.dumps(
            dict(value), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise Spine42V3RasterMetricsError(
            "Raster metrics are not strict finite JSON"
        ) from exc
def spine42_v3_raster_metrics_sha256(value: Mapping[str, Any]) -> str:
    """Recompute and require the domain-separated metrics identity."""
    body = json.loads(canonical_spine42_v3_raster_metrics_bytes(value))
    supplied = body.pop("raster_metrics_sha256", None)
    result = canonical_sha256({"domain": METRICS_HASH_DOMAIN, **body})
    if supplied != result:
        raise Spine42V3RasterMetricsError(
            "Raster metrics digest is inconsistent"
        )
    return result
def _inventory(plan):
    cases, artifacts = plan.get("cases"), plan.get("artifacts")
    attachments = plan.get("attachments")
    if type(cases) is not list or not cases or type(artifacts) is not list \
            or type(attachments) is not list \
            or len(artifacts) > MAX_CAPTURE_ARTIFACTS:
        raise Spine42V3RasterMetricsError("Capture inventory is invalid")
    rows, case_ids = {}, set()
    attachment_pairs = {
        (item.get("slot_id"), item.get("attachment_id"))
        for item in attachments if type(item) is dict
    }
    if len(attachment_pairs) != len(attachments):
        raise Spine42V3RasterMetricsError("Attachment inventory is invalid")
    for raw in artifacts:
        _artifact_row(raw, attachment_pairs)
        artifact_id = raw["artifact_id"]
        if artifact_id in rows:
            raise Spine42V3RasterMetricsError("Artifact ids are not unique")
        rows[artifact_id] = raw
    expected_per_case = 2 + len(attachments)
    for case in cases:
        if type(case) is not dict or type(case.get("case_id")) is not str \
                or case["case_id"] in case_ids \
                or type(case.get("artifact_ids")) is not list \
                or len(case["artifact_ids"]) != expected_per_case \
                or len(set(case["artifact_ids"])) != expected_per_case:
            raise Spine42V3RasterMetricsError("Capture case inventory is invalid")
        case_ids.add(case["case_id"])
        selected = [rows.get(item) for item in case["artifact_ids"]]
        if None in selected or any(
            row["case_id"] != case["case_id"] for row in selected
        ) or {row["kind"] for row in selected} != {
            "opaque_composite", "transparent_composite", "attachment_isolate"
        } and attachments:
            raise Spine42V3RasterMetricsError("Case artifact binding is invalid")
        if not attachments and {row["kind"] for row in selected} != {
            "opaque_composite", "transparent_composite"
        }:
            raise Spine42V3RasterMetricsError("Case artifact binding is invalid")
    if set(row["case_id"] for row in artifacts) != case_ids \
            or sum(len(case["artifact_ids"]) for case in cases) != len(rows):
        raise Spine42V3RasterMetricsError("Artifact inventory has extras")
    return cases, rows
def _artifact_row(row, attachment_pairs) -> None:
    fields = {
        "artifact_id", "path", "kind", "case_id", "slot_id",
        "attachment_id", "background",
    }
    if type(row) is not dict or set(row) != fields \
            or type(row.get("artifact_id")) is not str \
            or row.get("path") != f"{row.get('artifact_id')}.png" \
            or row.get("kind") not in {
                "opaque_composite", "transparent_composite", "attachment_isolate"
            }:
        raise Spine42V3RasterMetricsError("Capture artifact row is invalid")
    pair = (row.get("slot_id"), row.get("attachment_id"))
    if row["kind"] == "attachment_isolate":
        if pair not in attachment_pairs or row.get("background") != "#00000000":
            raise Spine42V3RasterMetricsError("Attachment isolate row is invalid")
    elif pair != (None, None) or row.get("background") != (
        "#20242aff" if row["kind"] == "opaque_composite" else "#00000000"
    ):
        raise Spine42V3RasterMetricsError("Composite artifact row is invalid")
def _snapshot_artifacts(rows, supplied):
    if not isinstance(supplied, Mapping) or set(supplied) != set(rows):
        raise Spine42V3RasterMetricsError(
            "PNG inventory is missing, extra, or incorrectly named"
        )
    result = {}
    for artifact_id in rows:
        data = supplied[artifact_id]
        if type(data) is not bytes:
            raise Spine42V3RasterMetricsError("PNG artifact must be bytes")
        result[artifact_id] = data
    return result
def _expected_dimensions(plan):
    capture = plan["capture"]
    viewport, dpr = capture["viewport"], capture["device_pixel_ratio"]
    return viewport["width"] * dpr, viewport["height"] * dpr
def _decode(data, artifact_id, width, height):
    image = decode_rgba_png(data, source_name=f"{artifact_id}.png")
    if (image.width, image.height) != (width, height):
        raise Spine42V3RasterMetricsError(
            "Capture PNG dimensions differ from the fixed viewport and DPR"
        )
    return image
def _case_metrics(case, rows, decoded):
    selected = [rows[item] for item in case["artifact_ids"]]
    opaque = next(row for row in selected if row["kind"] == "opaque_composite")
    alpha = next(row for row in selected if row["kind"] == "transparent_composite")
    isolates = [row for row in selected if row["kind"] == "attachment_isolate"]
    alpha_image = decoded[alpha["artifact_id"]]
    composite = _mask(alpha_image)
    isolate_metrics, isolate_masks = [], []
    for row in isolates:
        mask = _mask(decoded[row["artifact_id"]])
        isolate_masks.append(mask)
        isolate_metrics.append({
            "artifact_id": row["artifact_id"], "slot_id": row["slot_id"],
            "attachment_id": row["attachment_id"],
            "opaque_pixels": sum(mask), "boundary_pixels": _boundary(mask, alpha_image),
            "clipped_boundary_pixels": _clipped(mask, alpha_image),
            "nonempty": any(mask),
        })
    union = bytes(any(mask[index] for mask in isolate_masks)
                  for index in range(len(composite)))
    missing = sum(left and not right for left, right in zip(composite, union))
    extra = sum(right and not left for left, right in zip(composite, union))
    composite_boundary = _boundary_mask(composite, alpha_image)
    union_boundary = _boundary_mask(union, alpha_image)
    boundary_xor = sum(left != right for left, right in zip(
        composite_boundary, union_boundary
    ))
    nonopaque = sum(
        decoded[opaque["artifact_id"]].pixels[index] != 255
        for index in range(3, len(decoded[opaque["artifact_id"]].pixels), 4)
    )
    clipped = _clipped(composite, alpha_image)
    reasons = []
    if missing or extra:
        reasons.append("isolate_union_differs_from_transparent_composite")
    if boundary_xor:
        reasons.append("attachment_boundary_differs")
    if clipped:
        reasons.append("transparent_composite_touches_capture_boundary")
    if any(not row["nonempty"] for row in isolate_metrics):
        reasons.append("attachment_isolate_is_empty")
    if nonopaque:
        reasons.append("opaque_composite_has_nonopaque_pixels")
    return {
        "case_id": case["case_id"], "tick": case["tick"],
        "time_seconds": case["time_seconds"],
        "width": alpha_image.width, "height": alpha_image.height,
        "opaque_composite_nonopaque_pixels": nonopaque,
        "transparent_composite_opaque_pixels": sum(composite),
        "isolate_union_opaque_pixels": sum(union),
        "missing_pixels": missing, "extra_pixels": extra,
        "xor_pixels": missing + extra,
        "composite_boundary_pixels": sum(composite_boundary),
        "isolate_union_boundary_pixels": sum(union_boundary),
        "boundary_xor_pixels": boundary_xor,
        "clipped_boundary_pixels": clipped,
        "attachment_isolates": isolate_metrics,
        "reason_codes": reasons, "passed": not reasons,
    }
def _mask(image: RgbaImage) -> bytes:
    return bytes(
        image.pixels[index] >= ALPHA_THRESHOLD
        for index in range(3, len(image.pixels), 4)
    )
def _boundary(mask, image):
    return sum(_boundary_mask(mask, image))
def _boundary_mask(mask, image):
    result = bytearray(len(mask))
    for index, foreground in enumerate(mask):
        if not foreground:
            continue
        x, y = index % image.width, index // image.width
        neighbors = (
            index - 1 if x else None, index + 1 if x + 1 < image.width else None,
            index - image.width if y else None,
            index + image.width if y + 1 < image.height else None,
        )
        result[index] = any(item is None or not mask[item] for item in neighbors)
    return bytes(result)
def _clipped(mask, image):
    edge = set(range(image.width)) | set(range(
        (image.height - 1) * image.width, image.height * image.width
    ))
    edge.update(row * image.width for row in range(image.height))
    edge.update(row * image.width + image.width - 1 for row in range(image.height))
    return sum(mask[index] for index in edge)
def _json_copy(value):
    return json.loads(json.dumps(
        value, allow_nan=False, sort_keys=True, separators=(",", ":")
    ))
__all__ = [
    "METRICS_FORMAT", "METRICS_VERSION", "Spine42V3RasterMetricsError",
    "canonical_spine42_v3_raster_metrics_bytes",
    "compute_spine42_v3_raster_metrics",
    "spine42_v3_raster_metrics_sha256",
]
