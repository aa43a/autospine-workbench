"""Durable motion uploads; decoding runs in cancellable bounded child processes."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from threading import Event, RLock
import time
from uuid import uuid4

from ..safe_input_files import read_real_file
from .motion_intake_process import failure_reason, read_progress, terminate_tree
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document

ACTIVE = {'pending', 'running'}
MAX_UPLOAD = 64 * 1024 * 1024


class MotionIntakeJobs:
    def __init__(self, projects):
        self.projects = projects
        self.character_manager = None
        self.root = Path(projects.state_root) / 'jobs/motion-intake-v1'
        self.state_root = Path(projects.state_root).resolve()
        self.blender = os.environ.get('AUTOSPINE_BLENDER') or shutil.which('blender') or ''
        self._lock = RLock()
        self._jobs, self._cancel, self._closed = {}, {}, False
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='motion-intake')

    def folder(self, job, create=False):
        if not isinstance(job, str) or not re.fullmatch(r'motion-[a-f0-9]{32}', job):
            raise PipelineRunError('motion_job_invalid')
        return directory(self.root / job, create=create)

    def overview(self):
        jobs = []
        if self.root.exists():
            paths = sorted(self.root.glob('motion-*/request.json'),
                           key=lambda p: p.stat().st_mtime_ns, reverse=True)
            # Historical task cards are a journal, not fresh character verification.
            # Verify source state on opening/retrying/downloading a specific target.
            jobs = [self.get(path.parent.name, check_current=False) for path in paths]
        return dict(authority='none', jobs=jobs, formats=['fbx', 'bvh'],
                    blender_available=bool(self.blender and Path(self.blender).is_file()),
                    kimodo_generation='not_connected', npz_import='not_connected')

    def upload(self, stream, size, name, view):
        suffix = Path(name).suffix.lower() if isinstance(name, str) else ''
        if suffix not in ('.fbx', '.bvh') or len(name) > 180 or any(c in name for c in '/\\\r\n\0'):
            raise PipelineRunError('motion_filename_invalid')
        if type(size) is not int or not 16 <= size <= MAX_UPLOAD:
            raise PipelineRunError('motion_file_limit')
        if view not in ('front', 'side'):
            raise PipelineRunError('motion_view_invalid')
        with self._lock:
            if self._closed or sum(j['status'] in ACTIVE for j in self._jobs.values()) >= 2:
                raise PipelineRunError('motion_queue_full')
            job = 'motion-' + uuid4().hex
            folder = self.folder(job, True)
            value = dict(job_id=job, name=name, format=suffix[1:], view=view,
                         status='pending', step='uploading', authority='none')
            self._jobs[job] = value
            self._cancel[job] = Event()
        try:
            digest = sha256()
            with (folder / ('source' + suffix)).open('xb') as target:
                remaining = size
                while remaining:
                    raw = stream.read(min(1 << 20, remaining))
                    if not raw:
                        raise PipelineRunError('motion_upload_incomplete')
                    target.write(raw)
                    digest.update(raw)
                    remaining -= len(raw)
            request = dict(value, source_sha256=digest.hexdigest(), byte_length=size)
            publish_document(folder / 'request.json', request, staging=folder / 'staging')
            with self._lock:
                value.update(source_sha256=request['source_sha256'], step='queued')
                self._pool.submit(self._execute, job)
                return deepcopy(value)
        except Exception:
            with self._lock:
                value.update(status='failed', reason_code='motion_upload_failed')
            raise

    def get(self, job, *, check_current=True):
        with self._lock:
            folder = self.folder(job)
            if job in self._jobs:
                value = deepcopy(self._jobs[job])
                if value['status'] == 'running':
                    value['step'] = read_progress(folder) or value['step']
            else:
                request = read_document(folder / 'request.json')
                if (folder / 'result.json').exists():
                    value = read_document(folder / 'result.json')
                else:
                    public = {k: request[k] for k in ('job_id', 'kind', 'name', 'format', 'view', 'project_id') if k in request}
                    value = dict(public, status='interrupted', step='interrupted',
                                 authority='none', reason_code='motion_import_interrupted')
        if check_current and value.get('kind') == 'adapt' and value['status'] == 'succeeded':
            from .motion_target_jobs import assert_current
            try:
                assert_current(self, read_document(folder / 'request.json'))
            except (OSError, RuntimeError, ValueError, KeyError):
                value.update(status='outdated', reason_code='motion_target_character_or_source_changed')
        return value

    def preview(self, job):
        result = self.get(job)
        if result['status'] != 'succeeded':
            raise PipelineRunError('motion_preview_unavailable')
        raw = read_real_file(self.folder(job) / 'preview.json', 8 * 1024 * 1024, 'motion preview')
        if sha256(raw).hexdigest() != result['result']['preview_sha256']:
            raise PipelineRunError('motion_preview_changed')
        return raw

    def retry(self, job):
        old = self.get(job)
        if old['status'] in ACTIVE:
            raise PipelineRunError('motion_job_running')
        request = read_document(self.folder(job) / 'request.json')
        if request.get('kind') == 'adapt':
            from .motion_target_jobs import submit
            return submit(self, request['source_job_id'], {k: request[k] for k in ('project_id', 'character_job_id')})
        raw = read_real_file(self.folder(job) / ('source.' + request['format']), MAX_UPLOAD, 'motion source')
        if sha256(raw).hexdigest() != request['source_sha256']:
            raise PipelineRunError('motion_source_changed')
        return self.upload(BytesIO(raw), len(raw), request['name'], request['view'])

    def cancel(self, job):
        with self._lock:
            value = self.get(job)
            if value['status'] in ACTIVE:
                self._cancel[job].set()
                self._jobs[job]['cancel_requested'] = True
            return self.get(job)

    def _execute(self, job):
        folder = self.folder(job)
        process = None
        try:
            if self._cancel[job].is_set():
                raise PipelineRunError('motion_canceled')
            with self._lock:
                self._jobs[job].update(status='running', step='verify_source')
            request = read_document(folder / 'request.json')
            target = request.get('kind') == 'adapt'
            if target:
                from .motion_target_jobs import assert_current
                assert_current(self, request)
            module = 'motion_target_worker' if target else 'motion_intake_worker'
            extra = str(self.projects.workspace_root.resolve()) if target else self.blender
            command = [sys.executable, '-m', 'autospine_workbench.automation.' + module,
                       str(folder), str(self.state_root), extra]
            with (folder / 'worker.log').open('wb') as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=os.name != 'nt')
                started = time.monotonic()
                while process.poll() is None:
                    if self._cancel[job].wait(.15):
                        raise PipelineRunError('motion_canceled')
                    if time.monotonic() - started > (900 if target else 240):
                        raise PipelineRunError('motion_decode_timeout')
            if self._cancel[job].is_set():
                raise PipelineRunError('motion_canceled')
            if process.returncode:
                raise PipelineRunError(failure_reason(folder / 'worker.log'))
            result = read_document(folder / 'worker-result.json')
            if target:
                assert_current(self, request)
            outcome = dict(status='succeeded', step='complete', result=result)
        except Exception as exc:
            reason = getattr(exc, 'reason_code', 'motion_decode_failed')
            outcome = dict(status='canceled' if reason == 'motion_canceled' else 'failed', reason_code=reason)
        finally:
            try:
                if process is not None:
                    terminate_tree(process)
            except (OSError, subprocess.SubprocessError):
                outcome = dict(status='failed', reason_code='motion_termination_failed')
            with self._lock:
                value = dict(self._jobs[job], **outcome)
                publish_document(folder / 'result.json', value, staging=folder / 'staging')
                self._jobs[job] = value

    def close(self):
        with self._lock:
            self._closed = True
            for cancel in self._cancel.values():
                cancel.set()
        self._pool.shutdown(wait=True)
