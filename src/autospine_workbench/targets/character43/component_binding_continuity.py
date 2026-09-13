"""Prove the unmodified binding scope around one component replacement."""
from copy import deepcopy
from hashlib import sha256
import json
from ...resolved_project import canonical_sha256
from .numeric_reference import read


def unchanged_layers(source,target):
    report=json.loads(target['component-mount.json'])
    digest=canonical_sha256({n:sha256(b).hexdigest() for n,b in source.items()})
    if (report.get('schema')!='autospine.character-component-mount/v1' or report.get('source_bundle_sha256')!=digest
            or report.get('authority')!='none' or report.get('production_authorized') is not False
            or report.get('draw_order')!='replace_source_slot_in_place'
            or report.get('motion')!='rigid_parent_follow_no_added_tracks'):
        raise ValueError('component_binding_continuity_source')
    slot=report['source_region_id'];parts=report['parts'];added={p['region_id'] for p in parts}
    if not parts or len(parts)>65 or len(added)!=len(parts) or slot in added:
        raise ValueError('component_binding_continuity_scope')
    old=json.loads(source['character-manifest.json']);new=json.loads(target['character-manifest.json'])
    if old['source_addresses']!=new['source_addresses']: raise ValueError('component_binding_continuity_source')
    changed=[l['layer_id'] for l in old['layers'] if any(r['region_id']==slot for r in l['regions'])]
    if changed!=[report['layer_id']]: raise ValueError('component_binding_continuity_scope')
    for name,raw in source.items():
        if name.endswith('.png') and target.get(name)!=raw: raise ValueError('component_binding_continuity_texture')
    atlas=source['skeleton.atlas'].decode()
    for part in parts:
        name=part['region_id'];left,top,right,bottom=part['bbox'];w=right-left;h=bottom-top
        if any(c in name for c in '\r\n'): raise ValueError('component_binding_continuity_scope')
        atlas+=f'\ntextures/{name}.png\nsize: {w+4},{h+4}\nfilter: Linear,Linear\npma: false\nrepeat: none\n{name}\nbounds: 2,2,{w},{h}\n\n'
    if target['skeleton.atlas']!=atlas.encode(): raise ValueError('component_binding_continuity_texture')
    for name in ('skeleton.json','editor/skeleton.json'):
        a=json.loads(source[name]);b=deepcopy(json.loads(target[name]))
        original_paths={attachment.get('path',key) for entries in a['skins'][0]['attachments'].values()
                        for key,attachment in entries.items()}
        if added & original_paths: raise ValueError('component_binding_continuity_texture')
        original=next(s for s in a['slots'] if s['name']==slot)
        expected=[s for s in a['slots'] if s['name']!=slot]
        if [s for s in b['slots'] if s['name'] not in added]!=expected:
            raise ValueError('component_binding_continuity_order')
        at=a['slots'].index(original)
        if [s['name'] for s in b['slots'][at:at+len(parts)]]!=[p['region_id'] for p in parts]:
            raise ValueError('component_binding_continuity_order')
        if added & set(a['skins'][0]['attachments']): raise ValueError('component_binding_continuity_scope')
        b['slots'][at:at+len(parts)]=[original]
        for region in added: del b['skins'][0]['attachments'][region]
        b['skins'][0]['attachments'][slot]=a['skins'][0]['attachments'][slot]
        if a!=b: raise ValueError('component_binding_continuity_geometry')
    refs=[read(source),read(target)]
    for files,ref in zip((source,target),refs):
        if ref['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest(): raise ValueError('component_binding_continuity_motion')
    a,b=[r['animations'] for r in refs]
    if set(a)!=set(b): raise ValueError('component_binding_continuity_motion')
    for animation,frames in a.items():
        if len(frames)!=len(b[animation]): raise ValueError('component_binding_continuity_motion')
        for before,after in zip(frames,b[animation]):
            restored={**after,'vertices':{k:v for k,v in after['vertices'].items() if k not in added}}
            restored['vertices'][slot]=before['vertices'][slot]
            if restored!=before: raise ValueError('component_binding_continuity_motion')
    layers={l['layer_id']:l for l in old['layers']}
    return sorted(l['layer_id'] for l in new['layers'] if l['layer_id'] not in changed and layers.get(l['layer_id'])==l)
