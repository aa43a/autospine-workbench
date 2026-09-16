"""Exact, reversible project component parent decisions applied after exclusions."""
import json
import re
from ..manifest_artifacts import require_safe_token
from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .storage_io import directory, read_document, publish_document

SCHEMA = 'autospine.character-component-mounts/v1'
from .character_build_options import OPTIONS, valid_options


def _valid(doc):
    decision = doc.get('decision'); parents = doc.get('allowed_parents')
    options = doc.get('build_options')
    if not valid_options(options): return False
    if decision is None: return parents == [] and options == {}
    if type(parents) is not list or not 1 <= len(parents) <= 64 or any(type(p) is not str or not p for p in parents): return False
    if len(set(parents)) != len(parents) or type(decision) is not dict: return False
    if set(decision) != {'schema','source_bundle_sha256','source_region_id','plan_sha256','decision_source','reversible','parents'}: return False
    if decision['schema'] != 'autospine.component-mount-decision/v1' or decision['decision_source'] != 'human_confirmation' or decision['reversible'] is not True: return False
    if any(type(decision[k]) is not str or not re.fullmatch('[a-f0-9]{64}',decision[k]) for k in ('source_bundle_sha256','plan_sha256')): return False
    if type(decision['source_region_id']) is not str or not decision['source_region_id']: return False
    choices = decision['parents']
    return (type(choices) is dict and 1 <= len(choices) <= 64
            and all(type(k) is str and k and type(v) is str and v in parents for k,v in choices.items()))


def overview(manager, project):
    require_safe_token(project, 'project')
    root = manager.root/'component-mount-decisions'/project
    previous = None; current = None
    if root.exists():
        directory(root)
        paths = sorted(root.glob('*.json'))
        if len(paths) > 4096: raise PipelineRunError('character_mount_history_limit')
        for revision,path in enumerate(paths):
            doc = read_document(path)
            if (set(doc) != {'schema','project_id','revision','previous_sha256','decision','allowed_parents','build_options','authority','production_authorized'}
                    or path.name != f'{revision:06d}.json' or doc.get('schema') != SCHEMA
                    or doc.get('project_id') != project or type(doc.get('revision')) is not int
                    or doc['revision'] != revision or doc.get('previous_sha256') != previous
                    or doc.get('authority') != 'none' or doc.get('production_authorized') is not False
                    or not _valid(doc)):
                raise PipelineRunError('character_mount_history_invalid')
            previous = canonical_sha256(doc); current = doc
    return dict(project_id=project, authority='none', head_sha256=previous,
                review=current, active=bool(current and current['decision']))


def save(manager, project, body):
    keys = {'action','expected_head_sha256'}
    if body.get('action') == 'replace': keys |= {'job_id','decision','allowed_parents'}
    elif body.get('action') != 'revoke': raise PipelineRunError('character_mount_review_invalid')
    if set(body) != keys: raise PipelineRunError('character_mount_review_invalid')
    with manager._lock:
        manager.projects.get_project(project)
        current = overview(manager,project)
        if body['expected_head_sha256'] != current['head_sha256']: raise PipelineRunError('character_mount_review_conflict')
        decision = None; parents = []; options = {}
        if body['action'] == 'replace':
            decision = body['decision']; parents = body['allowed_parents']
            if not _valid(dict(decision=decision,allowed_parents=parents,build_options=options)) or decision is None:
                raise PipelineRunError('character_mount_review_invalid')
            result = manager.get(project,body['job_id'])
            if result['status'] != 'needs_review' or result.get('artifact_sha256') != decision['source_bundle_sha256']:
                raise PipelineRunError('character_mount_source_changed')
            files = manager.verified_files(project,body['job_id'])
            from ..targets.character43.component_mount_candidate import generate
            generate(files,decision['source_region_id'],parents,decision)
            request = read_document(manager._path(body['job_id'])/'request.json')
            options = {k:request[k] for k in OPTIONS if k in request}
        elif not current['active']: return current
        doc = dict(schema=SCHEMA,project_id=project,revision=0 if current['review'] is None else current['review']['revision']+1,
                   previous_sha256=current['head_sha256'],decision=decision,allowed_parents=parents,build_options=options,
                   authority='none',production_authorized=False)
        root = directory(manager.root/'component-mount-decisions'/project,create=True)
        if not publish_document(root/f'{doc["revision"]:06d}.json',doc,staging=root/'staging'):
            raise PipelineRunError('character_mount_review_conflict')
        return overview(manager,project)


def apply_saved(manager, request, result):
    current = overview(manager,request['project_id'])
    if current['head_sha256'] != request.get('component_mounts_sha256'):
        raise PipelineRunError('character_mount_decisions_changed')
    if not current['active']: return result
    review = current['review']; decision = review['decision']
    from ..targets.character43.component_mount_candidate import generate
    store = manager.application.store
    if result['artifact_sha256'] != decision['source_bundle_sha256']:
        from .character_mount_revalidation import rebuild
        files,report=rebuild(store,result['artifact_sha256'],review)
    else:
        files,report = generate(store.read(result['artifact_sha256']),decision['source_region_id'],review['allowed_parents'],decision)
    return dict(result,artifact_sha256=store.publish(files),manifest=json.loads(files['character-manifest.json']),
                component_mounts=dict(review_sha256=current['head_sha256'],source_region_id=decision['source_region_id'],
                                      parent_review_required=report['parent_review_required'],authority='none'))
