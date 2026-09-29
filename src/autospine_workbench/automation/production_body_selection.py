"""Bind production to a registered repair, never a loose artifact address."""
from .pipeline_run import PipelineRunError
from .storage_io import read_document
from ..resolved_project import canonical_sha256


def lineage(manager, selected, root):
    records=[];seen=set();job=selected
    for _ in range(33):
        if job in seen: break
        seen.add(job)
        state=manager.get(job)
        request=read_document(manager.folder(job)/'request.json')
        if state.get('status')!='succeeded' or request.get('joint_execution'):
            raise PipelineRunError('production_repair_parent_unavailable')
        records.append(dict(job_id=job,request_sha256=canonical_sha256(request),artifact_sha256=state['result']['artifact_sha256']))
        if job==root:return records
        repair=request.get('repair_execution',{})
        parent=repair.get('parent_job_id')
        if not parent:break
        if manager.get(parent).get('result',{}).get('artifact_sha256')!=repair.get('parent_artifact_sha256'):
            raise PipelineRunError('production_repair_lineage_changed')
        job=parent
    raise PipelineRunError('production_repair_unrelated_body')


def select(driver, request, parent_job, registration):
    from .motion_joint_source import source_context
    selected=registration[4:] if registration.startswith('job:') else parent_job
    ancestry=lineage(driver.motions,selected,parent_job)
    context = source_context(driver.motions, selected, None if registration.startswith('job:') else registration)
    parent = context['request']
    if any(parent.get(k) != request.get(k) for k in
           ('project_id', 'character_job_id', 'character_sha256', 'source_job_id')):
        raise PipelineRunError('production_repair_source_mismatch')
    if parent.get('source_job_sha256') != request['source_sha256']:
        raise PipelineRunError('production_repair_source_mismatch')
    if any(parent.get(k) != v for k,v in request['body_options'].items()):
        raise PipelineRunError('production_repair_parameters_changed')
    return dict(context['provenance'],root_job_id=parent_job,selector=registration,lineage=ancestry)


def validate(driver, request):
    value = request.get('body_selection')
    if value is None:
        return
    if not isinstance(value, dict) or not isinstance(value.get('selector'),str):
        raise PipelineRunError('production_repair_selection_invalid')
    actual = select(driver, request, value['root_job_id'], value['selector'])
    if actual != value:
        raise PipelineRunError('production_repair_selection_changed')


def candidates(manager,run_id):
    from .motion_related_candidates import entries
    run=manager.get(run_id);stage=run['stages']['body'];driver=manager.driver
    if stage['status']!='succeeded':raise PipelineRunError('production_body_unavailable')
    root=stage['job_id'];motions=driver.motions
    if motions.get(root).get('result',{}).get('artifact_sha256')!=stage['artifact_sha256']:
        raise PipelineRunError('production_body_changed')
    selectors=entries(motions.folder(root));unavailable=[];rows=[]
    # Read only small request records; candidate payload validation happens below.
    for path in sorted(motions.root.glob('motion-*/request.json')):
        request=read_document(path)
        if (any(request.get(k)!=run['request'].get(k) for k in ('project_id','character_job_id','source_job_id'))
                or not request.get('repair_execution') or request.get('joint_execution')):continue
        try:lineage(motions,path.parent.name,root)
        except (ValueError,RuntimeError,KeyError):continue
        selectors.append('job:'+path.parent.name)
    for selector in selectors:
        try:
            value=select(driver,run['request'],root,selector)
            job=value['parent_job_id'];registration=value['registration_sha256']
            rows.append(dict(selector=selector,artifact_sha256=value['artifact_sha256'],
                kind='repair_job' if selector.startswith('job:') else 'registered_candidate',
                player_url=f'/api/motions/{job}/view/'+(f'related-candidates/{registration}/' if registration else '')+'player.html'))
        except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:
            unavailable.append(dict(selector=selector,reason_code=getattr(exc,'reason_code',str(exc))))
    return dict(baseline_sha256=stage['artifact_sha256'],rows=rows,unavailable=unavailable,authority='none')
