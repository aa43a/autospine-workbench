"""Mutually exclusive regional artwork slots, with unchanged geometry and motion."""
from copy import deepcopy
import math
from ...resolved_project import canonical_sha256


def build(document, plan, texture):
    name,slot=plan['animation'],plan['slot'];mapping=plan['mapping']
    if len(document['skins'])!=1 or document['skins'][0].get('name')!='default' or set(document['animations'])!={name}:
        raise ValueError('material_scene_skin_or_animation')
    motion=document['animations'][name]
    if motion.get('drawOrder') or motion.get('deform') or motion.get('slots',{}).get(slot):
        raise ValueError('material_scene_existing_order_or_slot_tracks')
    mesh=document['skins'][0]['attachments'][slot][slot]
    if canonical_sha256(mesh)!=mapping['mesh_sha256'] or mesh.get('type')!='mesh':
        raise ValueError('material_scene_mesh_changed')
    selected=mapping['triangles'];start,end=mapping['interval'];count=len(mesh['triangles'])//3
    if (not selected or len(set(selected))!=len(selected) or any(type(i) is not int or not 0<=i<count for i in selected)
            or not all(type(t) in (float,int) and math.isfinite(t) for t in (start,end)) or not 0<=start<end):
        raise ValueError('material_scene_mapping_invalid')
    if (mapping['uv_policy']!='same_canvas_original_uv' or mapping['geometry_policy']!='preserve_original_weights_and_deform'
            or mapping['activation_policy']!='start_inclusive_end_exclusive_not_blend_or_visual_acceptance'):
        raise ValueError('material_scene_policy_unsupported')
    old=next(s for s in document['slots'] if s['name']==slot)
    if old.get('color','ffffffff')!='ffffffff' or old.get('blend','normal')!='normal' or old.get('attachment')!=slot:
        raise ValueError('material_scene_slot_style')
    doc=deepcopy(document);motion=doc['animations'][name];attachments=doc['skins'][0]['attachments']
    included=[v for i in range(count) if i in set(selected) for v in mesh['triangles'][3*i:3*i+3]]
    rest=[v for i in range(count) if i not in set(selected) for v in mesh['triangles'][3*i:3*i+3]]
    original=slot+'-material-original' if rest else slot;replacement=slot+'-material-replacement'
    added=[original,replacement] if rest else [replacement]
    if any(s['name'] in added for s in doc['slots']):raise ValueError('material_scene_name_collision')
    def subset(indices,path):
        value=deepcopy(mesh);value.update(triangles=indices,path=path)
        value.pop('hull',None);value.pop('edges',None);return value
    if rest:attachments[slot][slot]=subset(rest,mesh.get('path',slot))
    attachments[original]={original:subset(included,mesh.get('path',slot))}
    attachments[replacement]={replacement:subset(included,texture)}
    at=next(i for i,s in enumerate(doc['slots']) if s['name']==slot)+1
    doc['slots'][at:at]=[dict(old,name=s,attachment=s) for s in added]
    # Setup remains the original art. During animation alpha steps are complementary.
    next(s for s in doc['slots'] if s['name']==replacement)['color']='ffffff00'
    times=sorted({0.,start,end})
    for target,invert in ((original,True),(replacement,False)):
        motion.setdefault('slots',{})[target]={'alpha':[dict(time=t,value=int((start<=t<end)!=invert),curve='stepped') for t in times]}
    old_track=document['animations'][name].get('attachments',{}).get('default',{}).get(slot,{}).get(slot)
    if old_track:
        for target in added:motion.setdefault('attachments',{}).setdefault('default',{})[target]={target:deepcopy(old_track)}
    return doc,dict(original_region_slot=original,replacement_slot=replacement,added_slots=added,
        source_slot=slot,interval=[start,end],selected_triangles=selected,
        geometry_unchanged=True,authority='none',selected=False)
