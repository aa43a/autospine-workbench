"""Freeze an authored pose request into the cancellable motion task queue."""
from copy import deepcopy
from hashlib import sha256
import json
from threading import Event
from uuid import uuid4

from ..resolved_project import canonical_sha256
from ..targets.character43.pose_geometry_candidate import PROFILE
from .pipeline_run import PipelineRunError
from .storage_io import publish_document, read_document


def submit(manager, parent_job, body):
    from .motion_target_jobs import assert_current, context
    if not isinstance(body, dict) or set(body) != {'artifact_sha256', 'pose_geometry'}:
        raise PipelineRunError('pose_execution_request_invalid')
    result, files = context(manager, parent_job)
    if body['artifact_sha256'] != result['artifact_sha256']:
        raise PipelineRunError('pose_execution_parent_changed')
    pose = deepcopy(body['pose_geometry'])
    document = json.loads(files['skeleton.json'])
    if not isinstance(pose, dict) or pose.get('document_sha256') != canonical_sha256(document):
        raise PipelineRunError('pose_execution_document_changed')
    # Full geometry validation runs in the isolated worker, not on the HTTP thread.
    if (not isinstance(pose.get('slot'), str) or not isinstance(pose.get('animation'), str)
            or pose['animation'] not in document['animations']):
        raise PipelineRunError('pose_execution_scope_invalid')
    mesh = document['skins'][0]['attachments'].get(pose['slot'], {}).get(pose['slot'])
    if mesh is None or pose.get('mesh_sha256') != canonical_sha256(mesh):
        raise PipelineRunError('pose_execution_mesh_changed')
    request = read_document(manager.folder(parent_job)/'request.json')
    assert_current(manager, request)
    plan = dict(action='pose_geometry', artifact_sha256=result['artifact_sha256'],
                slot=pose['slot'], animation=pose['animation'], pose_geometry=pose)
    repair = dict(profile=PROFILE, parent_job_id=parent_job, parent_artifact_sha256=result['artifact_sha256'],
                  draft_sha256=canonical_sha256(plan), draft=plan)
    if 'motion-repair-provenance.json' in files:
        repair['parent_repair_sha256'] = sha256(files['motion-repair-provenance.json']).hexdigest()
    from .motion_repair_lineage import carry
    carry(files, repair)  # Fail before queuing if parent history is invalid/full.
    with manager._lock:
        if manager._closed or sum(j['status'] in {'pending', 'running'} for j in manager._jobs.values()) >= 2:
            raise PipelineRunError('motion_queue_full')
        job = 'motion-'+uuid4().hex
        root = manager.folder(job, True)
        request = deepcopy(request)
        request.update(job_id=job, repair_execution=repair)
        publish_document(root/'request.json', request, staging=root/'staging')
        value = dict(job_id=job, kind='adapt', project_id=request['project_id'],
                     character_job_id=request['character_job_id'], name=request['name']+' · 姿态修形候选',
                     status='pending', step='queued', authority='none', repair_parent_job_id=parent_job)
        manager._jobs[job] = value
        manager._cancel[job] = Event()
        manager._pool.submit(manager._execute, job)
        return deepcopy(value)
