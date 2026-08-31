"""Path-free failure summaries derived from immutable P10 job events."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .p10_capture_job_contract import (
    P10CaptureJobEvent, RETRYABLE_STATUSES,
)


FORMAT = "autospine-p10-capture-failure-diagnostic"
FORMAT_VERSION = 1
_FAILURE_STATUSES = RETRYABLE_STATUSES | {"failed_terminal"}

_CATEGORY_BY_CODE = {
    "input_head_changed": "input_identity",
    "input_replay_failed": "input_identity",
    "runtime_environment_unavailable": "runtime_environment",
    "process_restart": "orchestration",
    "manager_closed": "orchestration",
    "runtime_browser_identity_changed": "browser_identity",
    "runtime_browser_case_failed": "browser_execution",
    "runtime_capture_server_failed": "capture_transport",
    "runtime_case_evidence_failed": "capture_evidence",
    "runtime_evidence_validation_failed": "evidence_validation",
    "runtime_evidence_publication_failed": "evidence_publication",
    "runtime_package_changed": "runtime_environment",
    "runtime_progress_invalid": "orchestration",
    "runtime_execution_io_failed": "runtime_execution",
    "runtime_capture_failed": "runtime_execution",
}


def capture_failure_diagnostic(
    events: Sequence[P10CaptureJobEvent],
) -> dict[str, Any] | None:
    """Summarize a failed chain without mutating or exposing stored details."""

    if not events:
        return None
    head = _document(events[-1])
    if head["status"] not in _FAILURE_STATUSES:
        return None
    predecessor = _document(events[-2]) if len(events) > 1 else None
    progress = _latest_progress(events[:-1])
    completed = progress["current"] if progress else None
    total = progress["total"] if progress else None
    next_ordinal = completed + 1 if progress and completed < total else None
    code = head["failure_code"]
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "stage": _stage(predecessor, progress),
        "category": _CATEGORY_BY_CODE.get(code, "unclassified"),
        "completed_case_count": completed,
        "total_case_count": total,
        "next_incomplete_case_ordinal": next_ordinal,
    }


def _latest_progress(events):
    for event in reversed(events):
        progress = _document(event).get("progress")
        if progress is not None:
            return progress
    return None


def _stage(predecessor, progress):
    status = predecessor["status"] if predecessor else None
    if status == "queued":
        return "input_replay"
    if status == "exact_replay":
        return "preview_compilation"
    if status == "preview_compiled":
        return "environment_verification"
    if status == "runtime_verified":
        return "runtime_launch"
    if status == "capturing":
        if progress and progress["current"] == progress["total"]:
            return "capture_compilation"
        return "case_capture"
    if status == "sealing":
        return "evidence_publication"
    return "unknown"


def _document(event):
    if type(event) is not P10CaptureJobEvent:
        raise TypeError("Capture diagnostic requires exact job events")
    return event.document


__all__ = [
    "FORMAT", "FORMAT_VERSION", "capture_failure_diagnostic",
]
