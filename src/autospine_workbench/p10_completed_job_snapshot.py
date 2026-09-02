"""Verified, path-free closure for one completed P10 capture job."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .body_sway_visual_review_address_v2 import ExactVisualReviewAddressV2
from .p10_capture_job_contract import (
    P10CaptureJobContractError, P10CaptureJobEvent,
    P10CaptureJobRequest, require_p10_capture_job_transition,
)
from .p10_capture_job_store import P10CaptureJobSnapshot


class P10CompletedJobSnapshotError(ValueError):
    """Raised when a public job snapshot is not a closed completed chain."""


@dataclass(frozen=True, slots=True)
class VerifiedCompletedP10CaptureJob:
    """Exact request and event-chain proof retained outside public receipts."""

    _request: P10CaptureJobRequest = field(repr=False)
    _events: tuple[P10CaptureJobEvent, ...] = field(repr=False)

    @property
    def job_id(self) -> str:
        return self._request.job_id

    @property
    def package_id(self) -> str:
        return self._request.document["package_id"]

    @property
    def terminal_event_sha256(self) -> str:
        return self._events[-1].event_sha

    @property
    def terminal_sequence(self) -> int:
        return self._events[-1].document["sequence"]

    @property
    def address(self) -> ExactVisualReviewAddressV2:
        row = self._events[-1].document["addresses"]
        return ExactVisualReviewAddressV2(
            row["project"], row["preview"],
            row["execution_bundle"], row["artifact"],
        )

    def public_snapshot(self) -> dict[str, Any]:
        return P10CaptureJobSnapshot(
            self._request, self._events,
        ).public_document()


def verified_completed_p10_capture_job(
    document: Mapping[str, Any], expected_job_id: str,
) -> VerifiedCompletedP10CaptureJob:
    """Rebuild and compare every request/event/hash/state snapshot field."""

    try:
        if type(document) is not dict or type(expected_job_id) is not str:
            raise P10CompletedJobSnapshotError(
                "Completed capture job snapshot representation is invalid"
            )
        public_request = document.get("request")
        if type(public_request) is not dict \
                or public_request.get("job_id") != expected_job_id:
            raise P10CompletedJobSnapshotError(
                "Completed capture job request identity differs"
            )
        request = P10CaptureJobRequest.from_document({
            key: value for key, value in public_request.items()
            if key != "job_id"
        })
        if request.job_id != expected_job_id:
            raise P10CompletedJobSnapshotError(
                "Completed capture job request hash differs"
            )
        public_events = document.get("events")
        if type(public_events) is not list \
                or not 1 <= len(public_events) <= 10_000:
            raise P10CompletedJobSnapshotError(
                "Completed capture job event inventory is invalid"
            )
        events = _events(public_events, expected_job_id)
        value = VerifiedCompletedP10CaptureJob(request, events)
        require_verified_completed_p10_capture_job(value)
        if document != value.public_snapshot():
            raise P10CompletedJobSnapshotError(
                "Completed capture job snapshot fields differ from its chain"
            )
        return value
    except P10CompletedJobSnapshotError:
        raise
    except (KeyError, P10CaptureJobContractError, TypeError, ValueError) as exc:
        raise P10CompletedJobSnapshotError(
            "Completed capture job snapshot is invalid"
        ) from exc


def require_verified_completed_p10_capture_job(
    value: VerifiedCompletedP10CaptureJob,
) -> VerifiedCompletedP10CaptureJob:
    """Recheck a process-local closure before it grants compiler evidence."""

    try:
        if type(value) is not VerifiedCompletedP10CaptureJob \
                or type(value._request) is not P10CaptureJobRequest \
                or type(value._events) is not tuple \
                or not 1 <= len(value._events) <= 10_000:
            raise P10CompletedJobSnapshotError(
                "Completed capture job proof representation is invalid"
            )
        previous = None
        for event in value._events:
            if type(event) is not P10CaptureJobEvent \
                    or event.document["job_id"] != value.job_id:
                raise P10CompletedJobSnapshotError(
                    "Completed capture job event identity differs"
                )
            require_p10_capture_job_transition(previous, event)
            previous = event
        head = value._events[-1].document
        if head["status"] != "completed" \
                or head["addresses"] is None:
            raise P10CompletedJobSnapshotError(
                "Capture job proof is not a completed terminal chain"
            )
        value.address
        return value
    except P10CompletedJobSnapshotError:
        raise
    except (KeyError, P10CaptureJobContractError, TypeError, ValueError) as exc:
        raise P10CompletedJobSnapshotError(
            "Completed capture job proof is invalid"
        ) from exc


def _events(rows, job_id):
    result = []
    previous = None
    for row in rows:
        if type(row) is not dict or set(row) != {
            "event_sha", "format", "format_version", "job_id", "sequence",
            "status", "previous_event_sha", "progress", "addresses",
            "failure_code",
        }:
            raise P10CompletedJobSnapshotError(
                "Completed capture job public event shape is invalid"
            )
        event = P10CaptureJobEvent.from_document({
            key: value for key, value in row.items() if key != "event_sha"
        })
        if row["event_sha"] != event.event_sha \
                or event.document["job_id"] != job_id:
            raise P10CompletedJobSnapshotError(
                "Completed capture job public event hash differs"
            )
        require_p10_capture_job_transition(previous, event)
        result.append(event)
        previous = event
    return tuple(result)


__all__ = [
    "P10CompletedJobSnapshotError", "VerifiedCompletedP10CaptureJob",
    "require_verified_completed_p10_capture_job",
    "verified_completed_p10_capture_job",
]
