"""Revalidate existing human exclusions on unchanged, source-bound static regions."""
from copy import deepcopy
from hashlib import sha256
import json

from ...resolved_project import canonical_sha256
from .numeric_reference import read
from .region_exclusion import apply


def digest(files):
    return canonical_sha256({name: sha256(raw).hexdigest() for name, raw in files.items()})


def revalidate(previous, current, decisions):
    """No new approval: prove each original decision's complete region scope unchanged."""
    if not decisions or len(decisions) > 64:
        raise ValueError('character_region_revalidation_scope')
    before, after = (json.loads(files['character-manifest.json']) for files in (previous, current))
    sources = [deepcopy(m.get('source_addresses', {})) for m in (before, after)]
    for source in sources:
        source.pop('base_bundle_sha256', None)
    if not sources[0] or sources[0] != sources[1]:
        raise ValueError('character_region_revalidation_sources')
    docs = [json.loads(files['skeleton.json']) for files in (previous, current)]
    if docs[0].get('bones') != docs[1].get('bones'):
        raise ValueError('character_region_revalidation_bones')
    refs = [read(files) for files in (previous, current)]
    previous_digest, current_digest = digest(previous), digest(current)
    keys = [(d['layer_id'], d['region_id']) for d in decisions]
    if len(set(keys)) != len(keys):
        raise ValueError('character_region_revalidation_duplicate')
    result = []
    for decision in decisions:
        if decision.get('source_bundle_sha256') != previous_digest or decision.get('reversible') is not True:
            raise ValueError('character_region_revalidation_decision')
        # Verifies original human provenance, image, static state and animation dependencies.
        apply(previous, decision)
        region = decision['region_id']
        layers = [[r for r in m['layers'] if r['layer_id'] == decision['layer_id']] for m in (before, after)]
        if len(layers[0]) != 1 or layers[0] != layers[1]:
            raise ValueError('character_region_revalidation_layer')
        for key in ('slots', 'skins'):
            if key == 'slots':
                values = [[s for s in doc[key] if s['name'] == region] for doc in docs]
            else:
                values = [[skin.get('attachments', {}).get(region) for skin in doc[key]] for doc in docs]
            if values[0] != values[1]:
                raise ValueError('character_region_revalidation_geometry')
        trajectories = [{name: [(f['time'], f['vertices'].get(region)) for f in frames]
                         for name, frames in ref['animations'].items()} for ref in refs]
        if trajectories[0] != trajectories[1]:
            raise ValueError('character_region_revalidation_motion')
        derived = dict(decision, source_bundle_sha256=current_digest,
            manifest_sha256=sha256(current['character-manifest.json']).hexdigest(),
            scope_replay=dict(profile='unchanged-static-region-scope-v1', authority='none',
                new_human_confirmation=False, original_decision=deepcopy(decision)))
        apply(current, derived)
        result.append(derived)
    return result
