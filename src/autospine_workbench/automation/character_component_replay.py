"""One component replacement after an explicit review or exact exclusion replay."""
from hashlib import sha256
import json
from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file
from ..targets.character43.component_binding_continuity import unchanged_layers
from .storage_io import read_document,directory,publish_document
from .pipeline_run import PipelineRunError

SCHEMA='autospine.character-binding-replay/v2'
PROFILE='exact-component-binding-v1'


def derive(manager,result,files):
    from .character_weighted_review import history,confirmed_layers,eligible
    from .character_weighted_replay import derive as exclusion_replay,read_proof
    source_sha=json.loads(files['component-mount.json'])['source_bundle_sha256']
    source=manager.application.store.read(source_sha)
    # Deliberately bounded: no chain of component conversions, no arbitrary graph traversal.
    if 'component-mount.json' in source:return None
    unchanged=set(unchanged_layers(source,files));candidates=[]
    folders=list(manager.root.glob('job-*'))
    if len(folders)>4096:raise PipelineRunError('character_binding_replay_resource_limit')
    for folder in folders:
        if not (folder/'result.json').exists():continue
        old=read_document(folder/'result.json')
        if old.get('artifact_sha256')!=source_sha or old.get('project_id')!=result['project_id']:continue
        if old.get('job_id')!=folder.name or old.get('layers')!=json.loads(source['character-manifest.json'])['layers']:
            raise PipelineRunError('character_binding_replay_source_invalid')
        if old.get('status')!='needs_review':continue
        entries=history(manager,folder.name);current=entries[-1] if entries else None
        raw=read_real_file(folder/'runtime/report.json',64<<20,'historical runtime report')
        if sha256(raw).hexdigest()!=old.get('runtime',{}).get('files',{}).get('report.json'):
            raise PipelineRunError('character_binding_replay_runtime_invalid')
        runtime=json.loads(raw)
        if runtime.get('bundle_sha256')!=source_sha or runtime.get('passed') is not True or old.get('runtime',{}).get('geometry_status')!='passed':continue
        value=dict(project_id=old['project_id'],job_id=old['job_id'],artifact_sha256=source_sha,
            authority='none',can_review=True,review=current[1] if current else None,review_sha256=current[0] if current else None)
        if not current or current[1].get('schema')=='autospine.character-weighted-review/v2':
            prior=exclusion_replay(manager,old,source)
            if prior:value.update(replayed_review=prior,replay_sha256=canonical_sha256(prior))
        accepted=confirmed_layers(old,value)
        if accepted:candidates.append((old,value,accepted))
    if len(candidates)!=1:return None
    old,value,accepted=candidates[0]
    allowed={l['layer_id'] for l in result['layers'] if eligible(l)}
    retained=sorted(accepted & unchanged & allowed)
    if not retained:return None
    proof=dict(schema=SCHEMA,profile=PROFILE,project_id=result['project_id'],job_id=result['job_id'],
        artifact_sha256=result['artifact_sha256'],runtime_sha256=canonical_sha256(result['runtime']),
        layers_sha256=canonical_sha256(result['layers']),source_job_id=old['job_id'],source_bundle_sha256=source_sha,
        source_review_sha256=value.get('review_sha256'),source_replay_sha256=value.get('replay_sha256'),
        accepted_layer_ids=retained,decision_source='verified_scope_replay',new_human_confirmation=False,
        whole_character_visual_replayed=False,authority='none',production_authorized=False)
    digest=canonical_sha256(proof);root=directory(manager.root/'binding-replay-evidence',create=True)
    publish_document(root/(digest+'.json'),proof,staging=root/'staging')
    return read_proof(manager,digest)
