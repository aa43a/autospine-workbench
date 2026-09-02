"""Single-worker, attempt-aware orchestration for P10.4b v2 analysis."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import threading

from .p10_completed_job_snapshot import (
    verified_completed_p10_capture_job,
)
from .p10_safety_analysis_job_contract_v2 import (
    ACTIVE, P10SafetyAnalysisRunRequestV2,
)
from .p10_safety_analysis_job_store_v2 import (
    P10SafetyAnalysisJobConflictV2, P10SafetyAnalysisJobStoreV2,
    P10SafetyAnalysisJobStoreV2Error,
)
from .p10_safety_analysis_parent_validation_v2 import (
    verify_parent_p10_safety_analysis_result_v2,
)
from .p10_safety_analysis_v2_commands import (
    P10SafetyAnalysisV2CommandError,
)
from .p10_safety_analysis_worker_process_v2 import (
    P10SafetyAnalysisWorkerCancelledV2,
    P10SafetyAnalysisWorkerFailureV2,
    P10SafetyAnalysisWorkerProcessV2Error,
    run_p10_safety_analysis_worker_process_v2,
)
from .p10_safety_analysis_manager_error_v2 import (
    P10SafetyAnalysisManagerV2Error,
)
from .p10_safety_analysis_result_v2 import (
    public_result, require_request_job,
)
from .p10_safety_analysis_public_cache_v2 import (
    P10SafetyAnalysisPublicCacheV2,
)
from .project_store import ProjectStore


class P10SafetyAnalysisManagerV2:
    def __init__(self, job_reader, projects: ProjectStore) -> None:
        if type(projects) is not ProjectStore \
                or not callable(getattr(job_reader, "get", None)):
            raise P10SafetyAnalysisManagerV2Error(
                "Safety analysis manager requires exact local stores"
            )
        self._jobs = job_reader
        self._projects = projects
        self._store = P10SafetyAnalysisJobStoreV2(projects.state_root)
        try:
            self._recovered = self._store.recover_interrupted()
        except Exception as exc:
            raise P10SafetyAnalysisManagerV2Error(
                "Safety analysis startup recovery failed"
            ) from exc
        self._lock = threading.RLock()
        self._closed = False
        self._cancel = threading.Event()
        self._futures: dict[str, Future[None]] = {}
        self._progress_memory: dict[str, tuple[str, int, int]] = {}
        self._public_cache = P10SafetyAnalysisPublicCacheV2()
        self._worker = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="autospine-p10-safety-v2",
        )

    def entry(self, job_id: str):
        """Return immediately from the capture job and small run journals."""

        completed = self._completed_job(job_id)
        latest = self._store.latest_for_job(completed.job_id)
        if latest is not None:
            require_request_job(latest.request.document, completed)
        if latest is not None and latest.status in ACTIVE:
            return _response(completed.job_id, latest)
        return {"ok": True, "status": "ready", "job_id": completed.job_id}

    def submit(self, job_id: str):
        """Reuse an active attempt; otherwise enqueue the next exact attempt."""

        with self._lock:
            self._require_open()
            completed = self._completed_job(job_id)
            latest = self._store.latest_for_job(completed.job_id)
            if latest is not None:
                require_request_job(latest.request.document, completed)
            if latest is not None and latest.status in ACTIVE:
                return _response(completed.job_id, latest)
            if latest is not None and not latest.events:
                snapshot = self._store.create(latest.request)
                self._futures[snapshot.run_id] = self._worker.submit(
                    self._run, snapshot.run_id,
                )
                return _response(completed.job_id, snapshot)
            request = P10SafetyAnalysisRunRequestV2.build(
                completed,
                attempt=(1 if latest is None else
                         latest.request.document["attempt"] + 1),
                previous_run_id=(latest.run_id if latest else None),
            )
            snapshot = self._store.create(request)
            if snapshot.run_id not in self._futures:
                self._futures[snapshot.run_id] = self._worker.submit(
                    self._run, snapshot.run_id,
                )
            return _response(completed.job_id, snapshot)

    def get(self, job_id: str, run_id: str):
        snapshot = self._store.load(run_id)
        if snapshot.request.document["job_id"] != job_id:
            raise P10SafetyAnalysisManagerV2Error(
                "Safety analysis run belongs to another job"
            )
        return _response(job_id, snapshot)

    def result(self, job_id: str, run_id: str):
        snapshot = self._store.load(run_id)
        request = snapshot.request.document
        if request["job_id"] != job_id or snapshot.status != "completed":
            raise P10SafetyAnalysisManagerV2Error(
                "Safety analysis result is unavailable"
            )
        cached = self._public_cache.get(run_id)
        if cached is None:
            amplitude, continuous = self._store.read_result(run_id)
            cached = public_result(
                job_id, snapshot.public_document(), amplitude, continuous,
            )
            self._public_cache.put(run_id, cached)
        return cached

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._cancel.set()
            futures = tuple(self._futures.items())
        for _, future in futures:
            future.cancel()
        for run_id, _ in futures:
            self._fail(run_id, terminal=False, code="manager_closed")
        self._worker.shutdown(wait=False, cancel_futures=True)
        with self._lock:
            self._futures.clear()

    def _completed_job(self, job_id):
        try:
            return verified_completed_p10_capture_job(
                self._jobs.get(job_id), job_id,
            )
        except Exception as exc:
            raise P10SafetyAnalysisManagerV2Error(
                "Completed runtime capture job is unavailable"
            ) from exc

    def _run(self, run_id: str) -> None:
        try:
            self._require_not_cancelled()
            snapshot = self._store.load(run_id)
            if snapshot.status != "queued":
                return
            request = snapshot.request.document
            snapshot = self._store.append(
                run_id, "running", "review_admission",
                expected_previous=snapshot.head_event_sha256,
                current=0, total=1,
            )
            with self._lock:
                self._progress_memory[run_id] = (
                    "review_admission", 0, 1,
                )
            worker_result = run_p10_safety_analysis_worker_process_v2(
                run_id, request["job_id"], self._projects.state_root,
                self._projects.workspace_root,
                on_progress=lambda stage, current, total: self._progress(
                    run_id, stage, current, total,
                ),
                cancel_event=self._cancel,
            )
            self._require_not_cancelled()
            snapshot = self._store.load(run_id)
            snapshot = self._store.append(
                run_id, "running", "sealing",
                expected_previous=snapshot.head_event_sha256,
                current=0, total=1,
            )
            amplitude, continuous = \
                verify_parent_p10_safety_analysis_result_v2(
                    self._jobs, self._projects, self._store,
                    run_id, worker_result,
                )
            self._require_not_cancelled()
            completed = self._store.append(
                run_id, "completed", "completed",
                expected_previous=snapshot.head_event_sha256,
                current=1, total=1, result=worker_result.result,
            )
            receipt = public_result(
                request["job_id"], completed.public_document(),
                amplitude, continuous,
            )
            self._public_cache.put(run_id, receipt)
        except (_P10SafetyAnalysisCancelled,
                P10SafetyAnalysisWorkerCancelledV2):
            self._fail(run_id, terminal=False, code="manager_closed")
        except (P10SafetyAnalysisV2CommandError,
                P10SafetyAnalysisWorkerFailureV2) as exc:
            self._fail(
                run_id, terminal=exc.terminal, code=exc.failure_code,
            )
        except P10SafetyAnalysisWorkerProcessV2Error:
            self._fail(
                run_id, terminal=False, code="worker_process_failed",
            )
        except Exception:
            self._fail(run_id, terminal=False, code="analysis_failed")
        finally:
            with self._lock:
                self._futures.pop(run_id, None)
                self._progress_memory.pop(run_id, None)

    def _progress(self, run_id, stage, current, total):
        self._require_not_cancelled()
        safe_total = max(1, total)
        stride = max(1, safe_total // 50)
        with self._lock:
            prior = self._progress_memory.get(run_id)
        if prior is not None:
            prior_stage, prior_current, prior_total = prior
            if prior_stage == stage and prior_total == safe_total \
                    and prior_current <= current \
                    and current != safe_total \
                    and not (prior_current == 0 and current > 0) \
                    and current - prior_current < stride:
                return
        snapshot = self._store.load(run_id)
        if snapshot.status != "running":
            raise P10SafetyAnalysisManagerV2Error(
                "Safety analysis progress target is stale"
            )
        head = snapshot.events[-1].document
        previous = head["progress"]
        changed_stage = head["stage"] != stage
        if not changed_stage and current != safe_total \
                and not (previous["current"] == 0 and current > 0) \
                and current - previous["current"] < stride:
            with self._lock:
                self._progress_memory[run_id] = (
                    head["stage"], previous["current"], previous["total"],
                )
            return
        self._store.append(
            run_id, "running", stage,
            expected_previous=snapshot.head_event_sha256,
            current=current, total=safe_total,
        )
        with self._lock:
            self._progress_memory[run_id] = (
                stage, current, safe_total,
            )

    def _fail(self, run_id, *, terminal, code):
        try:
            snapshot = self._store.load(run_id)
            if snapshot.status in ACTIVE:
                self._store.append(
                    run_id,
                    "failed_terminal" if terminal else "failed_retryable",
                    "failed", expected_previous=snapshot.head_event_sha256,
                    failure_code=code,
                )
        except (P10SafetyAnalysisJobConflictV2,
                P10SafetyAnalysisJobStoreV2Error):
            return

    def _require_open(self):
        if self._closed:
            raise P10SafetyAnalysisManagerV2Error(
                "Safety analysis manager is closed"
            )

    def _require_not_cancelled(self):
        if self._cancel.is_set():
            raise _P10SafetyAnalysisCancelled()


class _P10SafetyAnalysisCancelled(RuntimeError):
    pass


def _response(job_id, snapshot):
    return {"ok": True, "status": snapshot.status, "job_id": job_id,
            "run": snapshot.public_document()}


__all__ = [
    "P10SafetyAnalysisManagerV2", "P10SafetyAnalysisManagerV2Error",
]
