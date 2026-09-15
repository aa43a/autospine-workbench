"""Binding-only continuity for a rebuilt, independently revalidated exclusion batch."""
from copy import deepcopy
from hashlib import sha256
import json

from .numeric_reference import read


def originals(files):
    receipt = json.loads(files.get('final-region-exclusion.json', b'{}'))
    if receipt.get('schema') != 'autospine.final-region-exclusion/v1': return None
    decisions = receipt.get('decisions', [])
    if not decisions or len(decisions) > 64: return None
    result = []
    for decision in decisions:
        replay = decision.get('scope_replay', {})
        if (replay.get('profile') != 'unchanged-static-region-scope-v1'
                or replay.get('new_human_confirmation') is not False or replay.get('authority') != 'none'):
            return None
        original = replay.get('original_decision')
        if not isinstance(original, dict): return None
        result.append(original)
    return result


def unchanged_layers(previous, current):
    expected = originals(current)
    old_receipt = json.loads(previous.get('final-region-exclusion.json', b'{}'))
    if (expected is None or old_receipt.get('schema') != 'autospine.final-region-exclusion/v1'
            or old_receipt.get('decisions') != expected): return []
    # A single explicit predecessor, never recursive decision/transform traversal.
    if any('scope_replay' in d for d in expected): return []
    manifests = [json.loads(f['character-manifest.json']) for f in (previous, current)]
    sources = [deepcopy(m.get('source_addresses', {})) for m in manifests]
    for source in sources: source.pop('base_bundle_sha256', None)
    if not sources[0] or sources[0] != sources[1]: return []
    docs = [json.loads(f['skeleton.json']) for f in (previous, current)]
    if not docs[0].get('bones') or docs[0]['bones'] != docs[1].get('bones'): return []
    if any(len(doc['skins']) != 1 for doc in docs): return []
    refs = [read(f) for f in (previous, current)]
    if any(ref['skeleton_sha256'] != sha256(f['skeleton.json']).hexdigest()
           for ref, f in zip(refs, (previous, current))): return []
    layers = [{r['layer_id']: r for r in m['layers']} for m in manifests]
    if any(len(rows) != len(m['layers']) for rows, m in zip(layers, manifests)): return []
    excluded = {(d['layer_id'], d['region_id']) for d in expected}
    result = []
    for key, old in layers[0].items():
        new = layers[1].get(key)
        if new is None: continue
        normalized = [deepcopy(r) for r in (old, new)]
        valid = True
        for row in normalized:
            for entry in row.get('excluded_regions', []):
                if (key, entry['region_id']) not in excluded: valid = False
                entry.pop('decision_sha256', None)
        if not valid or normalized[0] != normalized[1]: continue
        regions = [r['region_id'] for r in old['regions']]
        if not regions or len(set(regions)) != len(regions): continue
        for region in regions:
            slots = [[s for s in doc['slots'] if s['name'] == region] for doc in docs]
            attachments = [doc['skins'][0]['attachments'].get(region) for doc in docs]
            if len(slots[0]) != 1 or slots[0] != slots[1] or not attachments[0] or attachments[0] != attachments[1]:
                valid = False; break
            for name, attachment in attachments[0].items():
                texture = 'images/'+attachment.get('path', name)+'.png'
                if texture not in previous or previous[texture] != current.get(texture): valid = False
            tracks = [{name: [(f['time'], f['vertices'].get(region)) for f in frames]
                       for name, frames in ref['animations'].items()} for ref in refs]
            if tracks[0] != tracks[1] or any(points is None for track in tracks[0].values() for _, points in track):
                valid = False
        if valid: result.append(key)
    return sorted(result)
