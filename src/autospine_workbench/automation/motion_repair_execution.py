"""Submit a frozen local-repair plan through the existing cancellable motion queue."""
from copy import deepcopy
from threading import Event
from uuid import uuid4

from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .storage_io import publish_document, read_document

PROFILE = 'selected-attachment-area-repair-v1'
PARTITION_PROFILE = 'selected-region-rigid-partition-v1'


def submit(manager, parent_job, body):
    from .motion_repair_draft import evidence, history
    from .motion_target_jobs import assert_current
    if (set(body) != {'revision', 'draft_sha256'} or type(body['revision']) is not int
            or not isinstance(body['draft_sha256'], str)):
        raise PipelineRunError('motion_repair_request_invalid')
    report, digest = evidence(manager, parent_job)
    parent = manager.get(parent_job)
    if parent.get('kind') != 'adapt' or parent['status'] != 'succeeded':
        raise PipelineRunError('motion_repair_parent_unavailable')
    request = read_document(manager.folder(parent_job) / 'request.json')
    if request.get('repair_execution'):
        raise PipelineRunError('motion_repair_nested_execution_unsupported')
    assert_current(manager, request)
    with manager._lock:
        rows = history(manager, parent_job)
        index = body['revision'] - 1
        if not 0 <= index < len(rows):
            raise PipelineRunError('motion_repair_plan_unavailable')
        row = rows[index]
        key = lambda r: (r['slot'], r['animation'], r['event']['triangle'], r['event']['time'])
        if (canonical_sha256(row) != body['draft_sha256'] or row['action'] not in ('local_repair','partition')
                or any(key(r) == key(row) for r in rows[index+1:])):
            raise PipelineRunError('motion_repair_plan_changed')
        if row['action']=='partition' and not row.get('partition'):
            raise PipelineRunError('motion_partition_region_required')
        if row['artifact_sha256'] != report['artifact_sha256'] or row['evidence_sha256'] != digest:
            raise PipelineRunError('motion_repair_evidence_changed')
        if manager._closed or sum(j['status'] in {'pending','running'} for j in manager._jobs.values()) >= 2:
            raise PipelineRunError('motion_queue_full')
        job = 'motion-' + uuid4().hex
        root = manager.folder(job, True)
        request = deepcopy(request)
        profile=PARTITION_PROFILE if row['action']=='partition' else PROFILE
        request.update(job_id=job, repair_execution=dict(profile=profile, parent_job_id=parent_job,
            parent_artifact_sha256=report['artifact_sha256'], draft_sha256=body['draft_sha256'], draft=row))
        publish_document(root/'request.json', request, staging=root/'staging')
        value = dict(job_id=job, kind='adapt', project_id=request['project_id'],
            character_job_id=request['character_job_id'], name=request['name']+(' · 分区候选' if row['action']=='partition' else ' · 局部修正候选'),
            status='pending', step='queued', authority='none', repair_parent_job_id=parent_job)
        manager._jobs[job] = value; manager._cancel[job] = Event()
        manager._pool.submit(manager._execute, job)
        return deepcopy(value)


def retry(manager, request):
    repair = request['repair_execution']
    if repair.get('material_mapping'):
        from .motion_material_execution import submit as material_submit
        return material_submit(manager,repair['parent_job_id'],dict(revision=repair['material_mapping']['revision'],mapping_sha256=repair['material_mapping_sha256']))
    return submit(manager, repair['parent_job_id'],
                  dict(revision=repair['draft']['revision'], draft_sha256=repair['draft_sha256']))
