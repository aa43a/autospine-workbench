"""Apply an exact, explicit static-region exclusion while preserving remaining geometry."""
from hashlib import sha256
import json
from ...automation.storage_io import canonical_bytes
from .numeric_reference import read as read_reference, write as write_reference


def apply(files, decision):
    automatic=decision.get('schema')=='autospine.region-exclusion/v2' and decision.get('decision_source')=='policy_auto'
    if automatic:
        from .low_alpha_residual import validate
        validate(files,decision)
    elif decision.get('schema') != 'autospine.region-exclusion/v1' or decision.get('decision_source') != 'human_confirmation':
        raise ValueError('character_region_exclusion_decision')
    manifest = json.loads(files['character-manifest.json'])
    if decision['manifest_sha256'] != sha256(files['character-manifest.json']).hexdigest():
        raise ValueError('character_region_exclusion_stale')
    region = decision['region_id']; source = decision['layer_id']
    layers = [r for r in manifest['layers'] if r['layer_id'] == source]
    if len(layers) != 1 or not any(r['region_id'] == region and r['state'] == 'static_reference' for r in layers[0]['regions']):
        raise ValueError('character_region_exclusion_not_static')
    doc = json.loads(files['skeleton.json']); reference = read_reference(files)
    if reference['skeleton_sha256'] != sha256(files['skeleton.json']).hexdigest():
        raise ValueError('character_region_exclusion_reference')
    attachment = doc['skins'][0]['attachments'][region][region]
    texture = 'images/'+attachment.get('path', region)+'.png'
    if sha256(files[texture]).hexdigest() != decision['image_sha256']:
        raise ValueError('character_region_exclusion_stale')
    for animation in doc['animations'].values():
        if animation.get('drawOrder') or animation.get('draworder') or region in animation.get('slots', {}) \
                or any(region in choices for choices in animation.get('attachments', {}).values()):
            raise ValueError('character_region_exclusion_animated_dependency')
    if len(doc['skins']) != 1 or sum(s['name'] == region for s in doc['slots']) != 1:
        raise ValueError('character_region_exclusion_inventory')
    doc['slots'] = [s for s in doc['slots'] if s['name'] != region]
    del doc['skins'][0]['attachments'][region]
    for frames in reference['animations'].values():
        for frame in frames:
            del frame['vertices'][region]
    layer = layers[0]
    layer['regions'] = [r for r in layer['regions'] if r['region_id'] != region]
    layer.setdefault('excluded_regions', []).append(dict(region_id=region, decision_sha256=sha256(canonical_bytes(decision)).hexdigest()))
    states = {r['state'] for r in layer['regions']}
    if 'static_reference' not in states:
        layer['reason_codes'] = [r for r in layer['reason_codes'] if r not in ('residual_binding_required', 'static_reference_not_bound')]
    layer['state'] = next(iter(states)) if len(states) == 1 and not layer['missing_region_ids'] else 'partial'
    if not layer['regions'] and not layer['missing_region_ids']: layer['state'] = 'excluded'
    manifest.get('region_owners', {}).pop(region, None)
    manifest.update(profile='automatic-low-alpha-residual-v1' if automatic else 'reviewed-static-region-exclusion-v1', status='needs_review',
                    authority='none', production_authorized=False, full_character_animation=False,
                    qa={'runtime_status': 'not_run', 'full_character_contact_status': 'not_evaluated'})
    result = {n: raw for n, raw in files.items() if n.endswith('.png') or n in ('skeleton.atlas', 'binding-provenance.json')}
    result.update({n: raw for n, raw in files.items() if n.startswith('region-exclusions/')})
    if 'region-exclusion.json' in files:
        previous = files['region-exclusion.json']
        result['region-exclusions/'+sha256(previous).hexdigest()+'.json'] = previous
    result['skeleton.json'] = canonical_bytes(doc)
    if 'editor/skeleton.json' in files:
        editor = json.loads(files['editor/skeleton.json'])
        editor['slots'] = [s for s in editor['slots'] if s['name'] != region]
        del editor['skins'][0]['attachments'][region]
        result['editor/skeleton.json'] = canonical_bytes(editor)
    reference['skeleton_sha256'] = sha256(result['skeleton.json']).hexdigest()
    result = write_reference(result, reference)
    result['region-exclusion.json'] = canonical_bytes(decision)
    manifest['files'] = {n: sha256(raw).hexdigest() for n, raw in result.items()}
    result['character-manifest.json'] = canonical_bytes(manifest)
    return result
