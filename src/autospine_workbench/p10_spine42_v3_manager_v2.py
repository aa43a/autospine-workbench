"""Single-worker automatic P10.7a v2 Spine adapter orchestration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading

from .p10_capture_job_store import P10CaptureJobStore
from .p10_spine42_v3_auto_inputs_v2 import (
    P10Spine42V3AutoInputsV2, P10Spine42V3AutoInputsV2Error,
    load_verified_p10_spine42_v3_motion_v2,
    resolve_p10_spine42_v3_auto_inputs_v2,
)
from .p10_spine42_v3_commands_v2 import (
    P10Spine42V3CommandV2Error,
    compile_verified_body_sway_spine42_v3_v2_command,
)
from .p10_spine42_v3_job_v2 import (
    ACTIVE, P10Spine42V3JobStoreV2, P10Spine42V3JobV2Error,
)
from .p10_spine42_v3_result_v2 import (
    P10Spine42V3ResultV2Error, read_p10_spine42_v3_result_v2,
)


class P10Spine42V3ManagerV2Error(RuntimeError):
    pass


class _ReadOnlyCaptureJobs:
    def __init__(self, state_root):
        self._store = P10CaptureJobStore(state_root)

    def get(self, job_id):
        return self._store.load(job_id).public_document()


class P10Spine42V3ManagerV2:
    def __init__(self, projects):
        self._projects = projects
        try:
            self._store = P10Spine42V3JobStoreV2(projects.state_root)
            self._store.recover_interrupted()
        except Exception as exc:
            raise P10Spine42V3ManagerV2Error(
                "P10.7a v2 startup recovery failed"
            ) from exc
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="autospine-p10-spine42-v3-v2",
        )
        self._lock, self._cancel = threading.RLock(), threading.Event()
        self._futures, self._closed = {}, False

    def entry(self, job, safety, dynamic, motion):
        inputs = self._resolve(job, safety, dynamic, motion)
        latest = self._store.latest(job, safety, dynamic, motion)
        _require_same_inputs(latest, inputs)
        if latest is not None:
            return _response(inputs, latest)
        return {"ok": True, "status": "ready", **_address(inputs)}

    def submit(self, job, safety, dynamic, motion):
        with self._lock:
            if self._closed:
                raise P10Spine42V3ManagerV2Error("Manager is closed")
            inputs = self._resolve(job, safety, dynamic, motion)
            latest = self._store.latest(job, safety, dynamic, motion)
            _require_same_inputs(latest, inputs)
            if latest is not None and latest.status in ACTIVE | {"completed"}:
                return _response(inputs, latest)
            if latest is not None and latest.status == "failed_terminal":
                raise P10Spine42V3ManagerV2Error(
                    "Terminal P10.7a v2 failure cannot be retried"
                )
            row = self._store.create(
                inputs, attempt=1 if latest is None
                else latest.request["attempt"] + 1,
                previous_run_id=None if latest is None else latest.run_id,
            )
            self._futures[row.run_id] = self._executor.submit(
                self._run, row.run_id,
            )
            return _response(inputs, row)

    def get(self, job, safety, dynamic, motion, run_id):
        row = self._store.load(run_id)
        _require_binding(row, job, safety, dynamic, motion)
        return _response(_inputs_from_request(row.request), row)

    def result(self, job, safety, dynamic, motion, run_id):
        row = self._store.load(run_id)
        _require_binding(row, job, safety, dynamic, motion)
        if row.status != "completed":
            raise P10Spine42V3ManagerV2Error("Result is unavailable")
        try:
            return read_p10_spine42_v3_result_v2(
                self._projects.state_root, row,
            )
        except P10Spine42V3ResultV2Error as exc:
            raise P10Spine42V3ManagerV2Error(
                "P10.7a v2 historical exact readback failed"
            ) from exc

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._cancel.set()
            futures = tuple(self._futures.items())
        for _, future in futures:
            future.cancel()
        for run_id, _ in futures:
            self._fail(run_id, "manager_closed", False)
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _resolve(self, job, safety, dynamic, motion):
        return resolve_p10_spine42_v3_auto_inputs_v2(
            self._projects.state_root, job, safety, dynamic, motion,
        )

    def _run(self, run_id):
        try:
            row = self._running(run_id, "exact_motion_instance")
            inputs = self._resolve(*(row.request[key] for key in _ID_KEYS))
            _require_same_inputs(row, inputs)
            motion = load_verified_p10_spine42_v3_motion_v2(
                self._projects.state_root, inputs,
            )
            self._running(run_id, "source_adapter")
            self._running(run_id, "spine_adapter")
            result = compile_verified_body_sway_spine42_v3_v2_command(
                _ReadOnlyCaptureJobs(self._projects.state_root),
                self._projects, motion,
            )
            self._running(run_id, "publication", current=1)
            row = self._running(run_id, "parent_exact_readback")
            sealed = self._verify_parent(row, inputs, result)
            row = self._store.load(run_id)
            self._store.append(
                run_id, "completed", "completed",
                expected_previous=row.head_sha256, current=1, total=1,
                result=sealed,
            )
        except P10Spine42V3AutoInputsV2Error as exc:
            self._fail(run_id, exc.failure_code, exc.terminal)
        except P10Spine42V3CommandV2Error:
            self._fail(run_id, "spine_adapter_compile_failed", False)
        except Exception:
            self._fail(run_id, "parent_validation_failed", True)
        finally:
            with self._lock:
                self._futures.pop(run_id, None)

    def _running(self, run_id, stage, current=0):
        if self._cancel.is_set():
            raise P10Spine42V3ManagerV2Error("Manager closed")
        row = self._store.load(run_id)
        return self._store.append(
            run_id, "running", stage, expected_previous=row.head_sha256,
            current=current, total=1,
        )

    def _verify_parent(self, row, inputs, result):
        current = self._resolve(*(getattr(inputs, key) for key in _ID_KEYS))
        payload = result.document
        if current.identity != inputs.identity \
                or not _same_request(row.request, inputs) \
                or result.mode != "compiled" \
                or result.project_id != inputs.project_id \
                or payload.get("project_id") != inputs.project_id \
                or payload.get("address") != {
                    "skeleton_json_sha256": result.skeleton_json_sha256,
                    "bundle_sha256": result.bundle_sha256,
                } or payload.get("inventory") != list(result.inventory) \
                or payload.get("verification") != {
                    "status": "passed", "exact_readback": True,
                } or type(result.reused) is not bool \
                or _contains_path(payload):
            raise P10Spine42V3ManagerV2Error(
                "P10.7a v2 exact readback differs"
            )
        return {
            "project_id": result.project_id, "clip_id": result.clip_id,
            "skeleton_json_sha256": result.skeleton_json_sha256,
            "bundle_sha256": result.bundle_sha256,
            "run_document_sha256": result.run_document_sha256,
            "report_sha256": result.report_sha256,
            "inventory": list(result.inventory), "reused": result.reused,
        }

    def _fail(self, run_id, code, terminal):
        try:
            row = self._store.load(run_id)
            if row.status in ACTIVE:
                self._store.append(
                    run_id, "failed_terminal" if terminal
                    else "failed_retryable", "failed",
                    expected_previous=row.head_sha256, failure_code=code,
                )
        except P10Spine42V3JobV2Error:
            pass


_ID_KEYS = ("job_id", "safety_run_id", "dynamic_run_id", "motion_run_id")


def _require_binding(row, *ids):
    if any(row.request[key] != value for key, value in zip(_ID_KEYS, ids)):
        raise P10Spine42V3ManagerV2Error(
            "P10.7a v2 run belongs to another source"
        )


def _require_same_inputs(row, inputs):
    if row is not None and not _same_request(row.request, inputs):
        raise P10Spine42V3ManagerV2Error(
            "Current P10.7a v2 inputs differ from the latest attempt"
        )


def _same_request(request, inputs):
    return all(request.get(key) == value for key, value in inputs.identity.items())


def _inputs_from_request(request):
    return P10Spine42V3AutoInputsV2(**{
        key: request[key] for key in P10Spine42V3AutoInputsV2.__slots__
    })


def _address(inputs):
    return {key: inputs.identity[key] for key in (*_ID_KEYS, "project_id")}


def _response(inputs, row):
    return {"ok": True, "status": row.status, **_address(inputs),
            "run": row.public_document()}


def _contains_path(value):
    if isinstance(value, dict):
        return any(key == "path" or key.endswith("_path")
                   or _contains_path(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_path(item) for item in value)
    return False


__all__ = ["P10Spine42V3ManagerV2", "P10Spine42V3ManagerV2Error"]
