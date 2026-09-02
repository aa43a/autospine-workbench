"""Bounded field and state validation for P10.4b v2 async jobs."""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any

from .manifest_artifacts import require_safe_token, require_sha256
from .resolved_project import canonical_sha256


REQUEST_FORMAT = "autospine-p10-safety-analysis-request-v2"
EVENT_FORMAT = "autospine-p10-safety-analysis-event-v2"
EVENT_DOMAIN = "autospine-p10-safety-analysis-event/v2"
ACTIVE = frozenset({"queued", "running"})
TERMINAL = frozenset({"completed", "failed_retryable", "failed_terminal"})
STAGES = frozenset({
    "queued", "review_admission", "exact_source", "amplitude_probes",
    "continuous_segments", "continuous_boxes", "continuous_validation",
    "current_head_recheck",
    "sealing", "completed", "failed",
})
_REQUEST_FIELDS = {
    "format", "format_version", "job_id", "package_id",
    "terminal_event_sha256", "terminal_sequence", "capture_address",
    "attempt", "previous_run_id", "analyzers_sha256",
}
_ADDRESS_FIELDS = {
    "project_id", "temporary_preview_v2_sha256",
    "runtime_execution_bundle_sha256", "capture_artifact_set_sha256",
}
_EVENT_FIELDS = {
    "format", "format_version", "run_id", "sequence",
    "previous_event_sha256", "event_sha256", "status", "stage",
    "progress", "failure_code", "result",
}
_RESULT_FIELDS = {
    "authority_scope",
    "admission_sha256", "visual_candidate_sha256", "visual_revision",
    "visual_decision_sha256", "amplitude_sha256", "continuous_sha256",
    "amplitude_size_bytes", "continuous_size_bytes",
}
_FAILURE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class P10SafetyAnalysisJobValidationV2Error(ValueError):
    """Raised when an async job document is malformed or overclaims."""


def require_request_document(document) -> dict[str, Any]:
    value = _object_copy(document, "Safety analysis request")
    if set(value) != _REQUEST_FIELDS \
            or value.get("format") != REQUEST_FORMAT \
            or value.get("format_version") != 2:
        raise P10SafetyAnalysisJobValidationV2Error(
            "Safety analysis request fields are unsupported"
        )
    for name in ("job_id", "package_id", "terminal_event_sha256",
                 "analyzers_sha256"):
        require_sha256(value.get(name), name)
    _capture_address(value.get("capture_address"))
    attempt, sequence = value.get("attempt"), value.get("terminal_sequence")
    if type(attempt) is not int or not 1 <= attempt <= 10_000 \
            or type(sequence) is not int or not 1 <= sequence <= 10_000:
        raise P10SafetyAnalysisJobValidationV2Error(
            "Safety analysis request sequence is invalid"
        )
    previous = value.get("previous_run_id")
    if attempt == 1 and previous is not None:
        raise P10SafetyAnalysisJobValidationV2Error(
            "Initial safety analysis run cannot have a predecessor"
        )
    if attempt > 1:
        require_sha256(previous, "previous run")
    return value


def require_event_document(document) -> dict[str, Any]:
    value = _object_copy(document, "Safety analysis event")
    if set(value) != _EVENT_FIELDS or value.get("format") != EVENT_FORMAT \
            or value.get("format_version") != 2:
        raise P10SafetyAnalysisJobValidationV2Error(
            "Safety analysis event fields are unsupported"
        )
    require_sha256(value.get("run_id"), "run id")
    require_sha256(value.get("event_sha256"), "event")
    if value.get("previous_event_sha256") is not None:
        require_sha256(value["previous_event_sha256"], "previous event")
    if type(value.get("sequence")) is not int \
            or not 1 <= value["sequence"] <= 10_000 \
            or value.get("status") not in ACTIVE | TERMINAL \
            or value.get("stage") not in STAGES:
        raise P10SafetyAnalysisJobValidationV2Error(
            "Safety analysis event state is invalid"
        )
    _progress(value.get("progress"))
    _state_payload(value)
    payload = {key: item for key, item in value.items()
               if key != "event_sha256"}
    expected = canonical_sha256({"domain": EVENT_DOMAIN, "event": payload})
    if value["event_sha256"] != expected:
        raise P10SafetyAnalysisJobValidationV2Error(
            "Safety analysis event digest differs"
        )
    return value


def require_result_address(document) -> dict[str, Any]:
    """Return a detached result address after its full field validation."""

    value = _object_copy(document, "Safety analysis result address")
    _result(value)
    return value


def _state_payload(row) -> None:
    status, stage = row["status"], row["stage"]
    bad_stage = status == "queued" and stage != "queued" \
        or status == "running" and stage in {"queued", "completed", "failed"} \
        or status == "completed" and stage != "completed" \
        or status.startswith("failed_") and stage != "failed"
    if bad_stage:
        raise P10SafetyAnalysisJobValidationV2Error(
            "Safety analysis status and stage differ"
        )
    failure, result = row.get("failure_code"), row.get("result")
    if status.startswith("failed_"):
        if type(failure) is not str or _FAILURE.fullmatch(failure) is None \
                or result is not None:
            raise P10SafetyAnalysisJobValidationV2Error(
                "Safety analysis failure payload is invalid"
            )
    elif failure is not None:
        raise P10SafetyAnalysisJobValidationV2Error(
            "Only failed safety analysis events have a failure code"
        )
    if status == "completed":
        _result(result)
        if row["progress"] != {"current": 1, "total": 1}:
            raise P10SafetyAnalysisJobValidationV2Error(
                "Completed safety analysis progress is invalid"
            )
    elif result is not None:
        raise P10SafetyAnalysisJobValidationV2Error(
            "Only completed safety analysis events have a result"
        )


def _capture_address(value) -> None:
    if not isinstance(value, Mapping) or set(value) != _ADDRESS_FIELDS:
        raise P10SafetyAnalysisJobValidationV2Error(
            "Safety analysis capture address is invalid"
        )
    require_safe_token(value.get("project_id"), "capture project")
    for name in _ADDRESS_FIELDS - {"project_id"}:
        require_sha256(value.get(name), name)


def _result(value) -> None:
    if not isinstance(value, Mapping) or set(value) != _RESULT_FIELDS:
        raise P10SafetyAnalysisJobValidationV2Error(
            "Safety analysis result address is invalid"
        )
    excluded = {"visual_revision", "amplitude_size_bytes",
                "continuous_size_bytes", "authority_scope"}
    if value.get("authority_scope") != "compile_time_snapshot":
        raise P10SafetyAnalysisJobValidationV2Error(
            "Safety analysis result authority scope is invalid"
        )
    for name in _RESULT_FIELDS - excluded:
        require_sha256(value.get(name), name)
    revision = value.get("visual_revision")
    sizes = value.get("amplitude_size_bytes"), value.get("continuous_size_bytes")
    if type(revision) is not int or not 1 <= revision <= 64 \
            or any(type(size) is not int or not 1 <= size <= 160 * 1024 * 1024
                   for size in sizes):
        raise P10SafetyAnalysisJobValidationV2Error(
            "Safety analysis result metadata is invalid"
        )


def _progress(value) -> None:
    if not isinstance(value, Mapping) or set(value) != {"current", "total"} \
            or type(value["current"]) is not int \
            or type(value["total"]) is not int \
            or not 0 <= value["current"] <= value["total"] \
            or not 1 <= value["total"] <= 1_000_000:
        raise P10SafetyAnalysisJobValidationV2Error(
            "Safety analysis event progress is invalid"
        )


def _object_copy(value: Any, label: str):
    raw = _canonical(value).encode("utf-8")
    if len(raw) > 128 * 1024 or not isinstance(value, Mapping):
        raise P10SafetyAnalysisJobValidationV2Error(f"{label} is invalid")
    copied = json.loads(raw)
    if not isinstance(copied, dict):
        raise P10SafetyAnalysisJobValidationV2Error(f"{label} is invalid")
    return copied


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


__all__ = [
    "ACTIVE", "EVENT_DOMAIN", "EVENT_FORMAT", "REQUEST_FORMAT", "STAGES",
    "TERMINAL", "P10SafetyAnalysisJobValidationV2Error",
    "require_event_document", "require_request_document",
    "require_result_address",
]
