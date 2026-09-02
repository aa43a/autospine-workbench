"""Canonical request/event contracts for asynchronous P10.4b v2 runs."""

from __future__ import annotations

from dataclasses import dataclass, field
import json

from .body_sway_amplitude_envelope_profile_v2 import (
    amplitude_analyzer_profile_v2,
)
from .body_sway_continuous_proof_profile_v2 import (
    continuous_analyzer_profile_v2,
)
from .p10_completed_job_snapshot import VerifiedCompletedP10CaptureJob
from .p10_safety_analysis_job_validation_v2 import (
    ACTIVE, EVENT_DOMAIN, EVENT_FORMAT, REQUEST_FORMAT, TERMINAL,
    P10SafetyAnalysisJobValidationV2Error, require_event_document,
    require_request_document,
)
from .resolved_project import canonical_sha256


RUN_DOMAIN = "autospine-p10-safety-analysis-run/v2"


class P10SafetyAnalysisJobContractV2Error(ValueError):
    """Raised when persisted asynchronous state is not canonical."""


@dataclass(frozen=True, slots=True)
class P10SafetyAnalysisRunRequestV2:
    _canonical_json: str = field(repr=False)

    @classmethod
    def build(cls, completed: VerifiedCompletedP10CaptureJob, *, attempt: int,
              previous_run_id: str | None):
        if type(completed) is not VerifiedCompletedP10CaptureJob:
            raise P10SafetyAnalysisJobContractV2Error(
                "Safety analysis launch requires a completed capture job"
            )
        address = completed.address
        return cls.from_document({
            "format": REQUEST_FORMAT, "format_version": 2,
            "job_id": completed.job_id, "package_id": completed.package_id,
            "terminal_event_sha256": completed.terminal_event_sha256,
            "terminal_sequence": completed.terminal_sequence,
            "capture_address": {
                "project_id": address.project_id,
                "temporary_preview_v2_sha256":
                    address.temporary_preview_v2_sha256,
                "runtime_execution_bundle_sha256":
                    address.runtime_execution_bundle_sha256,
                "capture_artifact_set_sha256":
                    address.capture_artifact_set_sha256,
            },
            "attempt": attempt, "previous_run_id": previous_run_id,
            "analyzers_sha256": canonical_sha256({
                "domain": "autospine-p10-safety-analyzers/v2",
                "amplitude": amplitude_analyzer_profile_v2(),
                "continuous": continuous_analyzer_profile_v2(),
            }),
        })

    @classmethod
    def from_document(cls, document):
        try:
            return cls(_canonical(require_request_document(document)))
        except P10SafetyAnalysisJobValidationV2Error as exc:
            raise P10SafetyAnalysisJobContractV2Error(str(exc)) from exc

    @property
    def document(self):
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self):
        return self._canonical_json.encode("utf-8")

    @property
    def run_id(self):
        return canonical_sha256({"domain": RUN_DOMAIN,
                                 "request": self.document})


@dataclass(frozen=True, slots=True)
class P10SafetyAnalysisRunEventV2:
    _canonical_json: str = field(repr=False)

    @classmethod
    def build(cls, run_id, sequence, previous_sha, status, stage, *,
              current=0, total=1, failure_code=None, result=None):
        payload = {
            "format": EVENT_FORMAT, "format_version": 2,
            "run_id": run_id, "sequence": sequence,
            "previous_event_sha256": previous_sha,
            "status": status, "stage": stage,
            "progress": {"current": current, "total": total},
            "failure_code": failure_code, "result": result,
        }
        document = dict(payload)
        document["event_sha256"] = canonical_sha256({
            "domain": EVENT_DOMAIN, "event": payload,
        })
        return cls.from_document(document)

    @classmethod
    def from_document(cls, document):
        try:
            return cls(_canonical(require_event_document(document)))
        except P10SafetyAnalysisJobValidationV2Error as exc:
            raise P10SafetyAnalysisJobContractV2Error(str(exc)) from exc

    @property
    def document(self):
        return json.loads(self._canonical_json)

    @property
    def event_sha256(self):
        return self.document["event_sha256"]

    @property
    def canonical_bytes(self):
        return self._canonical_json.encode("utf-8")


def require_transition(previous, event) -> None:
    if previous is None:
        row = event.document
        valid = row["sequence"] == 1 and row["status"] == "queued" \
            and row["previous_event_sha256"] is None
    else:
        left, right = previous.document, event.document
        allowed = {
            "queued": ACTIVE | TERMINAL,
            "running": {"running"} | TERMINAL,
            "failed_retryable": {"queued"},
            "completed": set(), "failed_terminal": set(),
        }[left["status"]]
        valid = left["run_id"] == right["run_id"] \
            and right["sequence"] == left["sequence"] + 1 \
            and right["previous_event_sha256"] == previous.event_sha256 \
            and right["status"] in allowed
        if valid and left["status"] == right["status"] == "running" \
                and left["stage"] == right["stage"]:
            old, new = left["progress"], right["progress"]
            valid = old["total"] == new["total"] \
                and old["current"] <= new["current"]
    if not valid:
        raise P10SafetyAnalysisJobContractV2Error(
            "Safety analysis event transition is invalid"
        )


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


__all__ = [
    "ACTIVE", "TERMINAL", "P10SafetyAnalysisJobContractV2Error",
    "P10SafetyAnalysisRunEventV2", "P10SafetyAnalysisRunRequestV2",
    "require_transition",
]
