"""Repeat a source-bound target request without upgrading historical defaults."""
from copy import deepcopy
from hashlib import sha256
from threading import Event
from uuid import uuid4

from ..safe_input_files import read_real_file
from .pipeline_run import PipelineRunError
from .storage_io import publish_document


def retry(manager, request):
    import json
    from .motion_target_jobs import assert_current
    raw = read_real_file(manager.folder(request['job_id']) / 'request.json', 64 << 20, 'motion request')
    if json.loads(raw) != request:
        raise PipelineRunError('motion_target_request_changed')
    assert_current(manager, request)
    with manager._lock:
        if manager._closed or sum(j['status'] in {'pending', 'running'} for j in manager._jobs.values()) >= 2:
            raise PipelineRunError('motion_queue_full')
        job = 'motion-' + uuid4().hex
        root = manager.folder(job, True)
        frozen = deepcopy(request)
        frozen.update(job_id=job, retry_of=dict(job_id=request['job_id'], request_sha256=sha256(raw).hexdigest()))
        publish_document(root / 'request.json', frozen, staging=root / 'staging')
        value = dict(job_id=job, kind='adapt', project_id=request['project_id'],
                     character_job_id=request['character_job_id'], name=request['name'],
                     status='pending', step='queued', authority='none', retry_of=frozen['retry_of'])
        manager._jobs[job] = value
        manager._cancel[job] = Event()
        manager._pool.submit(manager._execute, job)
        return deepcopy(value)
