"""Derived binding-only review continuity; never creates a new human decision."""
from hashlib import sha256
import json
from .storage_io import read_document,directory,publish_document
from .pipeline_run import PipelineRunError
from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file
from ..targets.character43.binding_continuity import unchanged_layers
from .pipeline_run_validation import require_sha

SCHEMA='autospine.character-binding-replay/v1'


def read_proof(manager,digest):
    require_sha(digest)
    proof=read_document(manager.root/'binding-replay-evidence'/(digest+'.json'))
    if canonical_sha256(proof)!=digest or proof.get('schema')!=SCHEMA:
        raise PipelineRunError('character_binding_replay_digest_invalid')
    return proof


def derive(manager, result, files):
    if 'final-region-exclusion.json' not in files: return None
    from .character_weighted_review import history, confirmed_layers, eligible
    receipt=json.loads(files['final-region-exclusion.json'])
    source_sha=receipt['source_bundle_sha256']; candidates=[]
    # Locate only an exact predecessor carrying an explicit human review.
    folders=list(manager.root.glob('job-*'))
    if len(folders)>4096: raise PipelineRunError('character_binding_replay_resource_limit')
    for folder in folders:
        if not (folder/'weighted-review').exists() or not (folder/'result.json').exists(): continue
        old=read_document(folder/'result.json')
        if old.get('artifact_sha256')!=source_sha or old.get('project_id')!=result['project_id']: continue
        if old.get('job_id')!=folder.name: raise PipelineRunError('character_binding_replay_source_invalid')
        entries=history(manager,folder.name)
        if not entries: continue
        digest,review=entries[-1]
        # No recursive/transitive reuse: the source must be an explicit v1 decision.
        if review.get('schema')!='autospine.character-weighted-review/v1': continue
        raw=read_real_file(folder/'runtime/report.json',64<<20,'historical runtime report')
        if sha256(raw).hexdigest()!=old.get('runtime',{}).get('files',{}).get('report.json'):
            raise PipelineRunError('character_binding_replay_runtime_invalid')
        runtime=json.loads(raw)
        ready=(runtime.get('bundle_sha256')==source_sha and runtime.get('passed') is True
               and old.get('runtime',{}).get('geometry_status')=='passed')
        value=dict(project_id=old['project_id'],job_id=old['job_id'],artifact_sha256=source_sha,
            authority='none',can_review=ready,review=review,review_sha256=digest)
        accepted=confirmed_layers(old,value)
        if accepted: candidates.append((old,digest,accepted))
    if len(candidates)!=1: return None
    old,review_sha,accepted=candidates[0]
    source=manager.application.store.read(source_sha)
    if json.loads(source['character-manifest.json'])['layers']!=old['layers']:
        raise PipelineRunError('character_binding_replay_source_invalid')
    unchanged=set(unchanged_layers(source,files))
    allowed={l['layer_id'] for l in result['layers'] if eligible(l)}
    retained=sorted(accepted & unchanged & allowed)
    if not retained: return None
    proof=dict(schema=SCHEMA,profile='exact-final-exclusion-binding-v1',project_id=result['project_id'],
        job_id=result['job_id'],artifact_sha256=result['artifact_sha256'],
        runtime_sha256=canonical_sha256(result['runtime']),layers_sha256=canonical_sha256(result['layers']),
        source_job_id=old['job_id'],source_bundle_sha256=source_sha,source_review_sha256=review_sha,
        accepted_layer_ids=retained,decision_source='verified_scope_replay',new_human_confirmation=False,
        whole_character_visual_replayed=False,authority='none',production_authorized=False)
    digest=canonical_sha256(proof);folder=directory(manager.root/'binding-replay-evidence',create=True)
    publish_document(folder/(digest+'.json'),proof,staging=folder/'staging')
    return read_proof(manager,digest)


def confirmed(job,value):
    proof=value.get('replayed_review')
    if not proof or value.get('replay_sha256')!=canonical_sha256(proof): return set()
    expected=dict(schema=SCHEMA,profile='exact-final-exclusion-binding-v1',project_id=job.get('project_id'),
        job_id=job.get('job_id'),artifact_sha256=job.get('artifact_sha256'),
        runtime_sha256=canonical_sha256(job.get('runtime',{})),layers_sha256=canonical_sha256(job.get('layers',[])),
        decision_source='verified_scope_replay',new_human_confirmation=False,
        whole_character_visual_replayed=False,authority='none',production_authorized=False)
    if any(proof.get(k)!=v for k,v in expected.items()): return set()
    from .character_weighted_review import eligible
    allowed={l['layer_id'] for l in job.get('layers',[]) if eligible(l)}
    selected=proof.get('accepted_layer_ids')
    return set(selected) if type(selected) is list and all(type(k) is str for k in selected) and set(selected)<=allowed else set()
