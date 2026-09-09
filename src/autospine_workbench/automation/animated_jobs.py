"""Bounded, durable candidate-animation jobs; no release authority."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
from pathlib import Path, PurePosixPath
import re
from threading import Event, RLock
from uuid import uuid4
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from ..manifest_artifacts import require_safe_token
from .pipeline_run import PipelineRunError
from .pipeline_run_validation import require_sha
from .storage_io import directory, publish_document, read_document

SCHEMA = "autospine.animated-web-job/v1"
STATUSES = {"pending", "running", "needs_review", "succeeded", "blocked", "failed", "canceled"}


def safe_file(name):
    if type(name) is not str or not re.fullmatch(r"[A-Za-z0-9_./-]{1,240}", name):
        raise PipelineRunError("animated_file_invalid")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in name.split("/")) \
            or path.suffix not in {".json", ".atlas", ".png"}:
        raise PipelineRunError("animated_file_invalid")
    return name


def validate_request(request):
    if type(request) is not dict or set(request) != {
        "project_id", "expected_resolved_sha256", "clip", "resume"
    }:
        raise PipelineRunError("pipeline_request_invalid")
    require_safe_token(request["project_id"], "project")
    require_sha(request["expected_resolved_sha256"])
    require_safe_token(request["clip"], "clip")
    if type(request["resume"]) is not bool:
        raise PipelineRunError("pipeline_request_invalid")


class AnimatedWebJobs:
    def __init__(self, project_store, *, application=None):
        if application is None:
            from .animated_application import AnimatedApplication
            application = AnimatedApplication(project_store)
        self.application = application
        self.root = Path(project_store.state_root) / "jobs" / "animated-web-v1"
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="animated-preview")
        self._lock, self._active, self._closed = RLock(), {}, False

    def _path(self, job_id, *, create=False):
        if type(job_id) is not str or not re.fullmatch(r"job-[0-9a-f]{32}", job_id):
            raise PipelineRunError("pipeline_job_id_invalid")
        return directory(self.root / job_id, create=create)

    def submit(self, project_id, expected_resolved_sha256, clip, resume=True):
        request = dict(project_id=project_id, expected_resolved_sha256=expected_resolved_sha256,
                       clip=clip, resume=resume)
        validate_request(request)
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
            response = _response(job_id, project_id, "pending")
            self._active[job_id] = dict(request=request, response=response, cancel=Event())
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
            validate_request(request)
            if request["project_id"] != project_id:
                raise PipelineRunError("pipeline_job_not_found")
            if not (path / "result.json").exists():
                return _response(job_id, project_id, "blocked", reason_code="pipeline_interrupted")
            result = read_document(path / "result.json")
            if result.get("schema") != SCHEMA or result.get("job_id") != job_id \
                    or result.get("project_id") != project_id or result.get("authority") != "none" \
                    or result.get("target_version") != "4.3.26" \
                    or result.get("status") not in STATUSES:
                raise PipelineRunError("pipeline_storage_invalid")
            if "run" in result:
                _validate_run(result["run"], request)
                if result["status"] != result["run"]["status"]:
                    raise PipelineRunError("pipeline_storage_invalid")
            return result

    def cancel(self, project_id, job_id):
        with self._lock:
            result = self.get(project_id, job_id)
            if job_id in self._active:
                active = self._active[job_id]
                active["cancel"].set()
                active["response"]["cancel_requested"] = True
                result = deepcopy(active["response"])
            return result

    def files(self, project_id, job_id):
        result = self.get(project_id, job_id)
        run = result.get("run", {})
        if result["status"] not in {"succeeded", "needs_review"} or run.get("preview_available") is not True:
            raise PipelineRunError("pipeline_preview_not_ready")
        files = self.application.verified_files(project_id, run)
        if type(files) is not dict or not files:
            raise PipelineRunError("pipeline_artifact_invalid")
        for name, raw in files.items():
            safe_file(name)
            if type(raw) is not bytes:
                raise PipelineRunError("pipeline_artifact_invalid")
        return files

    def download(self, project_id, job_id):
        files = self.files(project_id, job_id)
        output = BytesIO()
        with ZipFile(output, "w", compression=ZIP_STORED) as archive:
            for name in sorted(files):
                archive.writestr(ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), files[name])
        return output.getvalue()

    def file(self, project_id, job_id, name):
        safe_file(name)
        result = self.get(project_id, job_id)
        run = result.get("run", {})
        if result["status"] not in {"succeeded", "needs_review"} or run.get("preview_available") is not True:
            raise PipelineRunError("pipeline_preview_not_ready")
        return self.application.verified_file(project_id, run, name)

    def _execute(self, job_id):
        with self._lock:
            active = self._active[job_id]
            active["response"]["status"] = "running"
        request, canceled = active["request"], active["cancel"].is_set
        path = self._path(job_id)

        def progress(value):
            with self._lock:
                active["response"]["progress"] = deepcopy(value)

        try:
            if canceled():
                result = _response(job_id, request["project_id"], "canceled")
            else:
                run = self.application.preview(**request, cancel_requested=canceled, progress=progress)
                _validate_run(run, request)
                result = _response(job_id, request["project_id"], run["status"], run=run)
                if run["status"] in {"pending", "running"}:
                    result = _response(job_id, request["project_id"], "blocked",
                                       reason_code="pipeline_resume_required")
        except Exception as exc:
            reason = getattr(exc, "reason_code", "pipeline_step_failed")
            if type(reason) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", reason):
                reason = "pipeline_step_failed"
            result = _response(job_id, request["project_id"], "failed", reason_code=reason)
        with self._lock:
            if canceled():
                result = _response(job_id, request["project_id"], "canceled")
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


def _validate_run(run, request):
    if type(run) is not dict or run.get("schema") != "autospine.animated-pipeline-run/v1" \
            or run.get("project_id") != request["project_id"] or run.get("authority") != "none" \
            or run.get("clip") != request["clip"] \
            or run.get("status") not in STATUSES:
        raise PipelineRunError("pipeline_storage_invalid")
    sources = run.get("source_addresses", run.get("sources", {}))
    if sources.get("resolved_project_sha256") != request["expected_resolved_sha256"]:
        raise PipelineRunError("project_snapshot_stale")


def _response(job_id, project_id, status, **fields):
    return dict(schema=SCHEMA, job_id=job_id, project_id=project_id, status=status,
                authority="none", target_version="4.3.26", **fields)
