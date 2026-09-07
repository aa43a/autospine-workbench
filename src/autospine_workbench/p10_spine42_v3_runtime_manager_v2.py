"""Single-owner, single-worker orchestration shell for P10.7b v2."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import threading

from .p10_spine42_v3_runtime_authority_v2 import (
    P10Spine42V3RuntimeAuthorityV2,
)
from .p10_spine42_v3_runtime_job_contract_v2 import LATE_STAGES, TERMINAL
from .p10_spine42_v3_runtime_job_store_v2 import (
    P10Spine42V3RuntimeJobConflictV2, P10Spine42V3RuntimeJobStoreV2,
)
from .p10_spine42_v3_runtime_manager_owner_lease_v2 import (
    P10Spine42V3RuntimeManagerOwnerLeaseV2,
)
from .p10_spine42_v3_runtime_preflight_v2 import (
    P10Spine42V3RuntimePreflightV2,
)
from .p10_spine42_v3_runtime_recovery_v2 import (
    recover_p10_spine42_v3_runtime_jobs_v2,
)
from .project_store import ProjectStore
from .spine42_v3_runtime_candidate_catalog_v2 import (
    read_spine42_v3_runtime_candidate_catalog_v2,
)


class P10Spine42V3RuntimeManagerV2Error(RuntimeError):
    """Path-free manager lifecycle failure."""


@dataclass(slots=True)
class _Task:
    permit: object
    future: Future | None = None
    started: bool = False


class P10Spine42V3RuntimeManagerV2:
    """Own the lease, journal CAS, permit, and exactly one worker."""

    def __init__(
        self, project_store, *, execution,
        owner_factory=P10Spine42V3RuntimeManagerOwnerLeaseV2,
        store_factory=P10Spine42V3RuntimeJobStoreV2,
        recovery=recover_p10_spine42_v3_runtime_jobs_v2,
        preflight_factory=P10Spine42V3RuntimePreflightV2,
        authority_factory=P10Spine42V3RuntimeAuthorityV2,
        executor_factory=ThreadPoolExecutor,
        catalog_reader=read_spine42_v3_runtime_candidate_catalog_v2,
    ):
        lease = executor = None
        try:
            if type(project_store) is not ProjectStore or not all(callable(x) for x in (
                execution, owner_factory, store_factory, recovery,
                preflight_factory, authority_factory, executor_factory,
                catalog_reader,
            )):
                raise ValueError
            lease = owner_factory(project_store.state_root).acquire()
            store = store_factory(project_store.state_root)
            recovered = recovery(store)
            preflight = preflight_factory(project_store.state_root)
            authority = authority_factory(store, lease)
            executor = executor_factory(
                max_workers=1,
                thread_name_prefix="autospine-p10-spine42-v3-runtime-v2",
            )
            self._projects, self._lease = project_store, lease
            self._store, self._recovered = store, recovered
            self._preflight, self._authority = preflight, authority
            self._executor, self._execution = executor, execution
            self._catalog_reader = catalog_reader
            self._lock, self._closed = threading.RLock(), False
            self._tasks: dict[str, _Task] = {}
        except Exception as exc:
            if executor is not None:
                try:
                    executor.shutdown(wait=True, cancel_futures=True)
                except Exception:
                    pass
            if lease is not None:
                try:
                    lease.close()
                except Exception:
                    pass
            raise P10Spine42V3RuntimeManagerV2Error(
                "Runtime manager could not be constructed") from exc

    @property
    def startup_recovery(self):
        return self._recovered

    def catalog(self, continuation=None):
        try:
            value = self._catalog_reader(
                self._projects.state_root,
                continuation_spine_run_id=continuation,
            )
            return value.public_document()
        except Exception as exc:
            raise P10Spine42V3RuntimeManagerV2Error(
                "Runtime candidate catalog is unavailable") from exc

    def submit(self, payload, *, selection_source):
        """Freshen, persist, CAS-claim, and enqueue one exact request."""
        with self._lock:
            self._require_open()
            try:
                prepared = self._preflight.prepare(
                    payload, selection_source=selection_source)
                prepared = self._preflight.refresh_for_create(prepared)
                snapshot = self._store.create(prepared.request)
                if snapshot.status != "queued":
                    return snapshot.public_document()
                snapshot = self._store.append_event(
                    snapshot.job_id, "running", "exact_source_readback",
                    expected_previous_event_sha256=(
                        snapshot.head_event_sha256),
                )
                try:
                    permit = self._authority.issue(prepared, snapshot)
                except Exception as exc:
                    self._settle(
                        snapshot, "failed_retryable",
                        "execution_authority_failed")
                    raise P10Spine42V3RuntimeManagerV2Error(
                        "Runtime execution authority could not be issued"
                    ) from exc
                task = _Task(permit)
                self._tasks[snapshot.job_id] = task
                try:
                    task.future = self._executor.submit(
                        self._run, snapshot.job_id, permit)
                except Exception:
                    self._authority.revoke(permit)
                    self._tasks.pop(snapshot.job_id, None)
                    snapshot = self._settle(
                        snapshot, "failed_retryable",
                        "execution_enqueue_failed")
                return snapshot.public_document()
            except P10Spine42V3RuntimeManagerV2Error:
                raise
            except Exception as exc:
                raise P10Spine42V3RuntimeManagerV2Error(
                    "Runtime job could not be submitted") from exc

    def get(self, job_id):
        try:
            return self._store.load(job_id).public_document()
        except Exception as exc:
            raise P10Spine42V3RuntimeManagerV2Error(
                "Runtime job is unavailable") from exc

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            tasks = tuple(self._tasks.items())
        failure = None
        try:
            for job_id, task in tasks:
                future = task.future
                if future is not None and future.cancel():
                    self._authority.revoke(task.permit)
                    try:
                        self._interrupt(job_id)
                    except Exception as exc:
                        failure = failure or exc
            self._executor.shutdown(wait=True, cancel_futures=True)
        except Exception as exc:
            failure = failure or exc
        finally:
            try:
                self._lease.close()
            except Exception as exc:
                failure = failure or exc
        if failure is not None:
            raise P10Spine42V3RuntimeManagerV2Error(
                "Runtime manager could not be closed") from failure

    def _run(self, job_id, permit):
        with self._lock:
            task = self._tasks.get(job_id)
            if task is None or task.permit is not permit:
                return
            task.started = True
        try:
            self._execution(
                self._store, self._preflight, self._authority, permit)
        except Exception:
            try:
                snapshot = self._store.load(job_id)
                if snapshot.status not in TERMINAL \
                        and snapshot.head["stage"] not in LATE_STAGES:
                    self._settle(
                        snapshot, "failed_retryable", "execution_failed")
            except Exception:
                pass
        finally:
            with self._lock:
                current = self._tasks.get(job_id)
                if current is not None and current.permit is permit:
                    self._tasks.pop(job_id, None)

    def _interrupt(self, job_id):
        snapshot = self._store.load(job_id)
        if snapshot.status not in TERMINAL:
            self._settle(
                snapshot, "interrupted_retryable", "manager_closed")

    def _settle(self, snapshot, status, code):
        head = snapshot.head
        try:
            return self._store.append_event(
                snapshot.job_id, status, head["stage"],
                expected_previous_event_sha256=(
                    snapshot.head_event_sha256),
                current=head["progress"]["current"],
                total=head["progress"]["total"],
                failure_code=code, resume_mode="new_authorization",
                capture_address=head["capture_address"],
            )
        except P10Spine42V3RuntimeJobConflictV2:
            return self._store.load(snapshot.job_id)

    def _require_open(self):
        if self._closed:
            raise P10Spine42V3RuntimeManagerV2Error(
                "Runtime manager is closed")

    def __enter__(self):
        return self

    def __exit__(self, _kind, _value, _traceback):
        self.close()


__all__ = [
    "P10Spine42V3RuntimeManagerV2",
    "P10Spine42V3RuntimeManagerV2Error",
]
