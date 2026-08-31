"""Strict public TemporaryBodySwayPreview v2 manifest and byte contract."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_preview_profile_v2 import (
    PREVIEW_RELEASE_GATE,
    PREVIEW_SEMANTICS,
    body_sway_preview_compiler_profile_v2,
    body_sway_preview_runtime_target_v2,
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
from .temporary_body_sway_preview_asset_validation_v2 import (
    TemporaryBodySwayPreviewAssetValidationV2Error,
    require_temporary_body_sway_preview_artifacts_v2,
)
from .temporary_body_sway_preview_fields_v2 import (
    TemporaryBodySwayPreviewFieldV2Error,
    require_preview_capture_plan_v2,
    require_preview_projection_metadata_v2,
)
from .temporary_body_sway_preview_inventory_v2 import (
    TemporaryBodySwayPreviewInventoryV2Error,
    require_temporary_body_sway_preview_inventory_v2,
)


FORMAT = "autospine-temporary-body-sway-preview"
FORMAT_VERSION = 2
MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
_TOP_FIELDS = {
    "format", "format_version", "project_id", "clip_id", "source",
    "timing", "selection", "compiler", "semantics", "runtime_target",
    "projection", "capture_plan", "artifacts", "status", "release_gate",
    "summary",
}
_BODY_SOURCE_FIELDS = {
    "idle_behavior_candidates_sha256", "idle_behavior_decision_sha256",
    "layer_manifest_sha256", "p3", "p5", "p9",
}
_SOURCE_FIELDS = _BODY_SOURCE_FIELDS | {
    "body_sway_probe_report_sha256",
    "capture_framing_candidate_sha256",
    "capture_framing_decision_sha256",
    "capture_framing_revision",
    "current_p10_1_head",
}
_SUMMARY_FIELDS = {
    "probe_sample_count", "rotation_track_count", "rotation_key_count",
    "capture_case_count", "artifact_file_count", "artifact_total_bytes",
    "bone_count", "slot_count", "attachment_count",
    "region_attachment_count", "mesh_attachment_count", "atlas_width",
    "atlas_height",
}


class TemporaryBodySwayPreviewValidationV2Error(ValueError):
    """Raised when preview v2 overclaims or has inconsistent bytes."""


def require_temporary_body_sway_preview_manifest_v2(
    document: Mapping[str, Any],
) -> None:
    _validate_manifest(document)


def require_temporary_body_sway_preview_v2(
    document: Mapping[str, Any], artifact_bytes: Mapping[str, bytes],
) -> None:
    context = _validate_manifest(document)
    try:
        derived = require_temporary_body_sway_preview_artifacts_v2(
            context["artifacts"], artifact_bytes,
            project_id=context["project_id"], clip_id=context["clip_id"],
            source=context["source"], selection=context["selection"],
            timing=context["timing"],
            runtime_target=context["runtime_target"],
            projection=context["projection"],
            capture_plan=context["capture_plan"],
        )
        for field, expected in derived.items():
            if context["summary"][field] != expected:
                raise TemporaryBodySwayPreviewValidationV2Error(
                    f"Temporary preview v2 summary differs: {field}"
                )
    except TemporaryBodySwayPreviewValidationV2Error:
        raise
    except TemporaryBodySwayPreviewAssetValidationV2Error as exc:
        raise TemporaryBodySwayPreviewValidationV2Error(str(exc)) from exc


def temporary_body_sway_preview_sha256_v2(
    document: Mapping[str, Any], artifact_bytes: Mapping[str, bytes],
) -> str:
    require_temporary_body_sway_preview_v2(document, artifact_bytes)
    return canonical_sha256(document)


def _validate_manifest(document) -> dict[str, Any]:
    try:
        root = object_value(document, "Temporary body-sway preview v2")
        exact_fields(root, _TOP_FIELDS, "Temporary body-sway preview v2")
        if root.get("format") != FORMAT \
                or root.get("format_version") != FORMAT_VERSION:
            raise TemporaryBodySwayPreviewValidationV2Error(
                "Temporary body-sway preview v2 format is unsupported"
            )
        identifier_value(root.get("project_id"), "project_id")
        identifier_value(root.get("clip_id"), "clip_id")
        source = _source(root.get("source"))
        require_timing(root.get("timing"))
        selection = object_value(root.get("selection"), "selection")
        require_body_sway_selection(selection)
        _fixed(root.get("compiler"), body_sway_preview_compiler_profile_v2(),
               "compiler")
        _fixed(root.get("semantics"), PREVIEW_SEMANTICS, "semantics")
        runtime = body_sway_preview_runtime_target_v2()
        _fixed(root.get("runtime_target"), runtime, "runtime target")
        projection = object_value(root.get("projection"), "projection")
        counts = require_preview_projection_metadata_v2(
            projection, source=source, timing=root["timing"],
        )
        capture = object_value(root.get("capture_plan"), "capture plan")
        case_count = require_preview_capture_plan_v2(
            capture, timing=root["timing"], selection=dict(selection),
            projection=projection,
        )
        artifacts = object_value(root.get("artifacts"), "artifacts")
        files = require_temporary_body_sway_preview_inventory_v2(artifacts)
        summary = _summary(root.get("summary"), counts, case_count, files)
        if root.get("status") \
                != "ready_for_official_runtime_capture_v2" \
                or root.get("release_gate") != PREVIEW_RELEASE_GATE:
            raise TemporaryBodySwayPreviewValidationV2Error(
                "Temporary preview v2 status and gate must remain blocked"
            )
        if len(_canonical(root)) > MAX_DOCUMENT_BYTES:
            raise TemporaryBodySwayPreviewValidationV2Error(
                "Temporary preview v2 manifest is too large"
            )
        return {
            "project_id": root["project_id"], "clip_id": root["clip_id"],
            "source": source, "runtime_target": runtime,
            "timing": dict(root["timing"]), "selection": dict(selection),
            "projection": dict(projection), "capture_plan": dict(capture),
            "artifacts": dict(artifacts), "summary": summary,
        }
    except TemporaryBodySwayPreviewValidationV2Error:
        raise
    except (
        BodySwayProbeValidationError, IdleBehaviorDecisionFieldError,
        TemporaryBodySwayPreviewFieldV2Error,
        TemporaryBodySwayPreviewInventoryV2Error,
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise TemporaryBodySwayPreviewValidationV2Error(
            f"Temporary body-sway preview v2 validation failed: {exc}"
        ) from exc


def _source(value) -> dict[str, Any]:
    source = object_value(value, "Temporary preview v2 source")
    exact_fields(source, _SOURCE_FIELDS, "Temporary preview v2 source")
    for field in (
        "body_sway_probe_report_sha256", "capture_framing_candidate_sha256",
        "capture_framing_decision_sha256",
    ):
        digest_value(source.get(field), field)
    revision = source.get("capture_framing_revision")
    if type(revision) is not int or not 1 <= revision <= 64:
        raise TemporaryBodySwayPreviewValidationV2Error(
            "Temporary preview v2 framing revision is invalid"
        )
    head = source.get("current_p10_1_head")
    if not isinstance(head, Mapping) or set(head) != {
        "candidate_sha256", "decision_sha256", "revision",
    }:
        raise TemporaryBodySwayPreviewValidationV2Error(
            "Temporary preview v2 P10.1 head fields are invalid"
        )
    digest_value(head.get("candidate_sha256"), "P10.1 candidate SHA-256")
    digest_value(head.get("decision_sha256"), "P10.1 decision SHA-256")
    if head["candidate_sha256"] != source["idle_behavior_candidates_sha256"] \
            or head["decision_sha256"] \
            != source["idle_behavior_decision_sha256"] \
            or type(head.get("revision")) is not int \
            or not 1 <= head["revision"] <= 64:
        raise TemporaryBodySwayPreviewValidationV2Error(
            "Temporary preview v2 P10.1 head differs from body source"
        )
    require_body_sway_source({field: source[field]
                              for field in _BODY_SOURCE_FIELDS})
    return dict(source)


def _summary(value, projection, case_count, files) -> dict[str, int]:
    row = object_value(value, "Temporary preview v2 summary")
    exact_fields(row, _SUMMARY_FIELDS, "Temporary preview v2 summary")
    if any(type(row.get(field)) is not int or row[field] < 0
           for field in _SUMMARY_FIELDS):
        raise TemporaryBodySwayPreviewValidationV2Error(
            "Temporary preview v2 summary values are invalid"
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
            or not 1 <= row["bone_count"] <= 4096 \
            or not 1 <= row["slot_count"] <= 4096 \
            or not 1 <= row["attachment_count"] <= 4096 \
            or row["attachment_count"] != row["region_attachment_count"] \
            + row["mesh_attachment_count"] \
            or not 1 <= row["atlas_width"] <= 4096 \
            or not 1 <= row["atlas_height"] <= 4096:
        raise TemporaryBodySwayPreviewValidationV2Error(
            "Temporary preview v2 summary differs from its manifest"
        )
    return {field: row[field] for field in _SUMMARY_FIELDS}


def _fixed(value, expected, label) -> None:
    if canonical_sha256(object_value(value, label)) != canonical_sha256(expected):
        raise TemporaryBodySwayPreviewValidationV2Error(
            f"Temporary preview v2 {label} is unsupported"
        )


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
