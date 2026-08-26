"""Strict public TemporaryBodySwayPreview v1 manifest and byte contract."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_preview_profile import (
    PREVIEW_RELEASE_GATE,
    PREVIEW_SEMANTICS,
    body_sway_preview_compiler_profile,
    body_sway_preview_runtime_target,
)
from .body_sway_probe_validation import (
    BodySwayProbeValidationError,
    require_body_sway_selection,
    require_body_sway_source,
)
from .idle_behavior_decision_validation_fields import (
    IdleBehaviorDecisionFieldError,
    digest_value,
    exact_fields,
    identifier_value,
    object_value,
    require_timing,
)
from .resolved_project import canonical_sha256
from .temporary_body_sway_preview_asset_validation import (
    TemporaryBodySwayPreviewAssetValidationError,
    require_temporary_body_sway_preview_artifacts,
)
from .temporary_body_sway_preview_fields import (
    TemporaryBodySwayPreviewFieldError,
    require_preview_capture_plan,
    require_preview_projection_metadata,
)
from .temporary_body_sway_preview_inventory import (
    TemporaryBodySwayPreviewInventoryError,
    require_temporary_body_sway_preview_inventory,
)


FORMAT = "autospine-temporary-body-sway-preview"
FORMAT_VERSION = 1
MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
_TOP_FIELDS = {
    "format", "format_version", "project_id", "clip_id", "source",
    "timing", "selection", "compiler", "semantics", "runtime_target",
    "projection", "capture_plan", "artifacts", "status", "release_gate",
    "summary",
}
_SOURCE_FIELDS = {
    "body_sway_probe_report_sha256", "idle_behavior_candidates_sha256",
    "idle_behavior_decision_sha256", "layer_manifest_sha256", "p3", "p5",
    "p9",
}
_SUMMARY_FIELDS = {
    "probe_sample_count", "rotation_track_count", "rotation_key_count",
    "capture_case_count", "artifact_file_count", "artifact_total_bytes",
    "bone_count", "slot_count", "attachment_count",
    "region_attachment_count", "mesh_attachment_count", "atlas_width",
    "atlas_height",
}


class TemporaryBodySwayPreviewValidationError(ValueError):
    """Raised when a temporary preview overclaims or has inconsistent bytes."""


def require_temporary_body_sway_preview_manifest(
    document: Mapping[str, Any],
) -> None:
    """Validate standalone manifest shape, semantics, seals, and aggregates."""

    _validate_manifest(document)


def require_temporary_body_sway_preview(
    document: Mapping[str, Any], artifact_bytes: Mapping[str, bytes],
) -> None:
    """Validate the manifest together with every exact artifact byte."""

    context = _validate_manifest(document)
    try:
        derived = require_temporary_body_sway_preview_artifacts(
            context["artifacts"], artifact_bytes,
            project_id=context["project_id"],
            clip_id=context["clip_id"],
            source=context["source"],
            selection=context["selection"],
            timing=context["timing"],
            runtime_target=context["runtime_target"],
            projection=context["projection"],
            capture_plan=context["capture_plan"],
        )
        summary = context["summary"]
        for field, expected in derived.items():
            if summary[field] != expected:
                raise TemporaryBodySwayPreviewValidationError(
                    f"Temporary preview summary differs from bytes: {field}"
                )
    except TemporaryBodySwayPreviewValidationError:
        raise
    except TemporaryBodySwayPreviewAssetValidationError as exc:
        raise TemporaryBodySwayPreviewValidationError(str(exc)) from exc


def temporary_body_sway_preview_sha256(
    document: Mapping[str, Any], artifact_bytes: Mapping[str, bytes],
) -> str:
    """Return manifest identity only after the complete five-file validation."""

    require_temporary_body_sway_preview(document, artifact_bytes)
    return canonical_sha256(document)


def _validate_manifest(document) -> dict[str, Any]:
    try:
        root = object_value(document, "Temporary body-sway preview")
        exact_fields(root, _TOP_FIELDS, "Temporary body-sway preview")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise TemporaryBodySwayPreviewValidationError(
                "Temporary body-sway preview format is unsupported"
            )
        identifier_value(root.get("project_id"), "project_id")
        identifier_value(root.get("clip_id"), "clip_id")
        source = _source(root.get("source"))
        require_timing(root.get("timing"))
        selection = object_value(root.get("selection"), "selection")
        require_body_sway_selection(selection)
        _fixed(root.get("compiler"), body_sway_preview_compiler_profile(),
               "compiler")
        _fixed(root.get("semantics"), PREVIEW_SEMANTICS, "semantics")
        runtime = body_sway_preview_runtime_target()
        _fixed(root.get("runtime_target"), runtime, "runtime target")
        projection = object_value(root.get("projection"), "projection")
        timing = root["timing"]
        counts = require_preview_projection_metadata(
            projection, source=source, timing=timing
        )
        capture = object_value(root.get("capture_plan"), "capture plan")
        case_count = require_preview_capture_plan(
            capture,
            duration=timing["duration_ticks"],
            ticks_per_second=timing["ticks_per_second"],
            selection=dict(selection),
            sample_ticks=counts["sample_ticks"],
        )
        artifacts = object_value(root.get("artifacts"), "artifacts")
        files = require_temporary_body_sway_preview_inventory(artifacts)
        summary = _summary(root.get("summary"), counts, case_count, files)
        if root.get("status") != "ready_for_official_runtime_capture" \
                or root.get("release_gate") != PREVIEW_RELEASE_GATE:
            raise TemporaryBodySwayPreviewValidationError(
                "Temporary preview status and release gate must remain blocked"
            )
        encoded = _canonical(root)
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise TemporaryBodySwayPreviewValidationError(
                "Temporary preview manifest exceeds its byte limit"
            )
        return {
            "project_id": root["project_id"],
            "clip_id": root["clip_id"],
            "source": source, "runtime_target": runtime,
            "timing": dict(timing),
            "selection": dict(selection),
            "projection": dict(projection), "capture_plan": dict(capture),
            "artifacts": dict(artifacts), "summary": summary,
        }
    except TemporaryBodySwayPreviewValidationError:
        raise
    except (
        BodySwayProbeValidationError, IdleBehaviorDecisionFieldError,
        TemporaryBodySwayPreviewFieldError,
        TemporaryBodySwayPreviewInventoryError,
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewValidationError(
            f"Temporary body-sway preview validation failed: {exc}"
        ) from exc


def _source(value) -> dict[str, Any]:
    source = object_value(value, "Temporary preview source")
    exact_fields(source, _SOURCE_FIELDS, "Temporary preview source")
    digest_value(
        source.get("body_sway_probe_report_sha256"),
        "body_sway_probe_report_sha256",
    )
    body_source = {
        field: source[field]
        for field in _SOURCE_FIELDS - {"body_sway_probe_report_sha256"}
    }
    require_body_sway_source(body_source)
    return dict(source)


def _summary(value, projection, case_count, files) -> dict[str, int]:
    row = object_value(value, "Temporary preview summary")
    exact_fields(row, _SUMMARY_FIELDS, "Temporary preview summary")
    for field in _SUMMARY_FIELDS:
        if type(row.get(field)) is not int or row[field] < 0:
            raise TemporaryBodySwayPreviewValidationError(
                f"Temporary preview summary is invalid: {field}"
            )
    expected = {
        "probe_sample_count": projection["sample_count"],
        "rotation_track_count": projection["rotation_track_count"],
        "rotation_key_count": projection["rotation_key_count"],
        "capture_case_count": case_count,
        "artifact_file_count": len(files),
        "artifact_total_bytes": sum(item["size_bytes"] for item in files),
    }
    if any(row[field] != count for field, count in expected.items()) \
            or row["bone_count"] < 1 or row["slot_count"] < 1 \
            or row["attachment_count"] < 1 \
            or row["bone_count"] > 4096 or row["slot_count"] > 4096 \
            or row["attachment_count"] > 16_384 \
            or row["region_attachment_count"] > 16_384 \
            or row["mesh_attachment_count"] > 16_384 \
            or row["attachment_count"] != row["region_attachment_count"] \
            + row["mesh_attachment_count"] \
            or not 1 <= row["atlas_width"] <= 4096 \
            or not 1 <= row["atlas_height"] <= 4096:
        raise TemporaryBodySwayPreviewValidationError(
            "Temporary preview summary differs from its manifest"
        )
    return {field: row[field] for field in _SUMMARY_FIELDS}


def _fixed(value, expected, label) -> None:
    if canonical_sha256(object_value(value, label)) != canonical_sha256(expected):
        raise TemporaryBodySwayPreviewValidationError(
            f"Temporary preview {label} is unsupported"
        )


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
