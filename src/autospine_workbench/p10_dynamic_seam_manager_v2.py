"""Attempt-aware parent orchestration for automatic P10.5d v2."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading

from .body_sway_dynamic_seam_bundle_reader_v2 import (
    BodySwayDynamicSeamBundleReaderV2,
)
from .p10_dynamic_seam_auto_inputs_v2 import (
    P10DynamicSeamAutoInputsV2Error, resolve_p10_dynamic_seam_auto_inputs_v2,
)
from .p10_dynamic_seam_job_v2 import (
    ACTIVE, P10DynamicSeamJobStoreV2, P10DynamicSeamJobV2Error,
)
from .p10_dynamic_seam_worker_process_v2 import (
    P10DynamicSeamWorkerV2Error, run_p10_dynamic_seam_worker_v2,
)


class P10DynamicSeamManagerV2Error(RuntimeError):
    pass


class P10DynamicSeamManagerV2:
    def __init__(self, projects):
        self._projects = projects
        try:
            self._store = P10DynamicSeamJobStoreV2(projects.state_root)
            self._store.recover_interrupted()
        except Exception as exc:
            raise P10DynamicSeamManagerV2Error(
                "P10.5d startup recovery failed"
            ) from exc
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="autospine-p10-seam-v2",
        )
        self._lock, self._cancel = threading.RLock(), threading.Event()
        self._futures, self._closed = {}, False

    def entry(self, job_id, safety_run_id):
        inputs = resolve_p10_dynamic_seam_auto_inputs_v2(
            self._projects.state_root, job_id, safety_run_id,
        )
        latest = self._store.latest(job_id, safety_run_id)
        if latest is not None and not _same_inputs(latest.request, inputs):
            raise P10DynamicSeamManagerV2Error(
                "Current P10.5d inputs differ from the latest attempt"
            )
        if latest is not None:
            return _response(job_id, safety_run_id, latest)
        return {"ok": True, "status": "ready", "job_id": job_id,
                "safety_run_id": safety_run_id}

    def submit(self, job_id, safety_run_id):
        with self._lock:
            if self._closed:
                raise P10DynamicSeamManagerV2Error("Manager is closed")
            inputs = resolve_p10_dynamic_seam_auto_inputs_v2(
                self._projects.state_root, job_id, safety_run_id,
            )
            latest = self._store.latest(job_id, safety_run_id)
            if latest is not None and not _same_inputs(
                latest.request, inputs,
            ):
                raise P10DynamicSeamManagerV2Error(
                    "Current P10.5d inputs differ from the latest attempt"
                )
            if latest is not None and latest.status in ACTIVE:
                return _response(job_id, safety_run_id, latest)
            if latest is not None and latest.status == "completed":
                return _response(job_id, safety_run_id, latest)
            if latest is not None and latest.status == "failed_terminal":
                raise P10DynamicSeamManagerV2Error(
                    "Terminal P10.5d failure cannot be retried"
                )
            snapshot = self._store.create(
                inputs, attempt=1 if latest is None
                else latest.request["attempt"] + 1,
                previous_run_id=None if latest is None else latest.run_id,
            )
            self._futures[snapshot.run_id] = self._executor.submit(
                self._run, snapshot.run_id,
            )
            return _response(job_id, safety_run_id, snapshot)

    def get(self, job_id, safety_run_id, run_id):
        row = self._store.load(run_id)
        _require_binding(row, job_id, safety_run_id)
        return _response(job_id, safety_run_id, row)

    def result(self, job_id, safety_run_id, run_id):
        row = self._store.load(run_id)
        _require_binding(row, job_id, safety_run_id)
        if row.status != "completed":
            raise P10DynamicSeamManagerV2Error("Result is unavailable")
        sealed = row.events[-1]["result"]
        verified = BodySwayDynamicSeamBundleReaderV2(
            self._projects.state_root
        ).load(sealed["project_id"], sealed["probe_sha256"],
               sealed["bundle_sha256"])
        return _public_result(row, verified)

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

    def _run(self, run_id):
        try:
            row = self._store.load(run_id)
            row = self._store.append(
                run_id, "running", "compile_segments",
                expected_previous=row.head_sha256,
            )
            result = run_p10_dynamic_seam_worker_v2(
                run_id, self._projects.state_root,
                self._projects.workspace_root,
                on_progress=lambda stage, current, total:
                    self._progress(run_id, stage, current, total),
                cancel_event=self._cancel,
            )
            row = self._store.load(run_id)
            row = self._store.append(
                run_id, "running", "parent_exact_readback",
                expected_previous=row.head_sha256,
            )
            self._verify_parent(row, result)
            row = self._store.load(run_id)
            self._store.append(
                run_id, "completed", "completed",
                expected_previous=row.head_sha256, current=1, total=1,
                result=result,
            )
        except P10DynamicSeamWorkerV2Error as exc:
            self._fail(run_id, exc.failure_code, exc.terminal)
        except P10DynamicSeamAutoInputsV2Error as exc:
            self._fail(run_id, exc.failure_code, exc.terminal)
        except Exception:
            self._fail(run_id, "parent_validation_failed", True)
        finally:
            with self._lock:
                self._futures.pop(run_id, None)

    def _progress(self, run_id, stage, current, total):
        if self._cancel.is_set():
            raise P10DynamicSeamManagerV2Error("Manager closed")
        row = self._store.load(run_id)
        if row.status != "running":
            raise P10DynamicSeamManagerV2Error("Progress target stale")
        prior = row.events[-1]
        stride = max(1, total // 50)
        if prior["stage"] == stage and current != total \
                and current - prior["progress"]["current"] < stride:
            return
        self._store.append(run_id, "running", stage,
                           expected_previous=row.head_sha256,
                           current=current, total=max(1, total))

    def _verify_parent(self, row, result):
        request = row.request
        current = resolve_p10_dynamic_seam_auto_inputs_v2(
            self._projects.state_root, request["job_id"],
            request["safety_run_id"],
        )
        if current.identity != {key: request[key]
                for key in current.identity}:
            raise P10DynamicSeamManagerV2Error("Current heads changed")
        verified = BodySwayDynamicSeamBundleReaderV2(
            self._projects.state_root
        ).load(result["project_id"], result["probe_sha256"],
               result["bundle_sha256"])
        source = verified.source
        if result != {
                "project_id": verified.project_id,
                "clip_id": verified.clip_id,
                "probe_sha256": verified.probe_sha256,
                "bundle_sha256": verified.bundle_sha256,
                "source_set_sha256": verified.source_set_sha256,
                "source_document_sha256": verified.source_document_sha256,
                "probe_status": verified.probe["status"],
            } or verified.project_id != request["project_id"] \
                or source["body_sway_continuous_preview_proof_v2_sha256"] \
                    != request["continuous_proof_sha256"] \
                or source["reviewed_seam_anchor_set_v1_sha256"] \
                    != request["reviewed_set_sha256"] \
                or source["reviewed_seam_anchor_set_v1_bundle_sha256"] \
                    != request["reviewed_set_bundle_sha256"] \
                or verified.probe["release_gate"]["status"] != "blocked" \
                or verified.probe["claims"]["release_authority"]:
            raise P10DynamicSeamManagerV2Error("Bundle input closure differs")

    def _fail(self, run_id, code, terminal):
        try:
            row = self._store.load(run_id)
            if row.status in ACTIVE:
                self._store.append(
                    run_id, "failed_terminal" if terminal
                    else "failed_retryable", "failed",
                    expected_previous=row.head_sha256, failure_code=code,
                )
        except P10DynamicSeamJobV2Error:
            pass


def _require_binding(row, job_id, safety_run_id):
    if row.request["job_id"] != job_id \
            or row.request["safety_run_id"] != safety_run_id:
        raise P10DynamicSeamManagerV2Error("Run belongs to another source")


def _same_inputs(request, inputs):
    return all(request.get(key) == value
               for key, value in inputs.identity.items())


def _response(job_id, safety_run_id, row):
    return {"ok": True, "status": row.status, "job_id": job_id,
            "safety_run_id": safety_run_id, "run": row.public_document()}


def _public_result(row, verified):
    probe, sealed = verified.probe, row.events[-1]["result"]
    return {
        "ok": True, "status": "completed",
        "job_id": row.request["job_id"],
        "safety_run_id": row.request["safety_run_id"],
        "run": row.public_document(), "project_id": verified.project_id,
        "clip_id": verified.clip_id,
        "probe": {"sha256": verified.probe_sha256,
                  "status": probe["status"], "summary": probe["summary"],
                  "relationships": _relationship_projection(probe)},
        "bundle": {key: sealed[key] for key in (
            "source_set_sha256", "source_document_sha256",
            "probe_sha256", "bundle_sha256")},
        "claims": probe["claims"],
        "release_gate": {"status": "blocked", "reason_codes":
                         probe["release_gate"]["reason_codes"]},
        "permanent_current_authority_claimed": False,
        "release_authority_granted": False,
    }


def _relationship_projection(probe):
    grouped = {}
    for segment in probe["segments"]:
        for item in segment["relationships"]:
            row = grouped.setdefault(item["relationship_id"], {
                "relationship_id": item["relationship_id"],
                "segment_count": 0, "status": "finite_upper_bound",
                "max_squared_anchor_residual_upper_px2": None,
                "gap_proxy": {"model": item["gap_proxy"]["model"],
                    "max_squared_upper_px2": None,
                    "raster_gap_claimed": False},
                "overlap": {"status": "not_evaluated",
                    "raster_overlap_claimed": False},
                "reason_codes": set(),
            })
            row["segment_count"] += 1
            value = item["anchor_residual"]["max_squared_upper_px2"]
            if value is None:
                row["status"] = "indeterminate"
            else:
                old = row["max_squared_anchor_residual_upper_px2"]
                row["max_squared_anchor_residual_upper_px2"] = value \
                    if old is None else max(old, value)
                row["gap_proxy"]["max_squared_upper_px2"] = \
                    row["max_squared_anchor_residual_upper_px2"]
            row["reason_codes"].update(segment["reason_codes"])
    return [{**row, "reason_codes": sorted(row["reason_codes"])}
            for _, row in sorted(grouped.items())]


__all__ = ["P10DynamicSeamManagerV2", "P10DynamicSeamManagerV2Error"]
