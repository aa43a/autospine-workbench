"""Reversible exact-source parent assignments for existing static regions."""
import json
import re
from .storage_io import directory, read_document, publish_document
from .pipeline_run import PipelineRunError
from ..manifest_artifacts import require_safe_token
from ..resolved_project import canonical_sha256


def valid_decision(doc):
    keys={'schema','source_bundle_sha256','parents','decision_source','reversible'}
    return (type(doc) is dict and set(doc)==keys and doc['schema']=='autospine.region-mount-decision/v1'
        and doc['decision_source'] in ('human_confirmation', 'agent_review') and doc['reversible'] is True
        and type(doc['source_bundle_sha256']) is str and bool(re.fullmatch('[a-f0-9]{64}',doc['source_bundle_sha256']))
        and type(doc['parents']) is dict and 0<len(doc['parents'])<=64
        and all(type(k) is str and bool(re.fullmatch('[A-Za-z0-9_-]{1,120}',k))
                and type(v) is str and bool(re.fullmatch('[A-Za-z0-9_-]{1,120}',v)) for k,v in doc['parents'].items()))


def overview(manager,project):
    require_safe_token(project,'project');root=manager.root/'region-mount-decisions'/project
    previous=None;current=None
    if root.exists():
        directory(root)
        for index,path in enumerate(sorted(root.glob('*.json'))):
            doc=read_document(path)
            if (path.name!=f'{index:06d}.json' or set(doc)!={'schema','project_id','revision','previous_sha256','decision','authority','production_authorized'}
                    or doc['schema']!='autospine.character-region-mounts/v1' or doc['project_id']!=project
                    or type(doc['revision']) is not int or doc['revision']!=index or doc['previous_sha256']!=previous
                    or doc['authority']!='none' or doc['production_authorized'] is not False
                    or (doc['decision'] is not None and not valid_decision(doc['decision']))):
                raise PipelineRunError('character_region_mount_history_invalid')
            previous=canonical_sha256(doc);current=doc
    return dict(project_id=project,authority='none',head_sha256=previous,review=current,
                active=bool(current and current['decision']))


def save(manager,project,body):
    action=body.get('action');keys={'action','expected_head_sha256'}
    if action=='replace':keys|={'job_id','decision'}
    elif action!='revoke':raise PipelineRunError('character_region_mount_invalid')
    if set(body)!=keys:raise PipelineRunError('character_region_mount_invalid')
    with manager._lock:
        manager.projects.get_project(project);current=overview(manager,project);decision=None
        if current['head_sha256']!=body['expected_head_sha256']:raise PipelineRunError('character_review_conflict')
        if action=='replace':
            decision=body['decision']
            if not valid_decision(decision):raise PipelineRunError('character_region_mount_invalid')
            result=manager.get(project,body['job_id'])
            if result['status']!='needs_review' or result['artifact_sha256']!=decision['source_bundle_sha256']:
                raise PipelineRunError('character_region_mount_source_changed')
            from ..targets.character43.region_mount_candidate import generate
            generate(manager.verified_files(project,body['job_id']),decision)
        elif not current['active']:return current
        doc=dict(schema='autospine.character-region-mounts/v1',project_id=project,
                 revision=0 if current['review'] is None else current['review']['revision']+1,
                 previous_sha256=current['head_sha256'],decision=decision,authority='none',production_authorized=False)
        root=directory(manager.root/'region-mount-decisions'/project,create=True)
        if not publish_document(root/f'{doc["revision"]:06d}.json',doc,staging=root/'staging'):
            raise PipelineRunError('character_review_conflict')
        return overview(manager,project)


def apply_saved(manager,request,result):
    current=overview(manager,request['project_id'])
    if current['head_sha256']!=request.get('region_mounts_sha256'):
        raise PipelineRunError('character_region_mount_decisions_changed')
    if not current['active']:return result
    from .character_residual_defaults import apply
    staged=apply(manager,request,result);decision=current['review']['decision']
    if staged['artifact_sha256']!=decision['source_bundle_sha256']:
        raise PipelineRunError('character_region_mount_source_changed')
    from ..targets.character43.region_mount_candidate import generate
    store=manager.application.store;files,report=generate(store.read(staged['artifact_sha256']),decision)
    return dict(staged,artifact_sha256=store.publish(files),manifest=json.loads(files['character-manifest.json']),
                region_mounts=dict(report,review_sha256=current['head_sha256']))
