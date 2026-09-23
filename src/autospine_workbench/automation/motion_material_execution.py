"""Freeze a live artwork mapping into the existing cancellable candidate queue."""
from copy import deepcopy
from threading import Event
from uuid import uuid4
from ..resolved_project import canonical_sha256
from ..targets.character43.material_region_candidate import PROFILE
from .animated_store import AnimatedStore
from .pipeline_run import PipelineRunError
from .storage_io import publish_document,read_document


def submit(manager,parent_job,body):
    from .motion_material_mapping import history
    from .motion_material_return import inspect as returns
    from .motion_repair_draft import history as drafts
    from .motion_repair_material import download
    from .motion_target_jobs import assert_current,context
    if set(body)!={'revision','mapping_sha256'} or type(body['revision']) is not int:
        raise PipelineRunError('motion_material_execution_request_invalid')
    request=read_document(manager.folder(parent_job)/'request.json')
    if request.get('repair_execution'):raise PipelineRunError('motion_repair_nested_execution_unsupported')
    assert_current(manager,request)
    with manager._lock:
        result,_=context(manager,parent_job);rows=history(manager,parent_job);i=body['revision']-1
        if not 0<=i<len(rows):raise PipelineRunError('motion_material_mapping_missing')
        mapping=rows[i]
        if (mapping['action']!='map' or canonical_sha256(mapping)!=body['mapping_sha256']
                or any(r['material_bundle_sha256']==mapping['material_bundle_sha256'] for r in rows[i+1:])):
            raise PipelineRunError('motion_material_mapping_changed')
        receipt=next((r for r in returns(manager,parent_job)['returns'] if r['material_bundle_sha256']==mapping['material_bundle_sha256']),None)
        if receipt is None or result['artifact_sha256']!=mapping['artifact_sha256']:
            raise PipelineRunError('motion_material_execution_source_changed')
        download(manager,parent_job,str(receipt['draft_revision'])) # rejects a withdrawn/superseded plan
        draft=drafts(manager,parent_job)[receipt['draft_revision']-1]
        if canonical_sha256(draft)!=mapping['draft_sha256']:raise PipelineRunError('motion_material_execution_draft_changed')
        material=AnimatedStore(manager.folder(parent_job)/'material-returns').read(receipt['material_bundle_sha256'])
        store=manager.character_manager().application.store
        if store.publish(material)!=receipt['material_bundle_sha256']:raise PipelineRunError('motion_material_execution_identity')
        if manager._closed or sum(j['status'] in {'pending','running'} for j in manager._jobs.values())>=2:
            raise PipelineRunError('motion_queue_full')
        job='motion-'+uuid4().hex;root=manager.folder(job,True);request=deepcopy(request)
        request.update(job_id=job,repair_execution=dict(profile=PROFILE,parent_job_id=parent_job,
            parent_artifact_sha256=mapping['artifact_sha256'],draft_sha256=canonical_sha256(draft),draft=draft,
            material_mapping=mapping,material_mapping_sha256=canonical_sha256(mapping)))
        publish_document(root/'request.json',request,staging=root/'staging')
        value=dict(job_id=job,kind='adapt',project_id=request['project_id'],character_job_id=request['character_job_id'],
            name=request['name']+' · 区域换图候选',status='pending',step='queued',authority='none',repair_parent_job_id=parent_job)
        manager._jobs[job]=value;manager._cancel[job]=Event();manager._pool.submit(manager._execute,job)
        return deepcopy(value)
