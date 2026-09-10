"""Durable local PSD uploads, bounded decoder subprocess, atomic audit publication."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from threading import RLock
from uuid import uuid4
from .storage_io import directory, publish_document, read_document
from .pipeline_run import PipelineRunError
from .psd_intake_worker import inspect_header, MAX_FILE_BYTES


class PsdImportJobs:
    def __init__(self, projects):
        self.projects = projects
        self.root = projects.state_root / 'jobs/psd-import-v1'
        self._lock = RLock()
        self._jobs = {}
        self._closed = False
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='psd-import')

    def folder(self, job, create=False):
        if not re.fullmatch(r'import-[a-f0-9]{32}', job):
            raise PipelineRunError('psd_job_invalid')
        return directory(self.root / job, create=create)

    def upload(self, stream, size, name):
        if not isinstance(name, str) or not name.lower().endswith('.psd') or len(name) > 180 or any(c in name for c in '/\\\r\n\0'):
            raise PipelineRunError('psd_filename_invalid')
        if not 26 <= size <= MAX_FILE_BYTES:
            raise PipelineRunError('psd_file_limit')
        with self._lock:
            if self._closed or sum(v['status'] in ('pending', 'running') for v in self._jobs.values()) >= 2:
                raise PipelineRunError('psd_queue_full')
            job = 'import-' + uuid4().hex
            folder = self.folder(job, True)
            value = dict(job_id=job, status='pending', step='queued', authority='none')
            self._jobs[job] = value
        try:
            digest = sha256()
            with (folder / 'source.psd').open('xb') as target:
                remaining = size
                while remaining:
                    raw = stream.read(min(1 << 20, remaining))
                    if not raw:
                        raise PipelineRunError('psd_upload_incomplete')
                    remaining -= len(raw)
                    target.write(raw)
                    digest.update(raw)
            inspect_header(folder / 'source.psd')
            request = dict(job_id=job, name=name, source_sha256=digest.hexdigest())
            publish_document(folder / 'request.json', request, staging=folder / 'staging')
            with self._lock:
                self._pool.submit(self._execute, job, request)
                return deepcopy(value)
        except Exception:
            with self._lock:
                self._jobs[job].update(status='failed', reason_code='psd_upload_invalid')
            raise

    def get(self, job):
        with self._lock:
            if job in self._jobs:
                return deepcopy(self._jobs[job])
            folder = self.folder(job)
            read_document(folder / 'request.json')
            if (folder / 'result.json').exists():
                return read_document(folder / 'result.json')
            return dict(job_id=job, status='failed', step='queued', authority='none', reason_code='psd_import_interrupted')

    def _execute(self, job, request):
        folder = self.folder(job)
        try:
            with self._lock:
                self._jobs[job].update(status='running', step='parsing')
            project = 'imported-' + request['source_sha256']
            destination = self.projects.audit_root / project
            directory(self.projects.audit_root, create=True)
            if not destination.exists():
                command = [sys.executable, '-m', 'autospine_workbench.automation.psd_intake_worker',
                           '--input', str(folder / 'source.psd'), '--output', str(folder / 'decoded')]
                result = subprocess.run(command, capture_output=True, timeout=180, cwd=str(Path(__file__).resolve().parents[3]))
                if result.returncode:
                    try:
                        reason = json.loads(result.stdout).get('reason_code', 'psd_decode_failed')
                    except (ValueError, TypeError):
                        reason = 'psd_decode_failed'
                    raise PipelineRunError(reason)
                with self._lock:
                    self._jobs[job]['step'] = 'registering'
                # Directory rename publishes audit and textures together on the same volume.
                os.rename(folder / 'decoded', destination)
            audit = json.loads((destination / 'audit.json').read_text(encoding='utf-8'))
            if audit.get('sha256') != request['source_sha256']:
                raise PipelineRunError('psd_source_conflict')
            self.projects.get_project(project)
            from .asset_library import AssetLibrary
            library = AssetLibrary(self.projects)
            if library.metadata(project)['revision'] == 0:
                library.change(project, dict(action='rename', expected_revision=0, name=request['name'][:-4][:120] or 'PSD 项目'))
            with self._lock:
                self._jobs[job].update(status='succeeded', step='complete', project_id=project)
        except Exception as exc:
            reason = 'psd_decode_timeout' if isinstance(exc, subprocess.TimeoutExpired) else getattr(exc, 'reason_code', 'psd_import_failed')
            with self._lock:
                self._jobs[job].update(status='failed', reason_code=reason)
        finally:
            with self._lock:
                publish_document(folder / 'result.json', self._jobs[job], staging=folder / 'staging')

    def close(self):
        with self._lock:
            self._closed = True
        self._pool.shutdown(wait=True)
