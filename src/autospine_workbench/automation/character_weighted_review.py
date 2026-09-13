"""Exact-candidate review of existing weighted regions, without rebinding a layer."""
import json
from .storage_io import directory, publish_document, read_document
from .pipeline_run import PipelineRunError
from .character_visual_review import context
from ..resolved_project import canonical_sha256

SCHEMA = 'autospine.character-weighted-review/v1'
OVERRIDE_SCHEMA = 'autospine.character-weighted-review/v2'


def eligible(layer):
    regions = layer.get('regions', [])
    return (layer.get('state') == 'weighted_candidate' and bool(regions)
            and all(row.get('state') == 'weighted_candidate' for row in regions)
            and not layer.get('missing_region_ids')
            and layer.get('binding_decision', {}).get('decision_source') in {'pending', 'explicit_selection', 'legacy_selection'}
            and layer.get('binding_decision', {}).get('action') == 'pending')


def _explicit_layers(job, value):
    """Only an exact, explicitly reviewed output scope may replace whole-layer pending."""
    if not value or value.get('can_review') is not True or value.get('authority') != 'none' or value.get('project_id') != job.get('project_id') or value.get('job_id') != job.get('job_id'):
        return set()
    review = value.get('review') or {}
    if (value.get('artifact_sha256') != job.get('artifact_sha256') or review.get('schema') not in {SCHEMA,OVERRIDE_SCHEMA}
            or review.get('artifact_sha256') != job.get('artifact_sha256')
            or review.get('project_id') != job.get('project_id') or review.get('job_id') != job.get('job_id')
            or review.get('runtime_sha256') != canonical_sha256(job.get('runtime', {}))
            or review.get('layers_sha256') != canonical_sha256(job.get('layers', []))
            or value.get('review_sha256') != canonical_sha256(review) or review.get('authority') != 'none'
            or review.get('decision_source') != 'human_review' or review.get('production_authorized') is not False):
        return set()
    allowed = {row['layer_id'] for row in job.get('layers', []) if eligible(row)}
    selected = review.get('accepted_layer_ids', [])
    return set(selected) if type(selected) is list and all(type(k) is str for k in selected) and set(selected) <= allowed else set()


def confirmed_layers(job,value):
    explicit=_explicit_layers(job,value)
    if not value or value.get('can_review') is not True or value.get('authority')!='none': return set()
    if any(value.get(k)!=job.get(k) for k in ('project_id','job_id','artifact_sha256')): return set()
    review=value.get('review')
    if review and review.get('schema')!=OVERRIDE_SCHEMA: return explicit
    revoked=[]
    if review:
        if value.get('review_sha256')!=canonical_sha256(review): return set()
        expected=dict(project_id=job.get('project_id'),job_id=job.get('job_id'),artifact_sha256=job.get('artifact_sha256'),
            runtime_sha256=canonical_sha256(job.get('runtime',{})),layers_sha256=canonical_sha256(job.get('layers',[])),
            decision_source='human_review',authority='none',production_authorized=False)
        if any(review.get(k)!=v for k,v in expected.items()): return set()
        revoked=review.get('revoked_replayed_layer_ids')
        if type(revoked) is not list or any(type(k) is not str for k in revoked): return set()
    from .character_weighted_replay import confirmed
    return explicit | (confirmed(job,value)-set(revoked))


def history(manager, job):
    root = manager._path(job)/'weighted-review'
    if not root.exists(): return []
    directory(root); entries = []; previous = None
    for path in sorted(root.glob('*.json')):
        doc = read_document(path)
        if (path.name != f'{len(entries):06d}.json' or doc.get('schema') not in {SCHEMA,OVERRIDE_SCHEMA}
                or doc.get('previous_sha256') != previous or doc.get('revision') != len(entries)):
            raise PipelineRunError('character_review_history_invalid')
        previous = canonical_sha256(doc); entries.append((previous, doc))
    return entries


def overview(manager, project, job):
    result = context(manager, project, job)
    files = manager.application.store.read(result['artifact_sha256'])
    manifest = json.loads(files['character-manifest.json'])
    if manifest['layers'] != result['layers']:
        raise PipelineRunError('character_review_source_mismatch')
    raw, _ = manager.review_file(project, job, ['report.json']); runtime = json.loads(raw)
    ready = (runtime.get('bundle_sha256') == result['artifact_sha256'] and runtime.get('passed') is True
             and result.get('runtime', {}).get('geometry_status') == 'passed')
    entries = history(manager, job); current = entries[-1] if entries else None
    if current and any(current[1].get(key) != value for key, value in dict(
            project_id=project, job_id=job, artifact_sha256=result['artifact_sha256'],
            layers_sha256=canonical_sha256(result['layers']), runtime_sha256=canonical_sha256(result['runtime'])).items()):
        raise PipelineRunError('character_review_source_mismatch')
    if current:
        selected = current[1].get('accepted_layer_ids')
        allowed = {r['layer_id'] for r in result['layers'] if eligible(r)}
        if (type(selected) is not list or any(type(k) is not str for k in selected)
                or selected != sorted(set(selected)) or not set(selected) <= allowed
                or current[1].get('decision_source') != 'human_review' or current[1].get('production_authorized') is not False):
            raise PipelineRunError('character_review_history_invalid')
        if current[1]['schema']==OVERRIDE_SCHEMA:
            revoked=current[1].get('revoked_replayed_layer_ids')
            if (type(revoked) is not list or any(type(k) is not str for k in revoked)
                    or revoked!=sorted(set(revoked)) or not set(revoked)<=allowed):
                raise PipelineRunError('character_review_history_invalid')
    value=dict(project_id=project, job_id=job, artifact_sha256=result['artifact_sha256'], authority='none',
                can_review=ready, reason_code=None if ready else 'character_weighted_qa_required',
                eligible_layer_ids=[r['layer_id'] for r in result['layers'] if eligible(r)],
                review_sha256=current[0] if current else None, review=current[1] if current else None)
    if 'skeleton.json' in files:
        from ..targets.character43.binding_inventory import inspect
        value['binding_inventory']=inspect(json.loads(files['skeleton.json']),result['layers'])
    if ready and (not current or current[1]['schema']==OVERRIDE_SCHEMA):
        from .character_weighted_replay import derive
        proof=derive(manager,result,files)
        if proof:
            value.update(replayed_review=proof,replay_sha256=canonical_sha256(proof))
    if value.get('replayed_review') or (current and current[1]['schema']==OVERRIDE_SCHEMA):
        value['confirmed_layer_ids']=sorted(confirmed_layers(result,value))
    return value


def save(manager, project, job, body):
    keys={'expected_artifact_sha256', 'expected_review_sha256', 'layer_id', 'action'}
    if (set(body) not in (keys,keys|{'expected_replay_sha256'})
            or body['action'] not in {'confirm', 'revoke'} or type(body['layer_id']) is not str):
        raise PipelineRunError('character_review_invalid')
    with manager._lock:
        current = overview(manager, project, job)
        if (body['expected_artifact_sha256'] != current['artifact_sha256']
                or body['expected_review_sha256'] != current['review_sha256']):
            raise PipelineRunError('character_review_conflict')
        if body.get('expected_replay_sha256')!=current.get('replay_sha256'):
            raise PipelineRunError('character_review_conflict')
        if not current['can_review'] or body['layer_id'] not in current['eligible_layer_ids']:
            raise PipelineRunError('character_weighted_scope_invalid')
        accepted = set((current['review'] or {}).get('accepted_layer_ids', []))
        revoked=set((current['review'] or {}).get('revoked_replayed_layer_ids',[]))
        overrides=bool(current.get('replayed_review')) or (current['review'] or {}).get('schema')==OVERRIDE_SCHEMA
        if body['action'] == 'confirm': accepted.add(body['layer_id'])
        else: accepted.discard(body['layer_id'])
        if overrides:
            if body['action']=='confirm': revoked.discard(body['layer_id'])
            else: revoked.add(body['layer_id'])
        if current['review'] and sorted(accepted) == current['review']['accepted_layer_ids'] and sorted(revoked)==current['review'].get('revoked_replayed_layer_ids',[]): return current
        result = manager.get(project, job)
        doc = dict(schema=SCHEMA, project_id=project, job_id=job, artifact_sha256=current['artifact_sha256'],
                   runtime_sha256=canonical_sha256(result['runtime']), layers_sha256=canonical_sha256(result['layers']),
                   previous_sha256=current['review_sha256'], revision=len(history(manager, job)),
                   decision_source='human_review', authority='none', production_authorized=False,
                   accepted_layer_ids=sorted(accepted))
        if overrides:
            doc.update(schema=OVERRIDE_SCHEMA,revoked_replayed_layer_ids=sorted(revoked),
                       replay_sha256=current.get('replay_sha256'))
        root = directory(manager._path(job)/'weighted-review', create=True)
        if not publish_document(root/f"{doc['revision']:06d}.json", doc, staging=root/'staging'):
            raise PipelineRunError('character_review_conflict')
        return overview(manager, project, job)
