"""Strict detached validation for BodySwayRuntimeCapture v2 evidence."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_probe_validation import require_body_sway_selection
from .body_sway_runtime_capture_v2_inventory import (
    BodySwayRuntimeCaptureV2InventoryError,
    require_body_sway_runtime_capture_v2_inventory,
)
from .body_sway_runtime_capture_v2_profile import (
    CAPTURE_DEVICE_PIXEL_RATIO,
    CAPTURE_VIEWPORT,
    CASE_STREAM_DIGEST_DOMAIN,
    FORMAT,
    FORMAT_VERSION,
    MAX_CAPTURE_DOCUMENT_BYTES,
    RELEASE_GATE,
    SEMANTICS,
    body_sway_runtime_capture_v2_compiler_profile,
)
from .body_sway_runtime_capture_v2_fields import (
    BodySwayRuntimeCaptureV2FieldError,
    require_runtime_v2_assets,
    require_runtime_v2_browser,
    require_runtime_v2_identity,
    require_runtime_v2_world_viewport,
)
from .idle_behavior_decision_validation_fields import (
    digest_value,
    identifier_value,
    require_timing,
)
from .resolved_project import canonical_sha256


class BodySwayRuntimeCaptureV2ValidationError(ValueError):
    """Raised when capture-framed runtime evidence is malformed or overclaims."""


def require_body_sway_runtime_capture_v2(
    document: Mapping[str, Any], capture_bytes: Mapping[str, bytes],
) -> None:
    """Validate one canonicalizable manifest and every exact PNG byte."""

    try:
        root = _object(document, "capture")
        _exact(root, {
            "format", "format_version", "project_id", "clip_id", "source",
            "timing", "selection", "compiler", "semantics", "runtime",
            "assets", "browser", "capture", "cases", "artifacts", "status",
            "release_gate", "summary",
        }, "capture")
        if root.get("format") != FORMAT \
                or root.get("format_version") != FORMAT_VERSION:
            raise BodySwayRuntimeCaptureV2ValidationError(
                "Runtime capture v2 format is unsupported"
            )
        identifier_value(root.get("project_id"), "project_id")
        identifier_value(root.get("clip_id"), "clip_id")
        source = _source(root.get("source"))
        require_timing(root.get("timing"))
        selection = _object(root.get("selection"), "selection")
        require_body_sway_selection(selection)
        _fixed(root.get("compiler"),
               body_sway_runtime_capture_v2_compiler_profile(), "compiler")
        _fixed(root.get("semantics"), SEMANTICS, "semantics")
        require_runtime_v2_identity(root.get("runtime"))
        require_runtime_v2_assets(root.get("assets"))
        require_runtime_v2_browser(root.get("browser"))
        plan = _capture(root.get("capture"), root["timing"])
        if source["capture_plan_v2_sha256"] \
                != plan["capture_plan_sha256"] \
                or source["world_viewport"] != plan["world_viewport"]:
            raise BodySwayRuntimeCaptureV2ValidationError(
                "Runtime capture v2 source differs from its capture plan"
            )
        files = require_body_sway_runtime_capture_v2_inventory(
            root.get("artifacts"), capture_bytes
        )
        cases = _cases(root.get("cases"), plan["cases"], files)
        if plan["case_stream_sha256"] != _case_stream_sha256(cases):
            raise BodySwayRuntimeCaptureV2ValidationError(
                "Runtime capture v2 case stream is inconsistent"
            )
        _aggregate(root, cases, files)
        if len(_canonical(root)) > MAX_CAPTURE_DOCUMENT_BYTES:
            raise BodySwayRuntimeCaptureV2ValidationError(
                "Runtime capture v2 manifest exceeds its byte limit"
            )
    except BodySwayRuntimeCaptureV2ValidationError:
        raise
    except (
        BodySwayRuntimeCaptureV2FieldError,
        BodySwayRuntimeCaptureV2InventoryError, KeyError, OverflowError,
        RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureV2ValidationError(
            f"Runtime capture v2 validation failed: {exc}"
        ) from exc


def body_sway_runtime_capture_v2_sha256(document, capture_bytes) -> str:
    require_body_sway_runtime_capture_v2(document, capture_bytes)
    return canonical_sha256(document)


def body_sway_runtime_capture_v2_case_stream_sha256(cases) -> str:
    return _case_stream_sha256(cases)


def _source(value: Any) -> Mapping[str, Any]:
    row = _object(value, "source")
    digest_fields = {
        "temporary_preview_v2_sha256", "preview_artifact_set_sha256",
        "preview_projection_v2_sha256", "capture_plan_v2_sha256",
        "preview_source_sha256",
        "capture_framing_candidate_sha256",
        "capture_framing_decision_sha256", "body_sway_probe_report_sha256",
    }
    _exact(row, {*digest_fields, "capture_framing_revision",
                 "current_p10_1_head", "world_viewport"}, "source")
    for field in digest_fields:
        digest_value(row.get(field), field)
    if row["capture_framing_candidate_sha256"] \
            == row["capture_framing_decision_sha256"]:
        raise BodySwayRuntimeCaptureV2ValidationError(
            "Runtime capture v2 candidate and decision identities collide"
        )
    revision = row.get("capture_framing_revision")
    if type(revision) is not int or not 1 <= revision <= 64:
        raise BodySwayRuntimeCaptureV2ValidationError(
            "Runtime capture v2 framing revision is invalid"
        )
    require_runtime_v2_world_viewport(row.get("world_viewport"))
    head = _object(row.get("current_p10_1_head"), "P10.1 head")
    _exact(head, {"candidate_sha256", "decision_sha256", "revision"},
           "P10.1 head")
    digest_value(head.get("candidate_sha256"), "P10.0 candidate SHA-256")
    digest_value(head.get("decision_sha256"), "P10.1 decision SHA-256")
    if type(head.get("revision")) is not int \
            or not 1 <= head["revision"] <= 10_000:
        raise BodySwayRuntimeCaptureV2ValidationError(
            "Runtime capture v2 P10.1 revision is invalid"
        )
    return row


def _capture(value: Any, timing: Mapping[str, Any]) -> Mapping[str, Any]:
    row = _object(value, "capture settings")
    _exact(row, {
        "viewport", "device_pixel_ratio", "background",
        "preserve_drawing_buffer", "world_viewport",
        "capture_plan_sha256", "case_stream_sha256", "cases",
    }, "capture settings")
    if row["viewport"] != CAPTURE_VIEWPORT \
            or row["device_pixel_ratio"] != CAPTURE_DEVICE_PIXEL_RATIO \
            or row["preserve_drawing_buffer"] is not True \
            or row["background"] != "#20242aff":
        raise BodySwayRuntimeCaptureV2ValidationError(
            "Runtime capture v2 pixel viewport differs from the fixed profile"
        )
    require_runtime_v2_world_viewport(row.get("world_viewport"))
    digest_value(row.get("capture_plan_sha256"), "capture plan SHA-256")
    digest_value(row.get("case_stream_sha256"), "case stream SHA-256")
    cases = row.get("cases")
    if not isinstance(cases, list) or len(cases) < 3 or len(cases) % 2 != 1:
        raise BodySwayRuntimeCaptureV2ValidationError(
            "Runtime capture v2 plan must contain setup and paired cases"
        )
    _plan_cases(cases, timing)
    return row


def _plan_cases(cases, timing) -> None:
    ids = set()
    for index, value in enumerate(cases):
        row = _object(value, "planned case")
        _exact(row, {"case_id", "animation", "tick", "time_seconds"},
               "planned case")
        identifier_value(row.get("case_id"), "case_id")
        tick = row.get("tick")
        if row["case_id"] in ids or type(tick) is not int \
                or not 0 <= tick <= timing["duration_ticks"] \
                or row.get("time_seconds") != tick / timing["ticks_per_second"]:
            raise BodySwayRuntimeCaptureV2ValidationError(
                "Runtime capture v2 planned case is invalid"
            )
        ids.add(row["case_id"])
        expected_animation = None if index == 0 else (
            "p10.base" if index % 2 == 1 else "p10.body-sway"
        )
        if row["animation"] != expected_animation \
                or index == 0 and (row["case_id"] != "setup" or tick != 0):
            raise BodySwayRuntimeCaptureV2ValidationError(
                "Runtime capture v2 planned case order is invalid"
            )
        if index > 1 and index % 2 == 0 and tick != cases[index - 1]["tick"]:
            raise BodySwayRuntimeCaptureV2ValidationError(
                "Runtime capture v2 base/combined ticks differ"
            )


def _cases(value, planned, files):
    if not isinstance(value, list) or len(value) != len(planned) \
            or len(value) != len(files):
        raise BodySwayRuntimeCaptureV2ValidationError(
            "Runtime capture v2 case count differs"
        )
    result = []
    for row, plan, artifact in zip(value, planned, files, strict=True):
        item = _object(row, "captured case")
        expected = {
            **plan, "image_path": artifact["path"],
            "png_sha256": artifact["sha256"],
        }
        if dict(item) != expected or artifact["case_id"] != plan["case_id"]:
            raise BodySwayRuntimeCaptureV2ValidationError(
                "Runtime capture v2 case differs from plan or PNG"
            )
        result.append(expected)
    return result


def _aggregate(root, cases, files) -> None:
    if root.get("status") \
            != "validated_capture_payload_ready_for_official_runtime_execution" \
            or root.get("release_gate") != RELEASE_GATE:
        raise BodySwayRuntimeCaptureV2ValidationError(
            "Runtime capture v2 must remain unexecuted, unreviewed, and blocked"
        )
    pair_count = (len(cases) - 1) // 2
    expected = {
        "case_count": len(cases), "setup_case_count": 1,
        "base_case_count": pair_count, "combined_case_count": pair_count,
        "runtime_error_count": 0,
        "png_total_bytes": sum(row["size_bytes"] for row in files),
    }
    if root.get("summary") != expected:
        raise BodySwayRuntimeCaptureV2ValidationError(
            "Runtime capture v2 summary is inconsistent"
        )


def _case_stream_sha256(cases) -> str:
    return canonical_sha256({"domain": CASE_STREAM_DIGEST_DOMAIN,
                             "cases": list(cases)})


def _object(value, label) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BodySwayRuntimeCaptureV2ValidationError(
            f"Runtime capture v2 {label} must be an object"
        )
    return value


def _exact(value, fields, label) -> None:
    if set(value) != set(fields):
        raise BodySwayRuntimeCaptureV2ValidationError(
            f"Runtime capture v2 {label} fields are invalid"
        )


def _fixed(value, expected, label) -> None:
    if canonical_sha256(_object(value, label)) != canonical_sha256(expected):
        raise BodySwayRuntimeCaptureV2ValidationError(
            f"Runtime capture v2 {label} is unsupported"
        )


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")
