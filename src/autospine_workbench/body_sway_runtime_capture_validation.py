"""Strict public BodySwayRuntimeCapture v1 evidence validation."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .body_sway_probe_validation import (
    require_body_sway_selection,
    require_body_sway_source,
)
from .body_sway_runtime_capture_inventory import (
    BodySwayRuntimeCaptureInventoryError,
    require_body_sway_runtime_capture_inventory,
)
from .body_sway_runtime_capture_profile import (
    CAPTURE_RELEASE_GATE,
    CAPTURE_SEMANTICS,
    CASE_STREAM_DIGEST_DOMAIN,
    MAX_CAPTURE_DOCUMENT_BYTES,
    body_sway_runtime_capture_compiler_profile,
    body_sway_runtime_capture_runner_profile,
)
from .body_sway_runtime_capture_session_validation import (
    require_body_sway_capture_sample_ticks,
    require_body_sway_runtime_capture_assets,
    require_body_sway_runtime_identity,
)
from .browser_executable_snapshot import MAX_EXECUTABLE_BYTES
from .browser_version_identity import (
    BrowserVersionIdentityError,
    browser_version_identity_sha256,
)
from .idle_behavior_decision_validation_fields import (
    digest_value,
    identifier_value,
    require_timing,
)
from .resolved_project import canonical_sha256
from .temporary_body_sway_preview_fields import require_preview_capture_plan


FORMAT = "autospine-body-sway-runtime-capture"
FORMAT_VERSION = 1
_TOP_FIELDS = {
    "format", "format_version", "project_id", "clip_id", "source",
    "timing", "selection", "compiler", "semantics", "runtime", "assets",
    "browser", "runner", "capture", "cases", "artifacts", "status",
    "release_gate", "summary",
}
_SOURCE_FIELDS = {
    "temporary_preview_sha256", "preview_artifact_set_sha256",
    "preview_projection_sha256", "capture_plan_sha256",
    "runtime_session_set_sha256", "upstream",
}
_CASE_FIELDS = {
    "case_id", "animation", "tick", "time_seconds", "image_path",
    "png_sha256",
}
class BodySwayRuntimeCaptureValidationError(ValueError):
    """Raised when runtime capture evidence is incomplete or overclaims."""


def require_body_sway_runtime_capture(
    document: Mapping[str, Any], capture_bytes: Mapping[str, bytes],
) -> None:
    """Validate a detached manifest and every exact PNG capture byte."""

    try:
        root = _object(document, "runtime capture")
        _exact(root, _TOP_FIELDS, "runtime capture")
        if root.get("format") != FORMAT \
                or type(root.get("format_version")) is not int \
                or root.get("format_version") != FORMAT_VERSION:
            raise BodySwayRuntimeCaptureValidationError(
                "Body-sway runtime capture format is unsupported"
            )
        identifier_value(root.get("project_id"), "project_id")
        identifier_value(root.get("clip_id"), "clip_id")
        source = _source(root.get("source"))
        require_timing(root.get("timing"))
        selection = _object(root.get("selection"), "selection")
        require_body_sway_selection(selection)
        _fixed(
            root.get("compiler"),
            body_sway_runtime_capture_compiler_profile(), "compiler",
        )
        _fixed(root.get("semantics"), CAPTURE_SEMANTICS, "semantics")
        require_body_sway_runtime_identity(root.get("runtime"))
        require_body_sway_runtime_capture_assets(root.get("assets"))
        _browser(root.get("browser"))
        _fixed(
            root.get("runner"),
            body_sway_runtime_capture_runner_profile(), "runner",
        )
        timing = root["timing"]
        plan, sample_ticks, stream_sha = _capture(
            root.get("capture"), timing, dict(selection)
        )
        files = require_body_sway_runtime_capture_inventory(
            root.get("artifacts"), capture_bytes
        )
        cases = _cases(root.get("cases"), plan["cases"], files)
        if source["capture_plan_sha256"] != plan["capture_plan_sha256"] \
                or stream_sha != body_sway_runtime_capture_case_stream_sha256(cases):
            raise BodySwayRuntimeCaptureValidationError(
                "Runtime capture source or case-stream seal is inconsistent"
            )
        _aggregate(root, cases, files)
        encoded = json.dumps(
            root, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_CAPTURE_DOCUMENT_BYTES:
            raise BodySwayRuntimeCaptureValidationError(
                "Runtime capture manifest exceeds its byte limit"
            )
    except BodySwayRuntimeCaptureValidationError:
        raise
    except (
        BodySwayRuntimeCaptureInventoryError, KeyError, OverflowError,
        RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureValidationError(
            f"Body-sway runtime capture validation failed: {exc}"
        ) from exc


def body_sway_runtime_capture_sha256(
    document: Mapping[str, Any], capture_bytes: Mapping[str, bytes],
) -> str:
    """Return the manifest identity only after complete detached validation."""

    require_body_sway_runtime_capture(document, capture_bytes)
    return canonical_sha256(document)


def _source(value: Any) -> Mapping[str, Any]:
    row = _object(value, "source")
    _exact(row, _SOURCE_FIELDS, "source")
    for field in _SOURCE_FIELDS - {"upstream"}:
        digest_value(row.get(field), field)
    upstream = _object(row.get("upstream"), "upstream source")
    body_report = upstream.get("body_sway_probe_report_sha256")
    digest_value(body_report, "body_sway_probe_report_sha256")
    probe_source = dict(upstream)
    probe_source.pop("body_sway_probe_report_sha256", None)
    require_body_sway_source(probe_source)
    return row


def _capture(value, timing, selection):
    row = _object(value, "capture")
    _exact(row, {"plan", "sample_ticks", "case_stream_sha256"}, "capture")
    duration = timing["duration_ticks"]
    ticks = require_body_sway_capture_sample_ticks(
        row.get("sample_ticks"), duration
    )
    plan = _object(row.get("plan"), "capture plan")
    require_preview_capture_plan(
        plan, duration=duration,
        ticks_per_second=timing["ticks_per_second"],
        selection=selection, sample_ticks=list(ticks),
    )
    digest_value(row.get("case_stream_sha256"), "case stream SHA-256")
    return plan, ticks, row["case_stream_sha256"]


def _cases(value, plan_cases, files):
    if not isinstance(value, list) or len(value) != len(plan_cases) \
            or len(value) != len(files):
        raise BodySwayRuntimeCaptureValidationError(
            "Runtime capture case count differs from its plan"
        )
    result = []
    for row, planned, artifact in zip(value, plan_cases, files, strict=True):
        item = _object(row, "case")
        _exact(item, _CASE_FIELDS, "case")
        expected = {
            "case_id": planned["case_id"],
            "animation": planned["animation"],
            "tick": planned["tick"],
            "time_seconds": planned["time_seconds"],
            "image_path": artifact["path"],
            "png_sha256": artifact["sha256"],
        }
        if dict(item) != expected or artifact["case_id"] != planned["case_id"]:
            raise BodySwayRuntimeCaptureValidationError(
                "Runtime capture case differs from its plan or artifact"
            )
        result.append(expected)
    return result


def _browser(value: Any) -> None:
    row = _object(value, "browser")
    _exact(row, {
        "family", "reported_version", "version_output_sha256",
        "executable_sha256", "executable_size", "identity_scope",
    }, "browser")
    if row.get("identity_scope") \
            != "launcher-executable-and-reported-version" \
            or type(row.get("executable_size")) is not int \
            or not 1 <= row["executable_size"] <= MAX_EXECUTABLE_BYTES:
        raise BodySwayRuntimeCaptureValidationError(
            "Runtime capture browser identity is invalid"
        )
    try:
        expected_version_sha = browser_version_identity_sha256(
            row.get("family"), row.get("reported_version")
        )
    except BrowserVersionIdentityError as exc:
        raise BodySwayRuntimeCaptureValidationError(
            "Runtime capture browser identity is invalid"
        ) from exc
    digest_value(
        row.get("version_output_sha256"), "browser version output SHA-256"
    )
    if row["version_output_sha256"] != expected_version_sha:
        raise BodySwayRuntimeCaptureValidationError(
            "Runtime capture browser version identity SHA-256 is inconsistent"
        )
    digest_value(row.get("executable_sha256"), "browser executable SHA-256")


def _aggregate(root, cases, files) -> None:
    if root.get("status") != "captured_unreviewed" \
            or root.get("release_gate") != CAPTURE_RELEASE_GATE:
        raise BodySwayRuntimeCaptureValidationError(
            "Runtime capture status must remain unreviewed and blocked"
        )
    pair_count = (len(cases) - 1) // 2
    expected = {
        "case_count": len(cases), "setup_case_count": 1,
        "base_case_count": pair_count, "combined_case_count": pair_count,
        "runtime_error_count": 0,
        "png_total_bytes": sum(row["size_bytes"] for row in files),
    }
    summary = _object(root.get("summary"), "summary")
    _exact(summary, set(expected), "summary")
    if dict(summary) != expected:
        raise BodySwayRuntimeCaptureValidationError(
            "Runtime capture summary is inconsistent"
        )


def body_sway_runtime_capture_case_stream_sha256(cases) -> str:
    """Seal the complete ordered case-to-PNG stream."""

    return canonical_sha256({
        "domain": CASE_STREAM_DIGEST_DOMAIN,
        "cases": list(cases),
    })


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BodySwayRuntimeCaptureValidationError(
            f"Runtime capture {label} must be an object"
        )
    return value


def _exact(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise BodySwayRuntimeCaptureValidationError(
            f"Runtime capture {label} fields are invalid"
        )


def _fixed(value: Any, expected: Mapping[str, Any], label: str) -> None:
    row = _object(value, label)
    if canonical_sha256(row) != canonical_sha256(expected):
        raise BodySwayRuntimeCaptureValidationError(
            f"Runtime capture {label} profile is unsupported"
        )
