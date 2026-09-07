"""Bounded asynchronous setup jobs; durable requests survive server restarts."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
from pathlib import Path
import re
from threading import Event, RLock
from uuid import uuid4

from ..manifest_artifacts import require_safe_token
from .pipeline_application import PipelineApplication
from .pipeline_profile import build_pipeline_profile
from .pipeline_run import PipelineRunError
from .pipeline_run_validation import require_sha
from .preview_download import export_preview
from .storage_io import directory, publish_document, read_document
from .web_job_contract import validate_job, validate_request
from .target_version import DEFAULT_TARGET_VERSION, require_target_version

SCHEMA = "autospine.pipeline-web-job/v1"


class PipelineWebJobs:
    def __init__(self, project_store):
        self.application = PipelineApplication(project_store)
        self.root = Path(project_store.state_root) / "jobs" / "pipeline-web-v1"
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="region-preview")
        self._lock, self._active, self._closed = RLock(), {}, False

    def _path(self, job_id, *, create=False):
        if type(job_id) is not str or not re.fullmatch(r"job-[0-9a-f]{32}", job_id):
            raise PipelineRunError("pipeline_job_id_invalid")
        return directory(self.root / job_id, create=create)

    def submit(self, project_id, profile, expected_resolved_sha256, *, resume=True,
               target_version=DEFAULT_TARGET_VERSION):
        require_safe_token(project_id, "project")
        build_pipeline_profile(profile)
        require_sha(expected_resolved_sha256)
        if type(resume) is not bool:
            raise PipelineRunError("pipeline_request_invalid")
        target_version = require_target_version(target_version)
        request = {"project_id": project_id, "profile": profile,
                   "expected_resolved_sha256": expected_resolved_sha256, "resume": resume,
                   "target_version": target_version}
        with self._lock:
            if self._closed:
                raise PipelineRunError("pipeline_manager_closed")
            for active in self._active.values():
                if active["request"] == request:
                    return deepcopy(active["response"])
            if len(self._active) >= 8:
                raise PipelineRunError("pipeline_queue_full")
            job_id = "job-" + uuid4().hex
            path = self._path(job_id, create=True)
            publish_document(path / "request.json", request, staging=path / "staging")
            response = _response(job_id, project_id, "pending", target_version=target_version)
            self._active[job_id] = {"request": request, "response": response, "cancel": Event()}
            self._pool.submit(self._execute, job_id)
            return deepcopy(response)

    def get(self, project_id, job_id):
        with self._lock:
            active = self._active.get(job_id)
            if active:
                if active["request"]["project_id"] != project_id:
                    raise PipelineRunError("pipeline_job_not_found")
                return deepcopy(active["response"])
            path = self._path(job_id)
            request = read_document(path / "request.json")
            target_version = validate_request(request)
            if request.get("project_id") != project_id:
                raise PipelineRunError("pipeline_job_not_found")
            if not (path / "result.json").exists():
                return _response(job_id, project_id, "blocked", reason_code="pipeline_interrupted",
                                 target_version=target_version)
            result = read_document(path / "result.json")
            validate_job(result, job_id, request)
            if result["status"] == "succeeded" and self.application.runs.load(
                result["run"]["run_id"]
            ) != result["run"]:
                raise PipelineRunError("pipeline_storage_invalid")
            return result

    def cancel(self, project_id, job_id):
        with self._lock:
            result = self.get(project_id, job_id)
            active = self._active.get(job_id)
            if active:
                active["cancel"].set()
                active["response"]["cancel_requested"] = True
                return deepcopy(active["response"])
            return result

    def _execute(self, job_id):
        with self._lock:
            active = self._active[job_id]
            active["response"]["status"] = "running"
        request, canceled = active["request"], active["cancel"].is_set
        target_version = validate_request(request)
        def response(status, **fields):
            return _response(job_id, request["project_id"], status,
                             target_version=target_version, **fields)
        path = self._path(job_id)
        try:
            if canceled():
                result = response("canceled")
            else:
                run = self.application.preview(
                    request["project_id"], request["profile"], resume=request["resume"],
                    expected_resolved_sha256=request["expected_resolved_sha256"],
                    cancel_requested=canceled,
                    target_version=target_version,
                )
                result = response(run["status"], run=run)
                if run["status"] in {"pending", "running"}:
                    result = response("blocked", reason_code="pipeline_resume_required")
                if run["status"] == "succeeded":
                    export_preview(self.application.state_root, run, path / "preview.zip", editor_import=False)
                    result["zip_sha256"] = hashlib.sha256((path / "preview.zip").read_bytes()).hexdigest()
        except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
            reason = getattr(exc, "reason_code", "pipeline_step_failed")
            if not isinstance(reason, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", reason):
                reason = "pipeline_step_failed"
            result = response("failed", reason_code=reason)
        with self._lock:
            # Late cancellation wins the UI job, even if pure compilation just completed.
            if canceled():
                result = response("canceled")
            try:
                publish_document(path / "result.json", result, staging=path / "staging")
            finally:
                self._active.pop(job_id, None)

    def close(self):
        with self._lock:
            self._closed = True
            for active in self._active.values():
                active["cancel"].set()
        self._pool.shutdown(wait=True)


def _response(job_id, project_id, status, *, target_version="4.2", **fields):
    return {"schema": SCHEMA, "job_id": job_id, "project_id": project_id,
            "status": status, "authority": "none", "target_version": target_version, **fields}
