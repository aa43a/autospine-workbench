"""Exclude reviewed residuals after all transforms, without rerunning texture transfer."""
from hashlib import sha256
import json
from ...automation.storage_io import canonical_bytes
from ...resolved_project import canonical_sha256
from .region_exclusion import apply
from .deformation_qa import inspect


def apply_batch(files, decisions):
    if not decisions or len(decisions) > 64:
        raise ValueError('character_final_exclusion_scope')
    keys = [(d['layer_id'], d['region_id']) for d in decisions]
    if len(set(keys)) != len(keys): raise ValueError('character_final_exclusion_duplicate')
    digest = canonical_sha256({n: sha256(b).hexdigest() for n, b in files.items()})
    # Validate every requested region against the same reviewed input before any change.
    for decision in decisions:
        if decision.get('source_bundle_sha256') != digest:
            raise ValueError('character_final_exclusion_source')
        apply(files, decision)
    output = files
    for decision in sorted(decisions, key=lambda d: (d['layer_id'], d['region_id'])):
        current = dict(decision,
                       source_bundle_sha256=canonical_sha256({n: sha256(b).hexdigest() for n,b in output.items()}),
                       manifest_sha256=sha256(output['character-manifest.json']).hexdigest(),
                       scope_replay=dict(profile='same-reviewed-final-batch-v1',
                           original_decision=decision, new_human_confirmation=False, authority='none'))
        output = apply(output, current)
    # Skirt geometry is untouched and remains available to the captured timeline.
    if 'skirt-trial.json' in files: output['skirt-trial.json'] = files['skirt-trial.json']
    # Preserve earlier evidence as provenance, not as a claim about the modified scene.
    for name in ('residual-transfer.json', 'deformation.json'):
        if name in files: output['pre-exclusion-evidence/'+name] = files[name]
    output['deformation.json'] = canonical_bytes(inspect(output))
    receipt = dict(schema='autospine.final-region-exclusion/v1', authority='none',
                   production_authorized=False, source_bundle_sha256=digest,
                   decisions=sorted(decisions, key=lambda d: (d['layer_id'], d['region_id'])),
                   execution_stage='after_motion_texture_skirt', runtime_status='not_run')
    output['final-region-exclusion.json'] = canonical_bytes(receipt)
    manifest = json.loads(output['character-manifest.json'])
    manifest['files'] = {n: sha256(b).hexdigest() for n, b in output.items() if n != 'character-manifest.json'}
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output
