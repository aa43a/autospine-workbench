"""Canonical, path-free contract for one package-centric P10 capture job."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import re
from typing import Any

from .resolved_project import canonical_sha256


REQUEST_FORMAT = "autospine-p10-capture-job-request"
EVENT_FORMAT = "autospine-p10-capture-job-event"
FORMAT_VERSION = 1
JOB_ID_DOMAIN = "autospine-p10-capture-job-id/v1"
EVENT_ID_DOMAIN = "autospine-p10-capture-job-event-id/v1"
ACTIVE_STATUSES = frozenset({
    "queued", "exact_replay", "preview_compiled", "runtime_verified",
    "capturing", "sealing",
})
RETRYABLE_STATUSES = frozenset({
    "failed_retryable", "interrupted_retryable",
})
TERMINAL_STATUSES = frozenset({"completed", "failed_terminal"})
STATUSES = ACTIVE_STATUSES | RETRYABLE_STATUSES | TERMINAL_STATUSES

_REQUEST_FIELDS = {
    "package_id", "client_request_id", "expected_p10_1",
    "expected_framing", "explicit_runtime_license_confirmation",
    "explicit_run_confirmation",
}
_EXPECTED_FIELDS = {"candidate_sha256", "decision_sha256", "revision"}
_EVENT_FIELDS = {
    "format", "format_version", "job_id", "sequence", "status",
    "previous_event_sha", "progress", "addresses", "failure_code",
}
_ADDRESS_FIELDS = {"project", "preview", "execution_bundle", "artifact"}
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_REVISION = 1_000_000_000


class P10CaptureJobContractError(ValueError):
    """Raised when a request, event, or transition is not exact."""


@dataclass(frozen=True, slots=True)
class P10CaptureJobRequest:
    """Canonical request whose address is independent of mapping order."""

    _canonical_json: str = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "P10CaptureJobRequest":
        row = _object(payload, "request")
        _exact(row, _REQUEST_FIELDS, "request")
        document = {
            "format": REQUEST_FORMAT, "format_version": FORMAT_VERSION,
            **_copy(row),
        }
        _require_request_document(document)
        return cls(_canonical(document))

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "P10CaptureJobRequest":
        row = _object(document, "stored request")
        _require_request_document(row)
        return cls(_canonical(row))

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def job_id(self) -> str:
        return canonical_sha256({
            "domain": JOB_ID_DOMAIN, "request": self.document,
        })

    def public_document(self) -> dict[str, Any]:
        return {"job_id": self.job_id, **self.document}


@dataclass(frozen=True, slots=True)
class P10CaptureJobEvent:
    """One immutable event retaining no clock, process, or filesystem path."""

    _canonical_json: str = field(repr=False)

    @classmethod
    def build(
        cls, job_id: str, sequence: int, status: str,
        previous_event_sha: str | None, *, current: int | None = None,
        total: int | None = None, addresses: Mapping[str, Any] | None = None,
        failure_code: str | None = None,
    ) -> "P10CaptureJobEvent":
        progress = None if current is None and total is None else {
            "current": current, "total": total,
        }
        document = {
            "format": EVENT_FORMAT, "format_version": FORMAT_VERSION,
            "job_id": job_id, "sequence": sequence, "status": status,
            "previous_event_sha": previous_event_sha,
            "progress": progress, "addresses": _copy(addresses),
            "failure_code": failure_code,
        }
        _require_event_document(document)
        return cls(_canonical(document))

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> "P10CaptureJobEvent":
        row = _object(document, "stored event")
        _require_event_document(row)
        return cls(_canonical(row))

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def event_sha(self) -> str:
        return canonical_sha256({
            "domain": EVENT_ID_DOMAIN, "event": self.document,
        })

    def public_document(self) -> dict[str, Any]:
        return {"event_sha": self.event_sha, **self.document}


def require_p10_capture_job_transition(
    previous: P10CaptureJobEvent | None, event: P10CaptureJobEvent,
) -> None:
    """Require sequence, hash-chain, state-machine, and progress continuity."""

    if type(event) is not P10CaptureJobEvent:
        raise P10CaptureJobContractError("Capture job event type is invalid")
    row = event.document
    if previous is None:
        if row["sequence"] != 1 or row["status"] != "queued" \
                or row["previous_event_sha"] is not None:
            raise P10CaptureJobContractError("First capture job event must be queued")
        return
    if type(previous) is not P10CaptureJobEvent:
        raise P10CaptureJobContractError("Previous capture job event is invalid")
    before = previous.document
    if row["job_id"] != before["job_id"] \
            or row["sequence"] != before["sequence"] + 1 \
            or row["previous_event_sha"] != previous.event_sha:
        raise P10CaptureJobContractError("Capture job event chain is inconsistent")
    allowed = _TRANSITIONS[before["status"]]
    if row["status"] not in allowed:
        raise P10CaptureJobContractError("Capture job status transition is invalid")
    if before["status"] == "capturing":
        old = before["progress"]
        if row["status"] == "capturing" and (
            row["progress"]["total"] != old["total"]
            or row["progress"]["current"] < old["current"]
        ):
            raise P10CaptureJobContractError("Capture progress moved backwards")
        if row["status"] == "sealing" and old["current"] != old["total"]:
            raise P10CaptureJobContractError("Capture cannot seal before completion")


def _require_request_document(row):
    _exact(row, _REQUEST_FIELDS | {"format", "format_version"}, "stored request")
    if row.get("format") != REQUEST_FORMAT \
            or row.get("format_version") != FORMAT_VERSION:
        raise P10CaptureJobContractError("Capture job request format is invalid")
    _sha(row.get("package_id"), "package")
    _token(row.get("client_request_id"), "client request")
    _expected(row.get("expected_p10_1"), "P10.1")
    _expected(row.get("expected_framing"), "capture framing")
    if row.get("explicit_runtime_license_confirmation") is not True \
            or row.get("explicit_run_confirmation") is not True:
        raise P10CaptureJobContractError("Both explicit confirmations are required")


def _require_event_document(row):
    _exact(row, _EVENT_FIELDS, "event")
    if row.get("format") != EVENT_FORMAT \
            or row.get("format_version") != FORMAT_VERSION:
        raise P10CaptureJobContractError("Capture job event format is invalid")
    _sha(row.get("job_id"), "job")
    sequence, status = row.get("sequence"), row.get("status")
    if type(sequence) is not int or not 1 <= sequence <= _MAX_REVISION \
            or type(status) is not str or status not in STATUSES:
        raise P10CaptureJobContractError("Capture job event state is invalid")
    previous = row.get("previous_event_sha")
    if previous is not None:
        _sha(previous, "previous event")
    progress, addresses, failure = (
        row.get("progress"), row.get("addresses"), row.get("failure_code")
    )
    if status == "capturing":
        progress = _object(progress, "capture progress")
        _exact(progress, {"current", "total"}, "capture progress")
        current, total = progress.get("current"), progress.get("total")
        if type(current) is not int or type(total) is not int \
                or total < 1 or not 0 <= current <= total:
            raise P10CaptureJobContractError("Capture progress is invalid")
    elif progress is not None:
        raise P10CaptureJobContractError("Only capturing events have progress")
    if status == "completed":
        _addresses(addresses)
    elif addresses is not None:
        raise P10CaptureJobContractError("Only completed events have addresses")
    if status in RETRYABLE_STATUSES | {"failed_terminal"}:
        _token(failure, "failure code")
    elif failure is not None:
        raise P10CaptureJobContractError("Only failure events have a failure code")


def _expected(value, label):
    row = _object(value, f"{label} identity")
    _exact(row, _EXPECTED_FIELDS, f"{label} identity")
    _sha(row.get("candidate_sha256"), f"{label} candidate")
    _sha(row.get("decision_sha256"), f"{label} decision")
    revision = row.get("revision")
    if type(revision) is not int or not 1 <= revision <= _MAX_REVISION:
        raise P10CaptureJobContractError(f"{label} revision is invalid")


def _addresses(value):
    row = _object(value, "completed addresses")
    _exact(row, _ADDRESS_FIELDS, "completed addresses")
    _token(row.get("project"), "project address")
    for name in ("preview", "execution_bundle", "artifact"):
        _sha(row.get(name), f"{name} address")


def _object(value, label):
    if not isinstance(value, Mapping):
        raise P10CaptureJobContractError(f"Capture job {label} must be an object")
    return value


def _exact(value, fields, label):
    if set(value) != fields:
        raise P10CaptureJobContractError(f"Capture job {label} fields are invalid")


def _sha(value, label):
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise P10CaptureJobContractError(f"Capture job {label} is not a SHA-256")


def _token(value, label):
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        raise P10CaptureJobContractError(f"Capture job {label} is invalid")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


def _copy(value):
    return None if value is None else json.loads(_canonical(value))


_FAILURES = RETRYABLE_STATUSES | {"failed_terminal"}
_TRANSITIONS = {
    "queued": {"exact_replay"} | _FAILURES,
    "exact_replay": {"preview_compiled"} | _FAILURES,
    "preview_compiled": {"runtime_verified"} | _FAILURES,
    "runtime_verified": {"capturing"} | _FAILURES,
    "capturing": {"capturing", "sealing"} | _FAILURES,
    "sealing": {"completed"} | _FAILURES,
    "failed_retryable": {"queued"},
    "interrupted_retryable": {"queued"},
    "completed": set(), "failed_terminal": set(),
}


__all__ = [
    "ACTIVE_STATUSES", "EVENT_FORMAT", "FORMAT_VERSION",
    "P10CaptureJobContractError", "P10CaptureJobEvent",
    "P10CaptureJobRequest", "REQUEST_FORMAT", "RETRYABLE_STATUSES",
    "STATUSES", "TERMINAL_STATUSES", "require_p10_capture_job_transition",
]
