"""Strict scalar and success-trace provenance for P10.7a v2 candidates."""

from __future__ import annotations

import re

from .manifest_artifacts import require_safe_token
from .p10_spine42_v3_job_contract_v2 import EVENT_FORMAT, REQUEST_FORMAT
from .p10_spine42_v3_job_v2 import P10Spine42V3JobSnapshotV2

_SHA = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_SHAS = (
    "job_id", "safety_run_id", "dynamic_run_id", "motion_run_id",
    "motion_instance_v3_sha256", "motion_instance_v3_bundle_sha256",
)
_REQUEST_FIELDS = {
    "format", "format_version", *_REQUEST_SHAS, "project_id", "attempt",
    "previous_run_id",
}
_EVENT_FIELDS = {
    "format", "format_version", "run_id", "sequence",
    "previous_event_sha256", "status", "stage", "progress",
    "failure_code", "result", "event_sha256",
}
_SUCCESS_TRACE = (
    ("queued", "queued", 0, 1),
    ("running", "exact_motion_instance", 0, 1),
    ("running", "source_adapter", 0, 1),
    ("running", "spine_adapter", 0, 1),
    ("running", "publication", 1, 1),
    ("running", "parent_exact_readback", 0, 1),
    ("completed", "completed", 1, 1),
)


class P10Spine42V3CompletionProvenanceV2Error(RuntimeError):
    """Raised when an old permissive journal is not strict provenance."""


def require_strict_p10_spine42_v3_row_v2(row):
    """Compensate for permissive scalar checks in the historical loader."""

    if type(row) is not P10Spine42V3JobSnapshotV2 \
            or type(row.request) is not dict or type(row.events) is not tuple:
        _fail("P10.7a v2 row type is invalid")
    request = row.request
    if set(request) != _REQUEST_FIELDS \
            or type(request.get("format")) is not str \
            or request["format"] != REQUEST_FORMAT \
            or type(request.get("format_version")) is not int \
            or request["format_version"] != 2:
        _fail("P10.7a v2 request scalar types are invalid")
    for key in _REQUEST_SHAS:
        _sha(request.get(key))
    attempt, previous = request.get("attempt"), request.get("previous_run_id")
    if type(attempt) is not int or not 1 <= attempt <= 10_000 \
            or (attempt == 1) != (previous is None):
        _fail("P10.7a v2 request attempt is invalid")
    if previous is not None:
        _sha(previous)
    if type(request.get("project_id")) is not str:
        _fail("P10.7a v2 request project is invalid")
    try:
        require_safe_token(request["project_id"], "P10.7a v2 project")
    except Exception as exc:
        raise P10Spine42V3CompletionProvenanceV2Error(
            "P10.7a v2 request project is invalid") from exc
    previous_event = None
    for position, event in enumerate(row.events, 1):
        _require_strict_event(
            event, row.run_id, position, previous_event)
        previous_event = event["event_sha256"]
    return row


def require_exact_p10_spine42_v3_success_v2(row):
    """Require the seven events emitted by the real P10.7a v2 manager."""

    require_strict_p10_spine42_v3_row_v2(row)
    if row.status != "completed" or len(row.events) != len(_SUCCESS_TRACE):
        _fail("P10.7a v2 completion trace is incomplete")
    for index, (event, expected) in enumerate(
        zip(row.events, _SUCCESS_TRACE), 1
    ):
        status, stage, current, total = expected
        if event["status"] != status or event["stage"] != stage \
                or event["progress"] != {
                    "current": current, "total": total,
                } or event["failure_code"] is not None \
                or (event["result"] is not None) != (
                    index == len(_SUCCESS_TRACE)
                ):
            _fail("P10.7a v2 completion trace differs from the manager")
    return row


def _require_strict_event(event, run_id, sequence, expected_previous):
    if type(event) is not dict or set(event) != _EVENT_FIELDS \
            or type(event.get("format")) is not str \
            or event["format"] != EVENT_FORMAT \
            or type(event.get("format_version")) is not int \
            or event["format_version"] != 2 \
            or type(event.get("sequence")) is not int \
            or event["sequence"] != sequence:
        _fail("P10.7a v2 event scalar types are invalid")
    _sha(event.get("run_id")); _sha(event.get("event_sha256"))
    if event["run_id"] != run_id:
        _fail("P10.7a v2 event run address differs")
    previous = event.get("previous_event_sha256")
    if previous != expected_previous:
        _fail("P10.7a v2 event predecessor differs")
    if previous is not None:
        _sha(previous)
    progress = event.get("progress")
    if type(progress) is not dict or set(progress) != {"current", "total"} \
            or type(progress.get("current")) is not int \
            or type(progress.get("total")) is not int \
            or not 0 <= progress["current"] <= progress["total"] \
            or not 1 <= progress["total"] <= 100:
        _fail("P10.7a v2 event progress scalar types are invalid")
    for key in ("status", "stage"):
        if type(event.get(key)) is not str:
            _fail("P10.7a v2 event state scalar types are invalid")
    failure, result = event.get("failure_code"), event.get("result")
    if failure is not None and type(failure) is not str \
            or result is not None and type(result) is not dict:
        _fail("P10.7a v2 event payload scalar types are invalid")


def _sha(value):
    if type(value) is not str or _SHA.fullmatch(value) is None:
        _fail("P10.7a v2 SHA-256 scalar type is invalid")


def _fail(message):
    raise P10Spine42V3CompletionProvenanceV2Error(message)


__all__ = [
    "P10Spine42V3CompletionProvenanceV2Error",
    "require_exact_p10_spine42_v3_success_v2",
    "require_strict_p10_spine42_v3_row_v2",
]
