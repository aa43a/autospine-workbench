"""Append-only journal for authorized P10.7b v2 runtime attempts."""

from __future__ import annotations

import threading

from .p10_spine42_v3_runtime_job_contract_v2 import (
    LATE_STAGES, P10Spine42V3RuntimeJobContractV2Error,
    P10Spine42V3RuntimeJobEventV2, P10Spine42V3RuntimeJobRequestV2,
    require_runtime_job_source_binding_v2, require_runtime_job_transition_v2,
)
from .p10_spine42_v3_runtime_job_files_v2 import (
    P10Spine42V3RuntimeJobFilesV2Error, event_inventory, event_name,
    exact_directory, normalized_state_root, publish_json, read_json,
    require_inventory, require_sha, run_directory, run_ids,
)
from .p10_spine42_v3_runtime_job_errors_v2 import (
    P10Spine42V3RuntimeJobConflictV2,
    P10Spine42V3RuntimeJobStoreV2Error,
)
from .p10_spine42_v3_runtime_job_bindings_v2 import (
    AUTHORIZATION_NAMESPACE, P10Spine42V3RuntimeJobBindingConflictV2,
    P10Spine42V3RuntimeJobBindingV2Error, bind_runtime_job_attempt_v2,
    require_runtime_job_retry_chain_v2, verify_runtime_job_bindings_v2,
)
from .p10_spine42_v3_runtime_job_snapshot_v2 import (
    P10Spine42V3RuntimeJobRecoveryV2, P10Spine42V3RuntimeJobSnapshotV2,
)
from .p10_spine42_v3_runtime_job_process_lock_v2 import (
    P10Spine42V3RuntimeJobProcessLockV2Error, runtime_job_process_lock_v2,
)
from .p10_spine42_v3_runtime_job_staging_v2 import (
    P10Spine42V3RuntimeJobStagingV2Error,
    cleanup_runtime_job_staging_v2, commit_runtime_job_staging_v2,
    create_runtime_job_staging_v2, existing_runtime_job_v2,
    recover_runtime_job_staging_v2, runtime_job_staging_parent_v2,
)

JOB_NAMESPACE = "body-sway-spine42-v3-runtime-jobs-v2"
_LOCK = threading.RLock()

class P10Spine42V3RuntimeJobStoreV2:
    """Persist journals only; no return value is a runner authority claim."""

    def __init__(self, state_root):
        try:
            self.state_root = normalized_state_root(state_root)
        except P10Spine42V3RuntimeJobFilesV2Error as exc:
            raise P10Spine42V3RuntimeJobStoreV2Error(
                "Runtime job store is unavailable") from exc

    def create(self, request):
        """Create one immutable authorization attempt or return its journal."""
        if type(request) is not P10Spine42V3RuntimeJobRequestV2:
            raise P10Spine42V3RuntimeJobStoreV2Error(
                "Runtime job request type is invalid")
        with _LOCK, runtime_job_process_lock_v2(self.state_root):
            staging_parent = staging = None
            try:
                existing = existing_runtime_job_v2(
                    self.state_root, JOB_NAMESPACE, request.job_id)
                if existing is not None:
                    snapshot = self.load(request.job_id)
                    if snapshot.request.canonical_bytes != request.canonical_bytes:
                        raise P10Spine42V3RuntimeJobConflictV2(
                            "Runtime job address is occupied")
                    return snapshot
                staging_parent, staging = create_runtime_job_staging_v2(
                    self.state_root, request.job_id)
                events = exact_directory(staging, "events", create=True)
                queued = P10Spine42V3RuntimeJobEventV2.build(
                    request.job_id, 1, None, "queued", "queued")
                publish_json(
                    staging, "request.json", request.document,
                    staging_parent=staging_parent)
                publish_json(
                    events, event_name(1), queued.document,
                    staging_parent=staging_parent)
                prepared = self._load_directory(
                    staging, request.job_id, verify_bindings=False)
                if prepared.request.canonical_bytes != request.canonical_bytes \
                        or prepared.events != (queued,):
                    raise P10Spine42V3RuntimeJobStoreV2Error(
                        "Runtime job staged snapshot differs")
                bind_runtime_job_attempt_v2(
                    self.state_root, request, self.load)
                _, reused = commit_runtime_job_staging_v2(
                    self.state_root, JOB_NAMESPACE, request.job_id, staging)
                if not reused:
                    staging = None
                snapshot = self.load(request.job_id)
                return snapshot
            except P10Spine42V3RuntimeJobConflictV2:
                raise
            except P10Spine42V3RuntimeJobBindingConflictV2 as exc:
                raise P10Spine42V3RuntimeJobConflictV2(
                    "Runtime job immutable binding conflicts") from exc
            except _FAILURES as exc:
                raise P10Spine42V3RuntimeJobStoreV2Error(
                    "Runtime job could not be created") from exc
            finally:
                cleanup_runtime_job_staging_v2(staging, staging_parent)

    def load(self, job_id):
        try:
            require_sha(job_id)
            directory = self._run(job_id, create=False)
            snapshot = self._load_directory(
                directory, job_id, verify_bindings=True)
            require_runtime_job_retry_chain_v2(
                snapshot, self._load_predecessor)
            return snapshot
        except P10Spine42V3RuntimeJobStoreV2Error:
            raise
        except _FAILURES as exc:
            raise P10Spine42V3RuntimeJobStoreV2Error(
                "Runtime job cannot be loaded") from exc

    def append_event(self, job_id, status, stage, *,
                     expected_previous_event_sha256, current=0, total=1,
                     failure_code=None, resume_mode=None,
                     capture_address=None, result=None):
        """Append one CAS event; success still grants no execution authority."""
        with _LOCK, runtime_job_process_lock_v2(self.state_root):
            snapshot = self.load(job_id)
            if snapshot.head_event_sha256 != expected_previous_event_sha256:
                raise P10Spine42V3RuntimeJobConflictV2(
                    "Runtime job event predecessor is stale")
            try:
                event = P10Spine42V3RuntimeJobEventV2.build(
                    job_id, len(snapshot.events) + 1,
                    expected_previous_event_sha256, status, stage,
                    current=current, total=total, failure_code=failure_code,
                    resume_mode=resume_mode, capture_address=capture_address,
                    result=result,
                )
                require_runtime_job_source_binding_v2(snapshot.request, event)
                require_runtime_job_transition_v2(
                    snapshot.events[-1] if snapshot.events else None, event)
                directory = self._run(job_id, create=False)
                event_root = exact_directory(directory, "events", create=False)
                publish_json(
                    event_root, event_name(len(snapshot.events) + 1),
                    event.document,
                    staging_parent=runtime_job_staging_parent_v2(
                        self.state_root),
                )
                result_snapshot = self.load(job_id)
                if result_snapshot.head_event_sha256 != event.event_sha256:
                    raise P10Spine42V3RuntimeJobStoreV2Error(
                        "Runtime job event failed exact readback")
                return result_snapshot
            except P10Spine42V3RuntimeJobConflictV2:
                raise
            except _FAILURES as exc:
                raise P10Spine42V3RuntimeJobStoreV2Error(
                    "Runtime job event cannot be appended") from exc

    def recover_interrupted(self):
        """Settle active jobs; never requeue, rerun, or mark one completed."""
        recovered, readback = [], []
        with _LOCK, runtime_job_process_lock_v2(self.state_root):
            self._recover_staging()
            for job_id in run_ids(self.state_root, JOB_NAMESPACE):
                snapshot = self.load(job_id)
                if snapshot.status not in {"queued", "running"}:
                    continue
                stage = snapshot.head["stage"]
                if stage in LATE_STAGES:
                    readback.append(job_id)
                    continue
                snapshot = self.append_event(
                    job_id, "interrupted_retryable", stage,
                    expected_previous_event_sha256=snapshot.head_event_sha256,
                    current=snapshot.head["progress"]["current"],
                    total=snapshot.head["progress"]["total"],
                    failure_code="process_restart",
                    resume_mode="new_authorization",
                    capture_address=snapshot.head["capture_address"],
                )
                recovered.append(snapshot.job_id)
        return P10Spine42V3RuntimeJobRecoveryV2(
            tuple(recovered), tuple(readback))

    def _recover_staging(self):
        recover_runtime_job_staging_v2(
            self.state_root, JOB_NAMESPACE,
            load_directory=lambda directory, job_id, verify: self._load_directory(
                directory, job_id, verify_bindings=verify),
            load_predecessor=self._load_predecessor,
            load_committed=self.load,
        )

    def _load_directory(self, directory, job_id, *, verify_bindings):
        require_inventory(directory, {"request.json"}, {"events"})
        request = P10Spine42V3RuntimeJobRequestV2.from_document(
            read_json(directory, "request.json"))
        if request.job_id != job_id:
            raise P10Spine42V3RuntimeJobStoreV2Error(
                "Runtime job request address differs")
        if verify_bindings:
            verify_runtime_job_bindings_v2(self.state_root, request)
        events, event_root = [], exact_directory(
            directory, "events", create=False)
        for sequence, path in event_inventory(event_root):
            event = P10Spine42V3RuntimeJobEventV2.from_document(
                read_json(path.parent, path.name))
            if event.document["sequence"] != sequence \
                    or event.document["job_id"] != job_id:
                raise P10Spine42V3RuntimeJobStoreV2Error(
                    "Runtime job event slot differs")
            require_runtime_job_source_binding_v2(request, event)
            require_runtime_job_transition_v2(
                events[-1] if events else None, event)
            events.append(event)
        if not events:
            raise P10Spine42V3RuntimeJobStoreV2Error(
                "Runtime job event history is empty")
        return P10Spine42V3RuntimeJobSnapshotV2(request, tuple(events))

    def _load_predecessor(self, job_id):
        return self._load_directory(
            self._run(job_id, create=False), job_id, verify_bindings=True)

    def _run(self, job_id, *, create):
        return run_directory(
            self.state_root, JOB_NAMESPACE, job_id, create=create)

_FAILURES = (
    P10Spine42V3RuntimeJobContractV2Error,
    P10Spine42V3RuntimeJobBindingV2Error,
    P10Spine42V3RuntimeJobFilesV2Error,
    P10Spine42V3RuntimeJobProcessLockV2Error,
    P10Spine42V3RuntimeJobStagingV2Error,
    RuntimeError, TypeError, ValueError,
)
__all__ = [
    "AUTHORIZATION_NAMESPACE", "JOB_NAMESPACE",
    "P10Spine42V3RuntimeJobConflictV2",
    "P10Spine42V3RuntimeJobRecoveryV2",
    "P10Spine42V3RuntimeJobSnapshotV2",
    "P10Spine42V3RuntimeJobStoreV2", "P10Spine42V3RuntimeJobStoreV2Error",
]
