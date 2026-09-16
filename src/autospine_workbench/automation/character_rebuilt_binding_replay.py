"""Re-read explicit predecessor reviews and verify binding scope after reconstruction."""
from hashlib import sha256
import json

from ..resolved_project import canonical_sha256
from ..safe_input_files import read_real_file
from ..targets.character43.rebuilt_binding_continuity import originals, unchanged_layers, predecessor
from .storage_io import read_document, directory, publish_document
from .pipeline_run import PipelineRunError

SCHEMA = 'autospine.character-binding-replay/v4'
PROFILE = 'revalidated-exclusion-binding-v1'


def derive(manager, result, files, *, extended=False):
    from .character_weighted_review import history, confirmed_layers, eligible
    from .character_weighted_replay import read_proof
    expected = originals(files,extended=extended)
    if expected is None: return None
    candidates = []
    folders = list(manager.root.glob('job-*'))
    if len(folders) > 4096: raise PipelineRunError('character_binding_replay_resource_limit')
    for folder in folders:
        if not (folder/'weighted-review').exists() or not (folder/'result.json').exists(): continue
        old = read_document(folder/'result.json')
        if old.get('project_id') != result['project_id'] or old.get('status') != 'needs_review': continue
        if old.get('job_id') != folder.name: raise PipelineRunError('character_binding_replay_source_invalid')
        entries = history(manager, folder.name)
        if not entries or entries[-1][1].get('schema') != 'autospine.character-weighted-review/v1': continue
        review_sha, review = entries[-1]
        source_sha = old['artifact_sha256']
        source = manager.application.store.read(source_sha)
        receipt = json.loads(source.get('final-region-exclusion.json', b'{}'))
        if not predecessor(receipt.get('decisions'),expected,extended=extended): continue
        if json.loads(source['character-manifest.json'])['layers'] != old['layers']:
            raise PipelineRunError('character_binding_replay_source_invalid')
        raw = read_real_file(folder/'runtime/report.json', 64 << 20, 'historical runtime report')
        if sha256(raw).hexdigest() != old.get('runtime', {}).get('files', {}).get('report.json'):
            raise PipelineRunError('character_binding_replay_runtime_invalid')
        runtime = json.loads(raw)
        ready = (runtime.get('bundle_sha256') == source_sha and runtime.get('passed') is True
                 and old.get('runtime', {}).get('geometry_status') == 'passed')
        value = dict(project_id=old['project_id'], job_id=old['job_id'], artifact_sha256=source_sha,
            authority='none', can_review=ready, review=review, review_sha256=review_sha)
        accepted = confirmed_layers(old, value)
        if accepted: candidates.append((old, review_sha, source, accepted))
    if len(candidates) != 1: return None
    old, review_sha, source, accepted = candidates[0]
    allowed = {r['layer_id'] for r in result['layers'] if eligible(r)}
    retained = sorted(accepted & allowed & set(unchanged_layers(source, files,extended=True) if extended else unchanged_layers(source,files)))
    if not retained: return None
    latest = history(manager, old['job_id'])
    if not latest or latest[-1][0] != review_sha: return None
    proof = dict(schema='autospine.character-binding-replay/v5' if extended else SCHEMA,
        profile='extended-post-exclusion-binding-v1' if extended else PROFILE, project_id=result['project_id'], job_id=result['job_id'],
        artifact_sha256=result['artifact_sha256'], runtime_sha256=canonical_sha256(result['runtime']),
        layers_sha256=canonical_sha256(result['layers']), source_job_id=old['job_id'],
        source_bundle_sha256=old['artifact_sha256'], source_review_sha256=review_sha,
        accepted_layer_ids=retained, decision_source='verified_scope_replay', new_human_confirmation=False,
        whole_character_visual_replayed=False, authority='none', production_authorized=False)
    digest = canonical_sha256(proof); root = directory(manager.root/'binding-replay-evidence', create=True)
    publish_document(root/(digest+'.json'), proof, staging=root/'staging')
    return read_proof(manager, digest)
