"""Detached validation for official execution evidence around payload v2."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_runtime_capture_v2 import BodySwayRuntimeCaptureV2
from .body_sway_runtime_capture_v2_validation import (
    require_body_sway_runtime_capture_v2,
)
from .body_sway_runtime_execution_profile import (
    AUTHORITY,
    FORMAT,
    FORMAT_VERSION,
    MAX_MANIFEST_BYTES,
    RELEASE_GATE,
    body_sway_runtime_execution_compiler_profile,
    body_sway_runtime_execution_runner_profile,
)
from .browser_version_identity import browser_version_identity_sha256
from .idle_behavior_decision_validation_fields import digest_value
from .resolved_project import canonical_sha256


class BodySwayRuntimeExecutionValidationError(ValueError):
    """Raised when execution evidence overclaims or is cross-wired."""


def require_body_sway_runtime_execution(
    document: Mapping[str, Any], capture: BodySwayRuntimeCaptureV2,
) -> None:
    """Require one exact outer receipt and its complete inner payload v2."""

    try:
        if type(capture) is not BodySwayRuntimeCaptureV2:
            raise BodySwayRuntimeExecutionValidationError(
                "Execution evidence requires an exact RuntimeCapture v2"
            )
        require_body_sway_runtime_capture_v2(
            capture.document, capture.capture_bytes,
        )
        root = _object(document, "execution evidence")
        _exact(root, {
            "format", "format_version", "project_id", "clip_id", "source",
            "compiler", "authority", "runtime", "browser", "runner",
            "reports", "status", "release_gate", "summary",
        }, "execution evidence")
        if root.get("format") != FORMAT \
                or root.get("format_version") != FORMAT_VERSION \
                or root.get("status") != "captured_unreviewed" \
                or root.get("compiler") \
                != body_sway_runtime_execution_compiler_profile() \
                or root.get("authority") != AUTHORITY \
                or root.get("runner") \
                != body_sway_runtime_execution_runner_profile() \
                or root.get("release_gate") != RELEASE_GATE:
            raise BodySwayRuntimeExecutionValidationError(
                "Execution evidence profile or authority is unsupported"
            )
        inner = capture.document
        if root.get("project_id") != inner["project_id"] \
                or root.get("clip_id") != inner["clip_id"]:
            raise BodySwayRuntimeExecutionValidationError(
                "Execution evidence identity differs from payload v2"
            )
        source = _source(root.get("source"), capture)
        _runtime(root.get("runtime"), inner["runtime"])
        _browser(root.get("browser"), inner["browser"])
        reports = _reports(
            root.get("reports"), capture, source["runtime_session_set_v2_sha256"],
            root["runtime"],
        )
        summary = _object(root.get("summary"), "summary")
        if summary != {
            "case_count": len(reports),
            "runtime_error_count": 0,
            "png_total_bytes": inner["summary"]["png_total_bytes"],
        }:
            raise BodySwayRuntimeExecutionValidationError(
                "Execution evidence summary is inconsistent"
            )
        raw = json.dumps(
            root, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if not 0 < len(raw) <= MAX_MANIFEST_BYTES:
            raise BodySwayRuntimeExecutionValidationError(
                "Execution evidence exceeds its byte limit"
            )
    except BodySwayRuntimeExecutionValidationError:
        raise
    except (
        AttributeError, KeyError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeExecutionValidationError(
            f"Runtime execution evidence validation failed: {exc}"
        ) from exc


def body_sway_runtime_execution_sha256(document, capture) -> str:
    require_body_sway_runtime_execution(document, capture)
    return canonical_sha256(document)


def _source(value, capture):
    row = _object(value, "source")
    fields = {
        "temporary_preview_v2_sha256", "preview_artifact_set_sha256",
        "runtime_capture_v2_sha256", "capture_artifact_set_sha256",
        "runtime_session_set_v2_sha256", "capture_plan_v2_sha256",
        "capture_framing_candidate_sha256",
        "capture_framing_decision_sha256", "capture_framing_revision",
        "body_sway_probe_report_sha256", "current_p10_1_head",
        "world_viewport",
    }
    _exact(row, fields, "source")
    inner = capture.document
    expected = {
        "temporary_preview_v2_sha256":
            inner["source"]["temporary_preview_v2_sha256"],
        "preview_artifact_set_sha256":
            inner["source"]["preview_artifact_set_sha256"],
        "runtime_capture_v2_sha256": capture.sha256,
        "capture_artifact_set_sha256": capture.artifact_set_sha256,
        "capture_plan_v2_sha256":
            inner["source"]["capture_plan_v2_sha256"],
        "capture_framing_candidate_sha256":
            inner["source"]["capture_framing_candidate_sha256"],
        "capture_framing_decision_sha256":
            inner["source"]["capture_framing_decision_sha256"],
        "capture_framing_revision":
            inner["source"]["capture_framing_revision"],
        "body_sway_probe_report_sha256":
            inner["source"]["body_sway_probe_report_sha256"],
        "current_p10_1_head": inner["source"]["current_p10_1_head"],
        "world_viewport": inner["source"]["world_viewport"],
    }
    session_sha = row.get("runtime_session_set_v2_sha256")
    digest_value(session_sha, "runtime session set v2 SHA-256")
    if any(row.get(field) != expected_value
           for field, expected_value in expected.items()):
        raise BodySwayRuntimeExecutionValidationError(
            "Execution source differs from the inner payload v2"
        )
    return row


def _runtime(value, inner):
    row = _object(value, "runtime")
    expected_fields = set(inner) | {
        "package_json_sha256", "license_sha256", "license_acknowledged",
        "license_file_presence_is_authorization",
    }
    _exact(row, expected_fields, "runtime")
    if any(row.get(field) != expected for field, expected in inner.items()) \
            or row.get("license_acknowledged") is not True \
            or row.get("license_file_presence_is_authorization") is not False:
        raise BodySwayRuntimeExecutionValidationError(
            "Execution runtime identity or license acknowledgement is invalid"
        )
    digest_value(row.get("package_json_sha256"), "runtime package.json SHA-256")
    digest_value(row.get("license_sha256"), "runtime license SHA-256")


def _browser(value, inner):
    row = _object(value, "browser")
    _exact(row, set(inner), "browser")
    if dict(row) != dict(inner) \
            or row.get("version_output_sha256") \
            != browser_version_identity_sha256(
                row.get("family"), row.get("reported_version"),
            ):
        raise BodySwayRuntimeExecutionValidationError(
            "Execution browser identity differs from payload v2"
        )


def _reports(value, capture, session_sha, execution_runtime):
    if not isinstance(value, list) \
            or len(value) != len(capture.document["cases"]):
        raise BodySwayRuntimeExecutionValidationError(
            "Execution report count differs from payload v2"
        )
    inner = capture.document
    files = {
        row["case_id"]: row for row in inner["artifacts"]["files"]
    }
    session_runtime = {
        field: field_value for field, field_value in execution_runtime.items()
        if field != "license_acknowledged"
    }
    capture_settings = {
        field: inner["capture"][field] for field in (
            "viewport", "device_pixel_ratio", "background",
            "preserve_drawing_buffer", "world_viewport",
        )
    }
    report_fields = {
        "status", "project_id", "clip_id", "session_set_sha256",
        "runtime", "source", "assets", "capture", "case", "image",
    }
    for report, case in zip(value, inner["cases"], strict=True):
        if type(report) is not dict or set(report) != report_fields:
            raise BodySwayRuntimeExecutionValidationError(
                "Execution report fields are invalid"
            )
        image = report.get("image")
        case_id = case["case_id"]
        expected_image = {
            "path": case["image_path"], "png_sha256": case["png_sha256"],
            "width": files[case_id]["width"],
            "height": files[case_id]["height"],
            "size_bytes": files[case_id]["size_bytes"],
        }
        observed_case = report.get("case")
        if report.get("status") != "captured" \
                or report.get("project_id") != inner["project_id"] \
                or report.get("clip_id") != inner["clip_id"] \
                or report.get("session_set_sha256") != session_sha \
                or report.get("runtime") != session_runtime \
                or report.get("source") != inner["source"] \
                or report.get("assets") != inner["assets"] \
                or report.get("capture") != capture_settings \
                or image != expected_image \
                or observed_case != {
                    "id": case_id, "animation": case["animation"],
                    "tick": case["tick"],
                    "time_seconds": case["time_seconds"],
                }:
            raise BodySwayRuntimeExecutionValidationError(
                "Execution report differs from payload v2 or session seal"
            )
    return value


def _object(value, label):
    if not isinstance(value, Mapping):
        raise BodySwayRuntimeExecutionValidationError(
            f"Execution evidence {label} must be an object"
        )
    return value


def _exact(value, fields, label):
    if set(value) != set(fields):
        raise BodySwayRuntimeExecutionValidationError(
            f"Execution evidence {label} fields are invalid"
        )


__all__ = [
    "BodySwayRuntimeExecutionValidationError",
    "body_sway_runtime_execution_sha256",
    "require_body_sway_runtime_execution",
]
