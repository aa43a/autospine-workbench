"""Late-stage, readback-only recovery for P10.7b v2 runtime jobs."""

from __future__ import annotations

from dataclasses import dataclass
from .p10_spine42_v3_runtime_job_store_v2 import (
    P10Spine42V3RuntimeJobConflictV2,
    P10Spine42V3RuntimeJobStoreV2,
    P10Spine42V3RuntimeJobStoreV2Error,
)
from .p10_spine42_v3_runtime_readback_v2 import (
    require_p10_spine42_v3_runtime_readback_v2,
)
from .spine42_v3_runtime_reader_v2 import (
    Spine42V3RuntimeReaderV2Error,
    Spine42V3RuntimeV2NotFound,
    VerifiedSpine42V3RuntimeReaderV2,
)


RECOVERY_FORMAT = "autospine-p10-spine42-v3-runtime-recovery-v2"


class P10Spine42V3RuntimeRecoveryV2Error(RuntimeError):
    """Raised when startup recovery cannot reach a trustworthy decision."""


@dataclass(frozen=True, slots=True)
class P10Spine42V3RuntimeRecoveryItemV2:
    job_id: str
    outcome: str
    status: str
    stage: str
    head_event_sha256: str

    def public_document(self):
        return {
            "job_id": self.job_id,
            "outcome": self.outcome,
            "status": self.status,
            "stage": self.stage,
            "head_event_sha256": self.head_event_sha256,
        }


@dataclass(frozen=True, slots=True)
class P10Spine42V3RuntimeRecoveryResultV2:
    interrupted_job_ids: tuple[str, ...]
    readback_required_job_ids: tuple[str, ...]
    items: tuple[P10Spine42V3RuntimeRecoveryItemV2, ...]

    def public_document(self):
        return {
            "format": RECOVERY_FORMAT,
            "format_version": 2,
            "interrupted_job_ids": list(self.interrupted_job_ids),
            "readback_required_job_ids": list(
                self.readback_required_job_ids
            ),
            "items": [item.public_document() for item in self.items],
            "runner_execution_authorized": False,
            "publication_authorized": False,
        }


def recover_p10_spine42_v3_runtime_jobs_v2(
    store, *, reader_factory=VerifiedSpine42V3RuntimeReaderV2,
):
    """Settle late journals by exact readback, without running anything."""

    if type(store) is not P10Spine42V3RuntimeJobStoreV2 \
            or not callable(reader_factory):
        raise P10Spine42V3RuntimeRecoveryV2Error(
            "Runtime recovery dependencies are invalid")
    try:
        recovery = store.recover_interrupted()
        if not recovery.readback_required_job_ids:
            return _result(recovery, ())
        reader = reader_factory(store.state_root)
        items = tuple(
            _recover_one(store, reader, job_id)
            for job_id in recovery.readback_required_job_ids
        )
        return _result(recovery, items)
    except P10Spine42V3RuntimeRecoveryV2Error:
        raise
    except P10Spine42V3RuntimeJobStoreV2Error as exc:
        raise P10Spine42V3RuntimeRecoveryV2Error(
            "Runtime recovery journal is unavailable") from exc
    except Exception as exc:
        raise P10Spine42V3RuntimeRecoveryV2Error(
            "Runtime recovery dependency failed") from exc


def _recover_one(store, reader, job_id):
    snapshot = store.load(job_id)
    if snapshot.status != "running" or snapshot.head["stage"] not in {
        "publishing", "parent_exact_readback",
    }:
        return _item("already_settled", snapshot)
    try:
        address = require_p10_spine42_v3_runtime_readback_v2(
            reader, snapshot, store.state_root,
        )
    except Spine42V3RuntimeV2NotFound:
        return _settle_failure(
            store, snapshot, "failed_retryable",
            "capture_address_not_found", "new_authorization",
        )
    except Spine42V3RuntimeReaderV2Error:
        return _settle_failure(
            store, snapshot, "failed_terminal",
            "capture_readback_mismatch", None,
        )
    try:
        if snapshot.head["stage"] == "publishing":
            snapshot = store.append_event(
                job_id, "running", "parent_exact_readback",
                expected_previous_event_sha256=(
                    snapshot.head_event_sha256
                ),
                current=0, total=1, capture_address=address,
            )
        snapshot = store.append_event(
            job_id, "completed", "completed",
            expected_previous_event_sha256=snapshot.head_event_sha256,
            current=1, total=1, result=address,
        )
        return _item("completed", snapshot)
    except P10Spine42V3RuntimeJobConflictV2:
        return _item("conflict_reloaded", store.load(job_id))


def _settle_failure(store, snapshot, status, code, resume_mode):
    try:
        head = snapshot.head
        snapshot = store.append_event(
            snapshot.job_id, status, head["stage"],
            expected_previous_event_sha256=snapshot.head_event_sha256,
            current=head["progress"]["current"],
            total=head["progress"]["total"], failure_code=code,
            resume_mode=resume_mode,
            capture_address=head["capture_address"],
        )
        return _item(status, snapshot)
    except P10Spine42V3RuntimeJobConflictV2:
        return _item("conflict_reloaded", store.load(snapshot.job_id))


def _item(outcome, snapshot):
    return P10Spine42V3RuntimeRecoveryItemV2(
        snapshot.job_id, outcome, snapshot.status,
        snapshot.head["stage"], snapshot.head_event_sha256,
    )


def _result(recovery, items):
    return P10Spine42V3RuntimeRecoveryResultV2(
        recovery.interrupted_job_ids,
        recovery.readback_required_job_ids,
        tuple(items),
    )


__all__ = [
    "P10Spine42V3RuntimeRecoveryItemV2",
    "P10Spine42V3RuntimeRecoveryResultV2",
    "P10Spine42V3RuntimeRecoveryV2Error", "RECOVERY_FORMAT",
    "recover_p10_spine42_v3_runtime_jobs_v2",
]
