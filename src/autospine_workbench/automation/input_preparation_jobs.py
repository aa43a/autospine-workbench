"""Bounded project-input preparation jobs, independent of animation compilation."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import re
from threading import Event, RLock
from uuid import uuid4

from ..manifest_artifacts import require_safe_token, require_sha256
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document

SCHEMA = 'autospine.input-preparation-job/v1'
TERMINAL = {'needs_review', 'succeeded', 'blocked', 'failed', 'canceled'}
STEPS = ('prepare-source', 'run-pose', 'register-review')


def validate_request(request):
    if type(request) is not dict or set(request) != {'project_id', 'expected_resolved_sha256'}:
        raise PipelineRunError('pipeline_request_invalid')
    require_safe_token(request['project_id'], 'Project')
    require_sha256(request['expected_resolved_sha256'], 'Resolved project')


def response(job_id, request, status):
    return dict(schema=SCHEMA, job_id=job_id, **request, status=status,
                authority='none', source_registered=False, reason_code=None, progress=[])


def validate_result(result):
    if (type(result) is not dict or result.get('status') not in TERMINAL or
        type(result.get('source_registered')) is not bool or result.get('authority') != 'none' or
        result.get('production_authorized', False) is not False or
        result['source_registered'] and result['status'] not in {'needs_review', 'succeeded'}):
        raise PipelineRunError('preparation_result_invalid')
    count = result.get('reviewed_joint_count', 0)
    if type(count) is not int or not 0 <= count <= 17:
        raise PipelineRunError('preparation_result_invalid')
    from ..benchmark.joint_draft import JOINTS
    for key in ('imported_joint_ids', 'ignored_joint_ids'):
        ids = result.get(key, [])
        if (type(ids) is not list or any(type(v) is not str or not v for v in ids)
                or len(set(ids)) != len(ids)):
            raise PipelineRunError('preparation_result_invalid')
        if key == 'imported_joint_ids' and (set(ids)-set(JOINTS) or key in result and len(ids) != count):
            raise PipelineRunError('preparation_result_invalid')
        if key == 'ignored_joint_ids' and set(ids).intersection(JOINTS):
            raise PipelineRunError('preparation_result_invalid')
    if result.get('reason_code') is not None and (
        type(result['reason_code']) is not str or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', result['reason_code'])):
        raise PipelineRunError('preparation_result_invalid')
    if result['source_registered'] and not re.fullmatch(
        r'[0-9a-f]{64}', str(result.get('input_identity_sha256', ''))):
        raise PipelineRunError('preparation_result_invalid')


class InputPreparationJobs:
    def __init__(self, store, application=None):
        if application is None:
            from .input_preparation_application import InputPreparationApplication
            application = InputPreparationApplication(store)
        self.application = application
        self.root = Path(store.state_root) / 'jobs' / 'input-preparation-v1'
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='prepare-inputs')
        self._lock, self._active, self._closed = RLock(), {}, False

    def _path(self, job_id, create=False):
        if type(job_id) is not str or not re.fullmatch(r'job-[0-9a-f]{32}', job_id):
            raise PipelineRunError('pipeline_job_id_invalid')
        return directory(self.root / job_id, create=create)

    def submit(self, project_id, expected_resolved_sha256):
        request = dict(project_id=project_id, expected_resolved_sha256=expected_resolved_sha256)
        validate_request(request)
        with self._lock:
            if self._closed:
                raise PipelineRunError('pipeline_manager_closed')
            for item in self._active.values():
                if item['request'] == request:
                    return deepcopy(item['response'])
            if len(self._active) >= 8:
                raise PipelineRunError('pipeline_queue_full')
            job_id = 'job-' + uuid4().hex
            folder = self._path(job_id, True)
            publish_document(folder / 'request.json', request, staging=folder / 'staging')
            value = response(job_id, request, 'pending')
            self._active[job_id] = dict(request=request, response=value, cancel=Event())
            self._pool.submit(self._execute, job_id)
            return deepcopy(value)

    def get(self, project_id, job_id):
        with self._lock:
            if job_id in self._active:
                value = self._active[job_id]['response']
                if value['project_id'] != project_id:
                    raise PipelineRunError('pipeline_job_not_found')
                return deepcopy(value)
            folder = self._path(job_id)
            request = read_document(folder / 'request.json')
            validate_request(request)
            if request['project_id'] != project_id:
                raise PipelineRunError('pipeline_job_not_found')
            if not (folder / 'result.json').exists():
                value = response(job_id, request, 'blocked')
                value['reason_code'] = 'preparation_interrupted'
                return value
            value = read_document(folder / 'result.json')
            if (value.get('schema') != SCHEMA or value.get('job_id') != job_id or
                any(value.get(k) != v for k, v in request.items()) or value.get('authority') != 'none' or
                value.get('status') not in TERMINAL or type(value.get('source_registered')) is not bool):
                raise PipelineRunError('pipeline_storage_invalid')
            try:
                nested = value.get('result')
                if nested is not None and type(nested) is not dict:
                    raise PipelineRunError('pipeline_storage_invalid')
                validate_result(dict(value, input_identity_sha256=(nested or {}).get('input_identity_sha256')))
                if 'result' in value:
                    validate_result(value['result'])
                    if any(value.get(k) != value['result'].get(k)
                           for k in ('status', 'source_registered', 'reason_code')):
                        raise PipelineRunError('pipeline_storage_invalid')
                elif value['source_registered']:
                    raise PipelineRunError('pipeline_storage_invalid')
            except PipelineRunError as exc:
                raise PipelineRunError('pipeline_storage_invalid') from exc
            return value

    def cancel(self, project_id, job_id):
        with self._lock:
            value = self.get(project_id, job_id)
            if job_id in self._active:
                self._active[job_id]['cancel'].set()
                self._active[job_id]['response']['cancel_requested'] = True
                value = deepcopy(self._active[job_id]['response'])
            return value

    def _execute(self, job_id):
        with self._lock:
            item = self._active[job_id]
            item['response']['status'] = 'running'
        request = item['request']
        def progress(steps):
            with self._lock:
                item['response']['progress'] = deepcopy(steps)
        try:
            result = self.application.prepare(**request, cancel_requested=item['cancel'].is_set, progress=progress)
            validate_result(result)
            value = response(job_id, request, result['status'])
            value.update(result=result, source_registered=result['source_registered'],
                         reason_code=result.get('reason_code'), progress=item['response'].get('progress', []))
        except Exception as exc:
            reason = getattr(exc, 'reason_code', 'preparation_failed')
            if type(reason) is not str or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', reason):
                reason = 'preparation_failed'
            value = response(job_id, request, 'canceled' if item['cancel'].is_set() else 'failed')
            value['reason_code'] = 'preparation_canceled' if item['cancel'].is_set() else reason
            value['progress'] = deepcopy(item['response'].get('progress', []))
        # Once registration succeeds, late cancellation cannot pretend it did not happen.
        with self._lock:
            folder = self._path(job_id)
            try:
                publish_document(folder / 'result.json', value, staging=folder / 'staging')
            finally:
                self._active.pop(job_id, None)

    def close(self):
        with self._lock:
            self._closed = True
            for item in self._active.values():
                item['cancel'].set()
        self._pool.shutdown(wait=True)
