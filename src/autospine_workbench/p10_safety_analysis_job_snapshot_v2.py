"""Immutable in-memory snapshot for one P10.4b v2 run."""

from __future__ import annotations

from dataclasses import dataclass

from .p10_safety_analysis_job_contract_v2 import (
    TERMINAL,
    P10SafetyAnalysisRunEventV2,
    P10SafetyAnalysisRunRequestV2,
)


@dataclass(frozen=True, slots=True)
class P10SafetyAnalysisJobSnapshotV2:
    request: P10SafetyAnalysisRunRequestV2
    events: tuple[P10SafetyAnalysisRunEventV2, ...]

    @property
    def run_id(self):
        return self.request.run_id

    @property
    def status(self):
        return self.events[-1].document["status"] if self.events else None

    @property
    def head_event_sha256(self):
        return self.events[-1].event_sha256 if self.events else None

    def public_document(self):
        head = self.events[-1].document if self.events else {}
        return {
            "run_id": self.run_id, "status": self.status,
            "stage": head.get("stage"), "progress": head.get("progress"),
            "failure_code": head.get("failure_code"),
            "result": head.get("result"),
            "event_count": len(self.events),
            "head_event_sha256": self.head_event_sha256,
            "terminal": self.status in TERMINAL,
            "retryable": self.status == "failed_retryable",
        }


__all__ = ["P10SafetyAnalysisJobSnapshotV2"]
