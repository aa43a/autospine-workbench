"""Single-worker orchestration for confirmed package-centric P10 captures."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
import threading
from typing import Any

from .p10_capture_job_contract import ACTIVE_STATUSES
from .p10_capture_failure_codes import classify_p10_capture_failure
from .p10_capture_job_store import P10CaptureJobConflict, P10CaptureJobSnapshot, P10CaptureJobStore
from .p10_preview_v2_commands import (
    P10PreviewV2CommandError, P10PreviewV2CommandResult,
    compile_body_sway_preview_v2_for_package,
)
from .p10_runtime_capture_v2_commands import (
    P10RuntimeCaptureV2CommandResult,
    execute_p10_runtime_capture_v2_for_package,
)
from .p10_runtime_capture_v2_runner import P10RuntimeCaptureV2Progress
from .p10_runtime_environment import P10RuntimeEnvironment, discover_p10_runtime_environment
from .project_store import ProjectStore

FORMAT, FORMAT_VERSION = "autospine-p10-runtime-capture-preflight", 1
class P10CaptureJobManagerError(RuntimeError):
    """Raised when safe asynchronous orchestration cannot be established."""

class P10CaptureJobManager:
    """Own one worker and never infer fresh execution authority."""

    def __init__(
        self, project_store: ProjectStore, *,
        environment_loader: Callable[[Any], P10RuntimeEnvironment] =
            discover_p10_runtime_environment,
        preview_compiler: Callable[..., P10PreviewV2CommandResult] =
            compile_body_sway_preview_v2_for_package,
        capture_executor: Callable[..., P10RuntimeCaptureV2CommandResult] =
            execute_p10_runtime_capture_v2_for_package,
    ) -> None:
        if type(project_store) is not ProjectStore:
            raise P10CaptureJobManagerError("Capture manager requires a ProjectStore")
        self._projects = project_store
        self._jobs = P10CaptureJobStore(project_store.state_root)
        self._compile = preview_compiler
        self._execute = capture_executor
        self._environment_loader = environment_loader
        try:
            self._recovered = self._jobs.recover_interrupted_jobs()
        except Exception as exc:
            raise P10CaptureJobManagerError(
                "Capture manager startup validation failed") from exc
        self._lock = threading.Lock()
        self._environment_lock = threading.Lock()
        self._environment_value: P10RuntimeEnvironment | None = None
        self._cancel = threading.Event()
        self._closed = False
        self._futures: dict[str, Future[None]] = {}
        self._worker = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="autospine-p10-capture")

    @property
    def recovered_job_ids(self) -> tuple[str, ...]:
        return self._recovered

    def prepare(self, package_id: str) -> dict[str, Any]:
        """Compile current identities and expose only the cached environment."""
        self._require_open()
        try:
            preview = self._compile(self._projects, package_id)
            expected = _expected(preview)
            environment = self._runtime_environment()
        except Exception as exc:
            raise P10CaptureJobManagerError(
                "Capture preflight could not replay the current package"
            ) from exc
        return {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "package": {
                "package_id": preview.package_id, "project_id": preview.project_id,
                "clip_id": preview.clip_id,
                "case_count": preview.case_count,
            },
            "expected": {"p10_1": expected[0], "framing": expected[1]},
            "environment": environment.public_document(),
            "status": "ready" if environment.available
            else "runtime_unavailable",
        }

    def submit(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Persist this confirmation once and enqueue it at most once."""
        with self._lock:
            self._require_open()
            snapshot = self._jobs.create(payload)
            if snapshot.status == "queued" \
                    and snapshot.job_id not in self._futures:
                self._futures[snapshot.job_id] = self._worker.submit(
                    self._run, snapshot.job_id)
            return snapshot.public_document()

    def get(self, job_id: str) -> dict[str, Any]:
        return self._jobs.load(job_id).public_document()

    def wait(self, job_id: str, timeout: float | None = None) -> dict[str, Any]:
        with self._lock:
            future = self._futures.get(job_id)
        if future is not None:
            try:
                future.result(timeout=timeout)
            except CancelledError:
                pass
            except TimeoutError:
                raise
            except Exception as exc:
                raise P10CaptureJobManagerError(
                    "Capture worker did not settle safely") from exc
        return self.get(job_id)

    def close(self) -> None:
        """Request cancellation, settle queued work, and wait for one worker."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._cancel.set()
            futures = tuple(self._futures.items())
        cancelled = [job_id for job_id, future in futures if future.cancel()]
        for job_id in cancelled:
            self._interrupt(job_id)
        self._worker.shutdown(wait=True, cancel_futures=True)
        for job_id, _future in futures:
            self._interrupt(job_id)

    def _run(self, job_id: str) -> None:
        snapshot = self._jobs.load(job_id)
        if snapshot.status != "queued":
            return
        request_document = snapshot.request.document
        try:
            if self._cancel.is_set():
                self._interrupt(job_id)
                return
            snapshot = self._advance(snapshot, "exact_replay")
            preview = self._compile(self._projects, request_document["package_id"])
            if not _matches(request_document, preview):
                self._fail(snapshot, True, "input_head_changed")
                return
            snapshot = self._advance(snapshot, "preview_compiled")
            try:
                environment = self._runtime_environment()
            except P10CaptureJobManagerError:
                self._fail(snapshot, False, "runtime_environment_unavailable")
                return
            if not environment.available:
                self._fail(snapshot, False, "runtime_environment_unavailable")
                return
            snapshot = self._advance(snapshot, "runtime_verified")
            result = self._execute(
                self._projects, request_document["package_id"],
                environment=environment,
                expected_p10_1=request_document["expected_p10_1"],
                expected_framing=request_document["expected_framing"],
                license_acknowledged=request_document[
                    "explicit_runtime_license_confirmation"
                ],
                run_confirmed=request_document["explicit_run_confirmation"],
                on_progress=lambda value: self._progress(
                    job_id, preview.case_count, value),
                is_cancelled=self._cancel.is_set,
            )
            _require_result(request_document, preview, result)
            snapshot = self._jobs.load(job_id)
            if snapshot.status != "sealing":
                return
            self._advance(snapshot, "completed", addresses={
                "project": result.project_id,
                "preview": result.temporary_preview_v2_sha256,
                "execution_bundle": result.bundle_sha256,
                "artifact": result.artifact_set_sha256,
            })
        except P10CaptureJobConflict:
            return
        except P10PreviewV2CommandError:
            self._fail_current(job_id, True, "input_replay_failed")
        except Exception as exc:
            if self._cancel.is_set():
                self._interrupt(job_id)
                return
            changed = self._current_input_changed(request_document)
            code = "input_head_changed" if changed \
                else classify_p10_capture_failure(exc)
            self._fail_current(job_id, changed, code)

    def _progress(
        self, job_id: str, expected_total: int,
        value: P10RuntimeCaptureV2Progress,
    ) -> None:
        if type(value) is not P10RuntimeCaptureV2Progress \
                or value.total_case_count != expected_total \
                or value.state not in {"running", "completed"}:
            raise P10CaptureJobManagerError("Runtime progress is inconsistent")
        snapshot = self._jobs.load(job_id)
        current = value.completed_case_count
        append_progress = True
        if snapshot.status == "runtime_verified":
            if current != 0:
                raise P10CaptureJobManagerError("Runtime progress did not start at zero")
        elif snapshot.status == "capturing":
            old = snapshot.events[-1].document["progress"]
            if current == old["current"]:
                append_progress = False
            elif old["total"] != expected_total \
                    or current != old["current"] + 1:
                raise P10CaptureJobManagerError("Runtime progress is not contiguous")
        else:
            raise P10CaptureJobManagerError("Runtime progress state is stale")
        if value.state == "completed":
            if current != expected_total:
                raise P10CaptureJobManagerError("Runtime completion is premature")
        elif not append_progress:
            return
        if append_progress:
            snapshot = self._advance(
                snapshot, "capturing", current=current, total=expected_total)
        if value.state == "completed":
            self._advance(snapshot, "sealing")

    def _current_input_changed(self, request) -> bool:
        try:
            preview = self._compile(self._projects, request["package_id"])
        except Exception:
            return True
        return not _matches(request, preview)

    def _advance(self, snapshot, status, **payload) -> P10CaptureJobSnapshot:
        return self._jobs.append_event(
            snapshot.job_id, status,
            expected_previous_event_sha=snapshot.head_event_sha, **payload)

    def _fail_current(self, job_id, terminal, code) -> None:
        self._fail(self._jobs.load(job_id), terminal, code)

    def _fail(self, snapshot, terminal, code) -> None:
        if snapshot.status in ACTIVE_STATUSES:
            status = "failed_terminal" if terminal else "failed_retryable"
            self._advance(snapshot, status, failure_code=code)

    def _interrupt(self, job_id) -> None:
        try:
            snapshot = self._jobs.load(job_id)
            if snapshot.status in ACTIVE_STATUSES:
                self._advance(snapshot, "interrupted_retryable",
                              failure_code="manager_closed")
        except P10CaptureJobConflict:
            return

    def _require_open(self) -> None:
        if self._closed:
            raise P10CaptureJobManagerError("Capture manager is closed")

    def _runtime_environment(self) -> P10RuntimeEnvironment:
        with self._environment_lock:
            if self._environment_value is None:
                value = self._environment_loader(self._projects.state_root)
                if type(value) is not P10RuntimeEnvironment:
                    raise P10CaptureJobManagerError(
                        "Runtime environment value is invalid")
                self._environment_value = value
            return self._environment_value

def _expected(preview):
    if type(preview) is not P10PreviewV2CommandResult:
        raise P10CaptureJobManagerError("Preview compiler result is invalid")
    source = preview.document["source"]
    return (
        dict(source["current_p10_1_head"]),
        {"candidate_sha256": preview.capture_framing_candidate_sha256,
         "decision_sha256": preview.capture_framing_decision_sha256,
         "revision": preview.capture_framing_revision},
    )

def _matches(request, preview) -> bool:
    try:
        expected = _expected(preview)
        return request["package_id"] == preview.package_id \
            and request["expected_p10_1"] == expected[0] \
            and request["expected_framing"] == expected[1]
    except (KeyError, TypeError, P10CaptureJobManagerError):
        return False

def _require_result(request, preview, result) -> None:
    if type(result) is not P10RuntimeCaptureV2CommandResult \
            or result.package_id != request["package_id"] \
            or result.project_id != preview.project_id \
            or result.clip_id != preview.clip_id \
            or result.temporary_preview_v2_sha256 \
                != preview.temporary_preview_v2_sha256 \
            or result.case_count != preview.case_count:
        raise P10CaptureJobManagerError("Runtime result differs from Preview v2")
