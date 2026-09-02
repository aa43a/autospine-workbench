"""Path-free projections for P10.7b v2 runtime job journals."""

from __future__ import annotations

from dataclasses import dataclass

from .p10_spine42_v3_runtime_job_contract_v2 import (
    TERMINAL, P10Spine42V3RuntimeJobEventV2,
    P10Spine42V3RuntimeJobRequestV2,
)


@dataclass(frozen=True, slots=True)
class P10Spine42V3RuntimeJobSnapshotV2:
    request: P10Spine42V3RuntimeJobRequestV2
    events: tuple[P10Spine42V3RuntimeJobEventV2, ...]

    @property
    def job_id(self):
        return self.request.job_id

    @property
    def head(self):
        return self.events[-1].document if self.events else None

    @property
    def head_event_sha256(self):
        return self.events[-1].event_sha256 if self.events else None

    @property
    def status(self):
        return self.head["status"] if self.head else None

    def public_document(self):
        head = self.head or {}
        return {
            "job_id": self.job_id, "request": self.request.document,
            "status": self.status, "stage": head.get("stage"),
            "progress": head.get("progress"),
            "failure_code": head.get("failure_code"),
            "resume_mode": head.get("resume_mode"),
            "result": head.get("result"), "event_count": len(self.events),
            "head_event_sha256": self.head_event_sha256,
            "terminal": self.status in TERMINAL,
            "runner_execution_authorized": False,
            "events": [event.public_document() for event in self.events],
        }


@dataclass(frozen=True, slots=True)
class P10Spine42V3RuntimeJobRecoveryV2:
    interrupted_job_ids: tuple[str, ...]
    readback_required_job_ids: tuple[str, ...]

    def public_document(self):
        return {
            "interrupted_job_ids": list(self.interrupted_job_ids),
            "readback_required_job_ids": list(self.readback_required_job_ids),
            "runner_execution_authorized": False,
        }


__all__ = [
    "P10Spine42V3RuntimeJobRecoveryV2",
    "P10Spine42V3RuntimeJobSnapshotV2",
]
