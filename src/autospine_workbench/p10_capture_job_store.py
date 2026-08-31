"""Alias-safe append-only store for package-centric P10 capture jobs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
from typing import Any

from .body_sway_visual_review_store_files import (
    BodySwayVisualReviewFilesError, exact_subdirectory,
    publish_named_document, read_named_document,
)
from .p10_capture_job_contract import (
    ACTIVE_STATUSES, P10CaptureJobEvent, P10CaptureJobRequest,
    RETRYABLE_STATUSES, TERMINAL_STATUSES,
    require_p10_capture_job_transition,
)
from .p10_capture_job_diagnostics import capture_failure_diagnostic
from .safe_input_files import strict_json_object
from .spine42_bundle_files import (
    Spine42BundleFilesError, is_alias, require_real_directory,
)

JOB_NAMESPACE = "body-sway-runtime-capture"
MAX_JOBS, MAX_EVENTS = 10_000, 10_000
MAX_REQUEST_BYTES, MAX_EVENT_BYTES = 64 * 1024, 64 * 1024
_SHA = re.compile(r"^[0-9a-f]{64}$")
_EVENT_NAME = re.compile(r"^([0-9]{6})\.json$")

class P10CaptureJobStoreError(RuntimeError):
    """Raised when persisted job state is unsafe or inconsistent."""

class P10CaptureJobConflict(P10CaptureJobStoreError):
    """Raised when an append no longer names the exact event-chain head."""

    def __init__(self, expected: str | None, current: str | None) -> None:
        super().__init__("Capture job event predecessor is stale")
        self.expected_previous_event_sha = expected
        self.current_event_sha = current

@dataclass(frozen=True, slots=True)
class P10CaptureJobSnapshot:
    request: P10CaptureJobRequest
    events: tuple[P10CaptureJobEvent, ...]

    @property
    def job_id(self) -> str:
        return self.request.job_id

    @property
    def head_event_sha(self) -> str | None:
        return self.events[-1].event_sha if self.events else None

    @property
    def status(self) -> str | None:
        return self.events[-1].document["status"] if self.events else None

    def public_document(self) -> dict[str, Any]:
        head = self.events[-1].document if self.events else {}
        return {
            "job_id": self.job_id,
            "request": self.request.public_document(),
            "status": self.status,
            "event_count": len(self.events),
            "head_event_sha": self.head_event_sha,
            "retryable": self.status in RETRYABLE_STATUSES,
            "terminal": self.status in TERMINAL_STATUSES,
            "progress": head.get("progress"),
            "addresses": head.get("addresses"),
            "failure_code": head.get("failure_code"),
            "failure_diagnostic": capture_failure_diagnostic(self.events),
            "events": [event.public_document() for event in self.events],
        }

class P10CaptureJobStore:
    """Persist immutable requests and one linear event chain per job."""

    def __init__(self, state_root: Path) -> None:
        try:
            self.state_root = Path(os.path.abspath(os.fspath(Path(state_root))))
        except (OSError, TypeError, ValueError) as exc:
            raise P10CaptureJobStoreError("Capture state root is invalid") from exc

    def create(self, payload: Mapping[str, Any]) -> P10CaptureJobSnapshot:
        request = P10CaptureJobRequest.from_payload(payload)
        directory = self._job_directory(request.job_id, create=True)
        events = _exact_directory(directory, "events", create=True)
        _publish_once(
            directory / "request.json", request.canonical_bytes,
            staging=directory, maximum=MAX_REQUEST_BYTES,
        )
        snapshot = self._load(directory, request.job_id, events)
        if not snapshot.events:
            snapshot = self.append_event(
                request.job_id, "queued", expected_previous_event_sha=None,
            )
        return snapshot

    def load(self, job_id: str) -> P10CaptureJobSnapshot:
        _require_sha(job_id, "job id")
        directory = self._job_directory(job_id, create=False)
        events = _exact_directory(directory, "events", create=False)
        return self._load(directory, job_id, events)

    def append_event(
        self, job_id: str, status: str, *,
        expected_previous_event_sha: str | None,
        current: int | None = None, total: int | None = None,
        addresses: Mapping[str, Any] | None = None,
        failure_code: str | None = None,
    ) -> P10CaptureJobSnapshot:
        snapshot = self.load(job_id)
        if expected_previous_event_sha != snapshot.head_event_sha:
            if self._is_exact_retry(
                snapshot, status, expected_previous_event_sha,
                current, total, addresses, failure_code,
            ):
                return snapshot
            raise P10CaptureJobConflict(
                expected_previous_event_sha, snapshot.head_event_sha,
            )
        event = P10CaptureJobEvent.build(
            job_id, len(snapshot.events) + 1, status,
            expected_previous_event_sha, current=current, total=total,
            addresses=addresses, failure_code=failure_code,
        )
        previous = snapshot.events[-1] if snapshot.events else None
        require_p10_capture_job_transition(previous, event)
        directory = self._job_directory(job_id, create=False)
        events = _exact_directory(directory, "events", create=False)
        path = events / _event_name(event.document["sequence"])
        try:
            _publish_once(
                path, event.canonical_bytes, staging=directory,
                maximum=MAX_EVENT_BYTES,
            )
        except P10CaptureJobStoreError as exc:
            current_snapshot = self.load(job_id)
            if current_snapshot.head_event_sha != snapshot.head_event_sha:
                raise P10CaptureJobConflict(
                    expected_previous_event_sha,
                    current_snapshot.head_event_sha,
                ) from exc
            raise
        result = self.load(job_id)
        if result.head_event_sha != event.event_sha:
            raise P10CaptureJobStoreError("Capture job event failed exact readback")
        return result

    def recover_interrupted_jobs(self) -> tuple[str, ...]:
        """Settle jobs active before this call; never resume their work."""

        identifiers = self._job_ids()
        recovered = []
        for job_id in identifiers:
            snapshot = self.load(job_id)
            if not snapshot.events:
                snapshot = self.append_event(
                    job_id, "queued", expected_previous_event_sha=None,
                )
            if snapshot.status not in ACTIVE_STATUSES:
                continue
            try:
                self.append_event(
                    job_id, "interrupted_retryable",
                    expected_previous_event_sha=snapshot.head_event_sha,
                    failure_code="process_restart",
                )
                recovered.append(job_id)
            except P10CaptureJobConflict:
                current = self.load(job_id)
                if current.status in ACTIVE_STATUSES:
                    raise
        return tuple(recovered)

    def _load(self, directory, job_id, events) -> P10CaptureJobSnapshot:
        request_raw = _read(directory / "request.json", MAX_REQUEST_BYTES)
        request = P10CaptureJobRequest.from_document(
            strict_json_object(request_raw, "P10 capture job request")
        )
        if request.canonical_bytes != request_raw or request.job_id != job_id:
            raise P10CaptureJobStoreError("Capture job request address is invalid")
        chain: list[P10CaptureJobEvent] = []
        for sequence, path in _event_inventory(events):
            raw = _read(path, MAX_EVENT_BYTES)
            event = P10CaptureJobEvent.from_document(
                strict_json_object(raw, "P10 capture job event")
            )
            if event.canonical_bytes != raw \
                    or event.document["job_id"] != job_id \
                    or event.document["sequence"] != sequence:
                raise P10CaptureJobStoreError("Capture job event slot is invalid")
            require_p10_capture_job_transition(chain[-1] if chain else None, event)
            chain.append(event)
        return P10CaptureJobSnapshot(request, tuple(chain))

    def _is_exact_retry(
        self, snapshot, status, previous, current, total, addresses, failure,
    ) -> bool:
        if not snapshot.events:
            return False
        candidate = P10CaptureJobEvent.build(
            snapshot.job_id, len(snapshot.events), status, previous,
            current=current, total=total, addresses=addresses,
            failure_code=failure,
        )
        return candidate.canonical_bytes == snapshot.events[-1].canonical_bytes

    def _job_directory(self, job_id: str, *, create: bool) -> Path:
        _require_sha(job_id, "job id")
        namespace = self._namespace(create=create)
        return _exact_directory(namespace, job_id, create=create)

    def _namespace(self, *, create: bool) -> Path:
        try:
            root = require_real_directory(
                self.state_root, "P10 capture state root",
            )
        except Spine42BundleFilesError as exc:
            raise P10CaptureJobStoreError("Capture state root is unsafe") from exc
        jobs = _exact_directory(root, "jobs", create=create)
        return _exact_directory(jobs, JOB_NAMESPACE, create=create)

    def _job_ids(self) -> tuple[str, ...]:
        namespace = self._namespace(create=True)
        result = []
        try:
            children = list(namespace.iterdir())
            if len(children) > MAX_JOBS:
                raise P10CaptureJobStoreError("Capture job inventory is excessive")
            for child in children:
                if _SHA.fullmatch(child.name) is None or is_alias(child) \
                        or not stat.S_ISDIR(child.lstat().st_mode):
                    raise P10CaptureJobStoreError("Capture job inventory is unsafe")
                result.append(child.name)
        except OSError as exc:
            raise P10CaptureJobStoreError("Capture jobs cannot be enumerated") from exc
        return tuple(sorted(result))

def _event_inventory(directory):
    try:
        children = list(directory.iterdir())
        if len(children) > MAX_EVENTS:
            raise P10CaptureJobStoreError("Capture job event history is excessive")
        found = {}
        for child in children:
            match = _EVENT_NAME.fullmatch(child.name)
            if match is None or is_alias(child) \
                    or not stat.S_ISREG(child.lstat().st_mode):
                raise P10CaptureJobStoreError("Capture job event inventory is unsafe")
            sequence = int(match.group(1))
            if sequence in found or _event_name(sequence) != child.name:
                raise P10CaptureJobStoreError("Capture job event slot is aliased")
            found[sequence] = child
        expected = list(range(1, len(found) + 1))
        if sorted(found) != expected:
            raise P10CaptureJobStoreError("Capture job events are not contiguous")
        return tuple((number, found[number]) for number in expected)
    except P10CaptureJobStoreError:
        raise
    except OSError as exc:
        raise P10CaptureJobStoreError("Capture job events cannot be read") from exc

def _publish_once(path, payload, *, staging, maximum):
    if type(payload) is not bytes or not 0 < len(payload) <= maximum:
        raise P10CaptureJobStoreError("Capture job payload is unbounded")
    try:
        publish_named_document(
            path.parent, path.name, payload, staging_parent=staging,
        )
    except (BodySwayVisualReviewFilesError, OSError) as exc:
        raise P10CaptureJobStoreError("Capture job file cannot be published") from exc

def _read(path, maximum):
    try:
        payload = read_named_document(path.parent, path.name)
        if len(payload) > maximum:
            raise P10CaptureJobStoreError("Capture job document is excessive")
        return payload
    except (BodySwayVisualReviewFilesError, OSError, ValueError) as exc:
        raise P10CaptureJobStoreError("Capture job document is unsafe") from exc

def _exact_directory(parent, name, *, create):
    try:
        return exact_subdirectory(parent, name, create=create)
    except BodySwayVisualReviewFilesError as exc:
        raise P10CaptureJobStoreError("Capture job directory is unsafe") from exc

def _event_name(sequence):
    if type(sequence) is not int or not 1 <= sequence <= MAX_EVENTS:
        raise P10CaptureJobStoreError("Capture job event sequence is invalid")
    return f"{sequence:06d}.json"

def _require_sha(value, label):
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise P10CaptureJobStoreError(f"Capture {label} is invalid")
