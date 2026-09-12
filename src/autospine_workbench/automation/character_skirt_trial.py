"""Optional whole-character skirt candidate, never an implicit binding decision."""
import json
from .pipeline_run import PipelineRunError

PROFILE = 'fixed-waist-three-chain-v1'


def validate(profile):
    if profile is not None and profile != PROFILE:
        raise PipelineRunError('character_skirt_profile_invalid')


def apply_selected(manager, request, result):
    profile = request.get('skirt_profile')
    validate(profile)
    if profile is None:
        return result
    from ..targets.character43.skirt_candidate import generate
    store = manager.application.store
    files = store.read(result['artifact_sha256'])
    manifest = json.loads(files['character-manifest.json'])
    layer_ids = sorted(row['layer_id'] for row in manifest['layers']
                       if row['name'] in ('bottomwear', 'bottomwear-front')
                       and row['state'] == 'static_reference')
    if not layer_ids:
        raise PipelineRunError('character_skirt_layers_missing')
    output, report = generate(files, result['artifact_sha256'], layer_ids)
    applied = dict(result, artifact_sha256=store.publish(output),
                manifest=json.loads(output['character-manifest.json']),
                skirt_trial=dict(profile=profile, layer_ids=[r['layer_id'] for r in report['rows']],
                    source_artifact_sha256=result['artifact_sha256'],
                    geometry_passed=report['geometry_passed'], setup_error_px=report['setup_error_px'],
                    authority='none', selected=False))
    if report.get('blocked_layers'): applied['skirt_trial']['blocked_layers'] = report['blocked_layers']
    return applied
