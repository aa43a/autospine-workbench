"""Prove unchanged binding scope across an exact final static-region exclusion."""
from copy import deepcopy
from hashlib import sha256
import json
from ...resolved_project import canonical_sha256
from .numeric_reference import read


def unchanged_layers(source, target, *, after_components=False):
    receipt=json.loads(target['final-region-exclusion.json'])
    source_sha=canonical_sha256({n:sha256(b).hexdigest() for n,b in source.items()})
    if (receipt.get('schema')!=('autospine.final-region-exclusion/v2' if after_components else 'autospine.final-region-exclusion/v1')
            or receipt.get('source_bundle_sha256')!=source_sha
            or receipt.get('execution_stage')!=('after_components' if after_components else 'after_motion_texture_skirt')
            or receipt.get('authority')!='none' or receipt.get('production_authorized') is not False):
        raise ValueError('character_binding_continuity_source')
    decisions=receipt['decisions']; removed={d['region_id'] for d in decisions}
    if not decisions or len(removed)!=len(decisions): raise ValueError('character_binding_continuity_scope')
    old=json.loads(source['character-manifest.json']); new=json.loads(target['character-manifest.json'])
    if old['source_addresses']!=new['source_addresses']: raise ValueError('character_binding_continuity_source')
    for d in decisions:
        rows=[r for l in old['layers'] if l['layer_id']==d['layer_id'] for r in l['regions'] if r['region_id']==d['region_id']]
        if (len(rows)!=1 or rows[0]['state']!='static_reference' or d.get('decision_source')!='human_confirmation'
                or d.get('source_bundle_sha256')!=source_sha or d.get('reversible') is not True):
            raise ValueError('character_binding_continuity_scope')
        attachment=json.loads(source['skeleton.json'])['skins'][0]['attachments'][d['region_id']][d['region_id']]
        image='images/'+attachment.get('path',d['region_id'])+'.png'
        if d.get('manifest_sha256')!=sha256(source['character-manifest.json']).hexdigest() or d.get('image_sha256')!=sha256(source[image]).hexdigest():
            raise ValueError('character_binding_continuity_source')
    if {n:b for n,b in source.items() if n.endswith('.png')}!={n:b for n,b in target.items() if n.endswith('.png')}:
        raise ValueError('character_binding_continuity_texture')
    if source['skeleton.atlas']!=target['skeleton.atlas']: raise ValueError('character_binding_continuity_texture')
    for name in ('skeleton.json','editor/skeleton.json'):
        if name not in source and name not in target: continue
        skeleton=deepcopy(json.loads(source[name]))
        skeleton['slots']=[s for s in skeleton['slots'] if s['name'] not in removed]
        for slot in removed: del skeleton['skins'][0]['attachments'][slot]
        if skeleton!=json.loads(target[name]): raise ValueError('character_binding_continuity_geometry')
    references=[read(source),read(target)]
    for files,reference in zip((source,target),references):
        if reference['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest():
            raise ValueError('character_binding_continuity_motion')
    before,after=[reference['animations'] for reference in references]
    if set(before)!=set(after): raise ValueError('character_binding_continuity_motion')
    for animation,frames in before.items():
        if len(frames)!=len(after[animation]): raise ValueError('character_binding_continuity_motion')
        for a,b in zip(frames,after[animation]):
            expected={**a,'vertices':{k:v for k,v in a['vertices'].items() if k not in removed}}
            if expected!=b: raise ValueError('character_binding_continuity_motion')
    layers={l['layer_id']:l for l in old['layers']}
    return sorted(l['layer_id'] for l in new['layers'] if layers.get(l['layer_id'])==l)
