"""Compose selected rigid quads with unchanged candidate partition animations."""
from copy import deepcopy
import math
from ...resolved_project import canonical_sha256
from ...benchmark.layer_binding_draft import validate_layer_binding_draft


def compose(doc, source, skeleton, atlas, bindings, draft):
    validate_layer_binding_draft(bindings, draft)
    if bindings['candidate_sha256'] != canonical_sha256(source) or bindings['source_skeleton_sha256'] != canonical_sha256(skeleton):
        raise ValueError('mixed_binding_source')
    if atlas['source_skeleton_sha256'] != canonical_sha256(skeleton):
        raise ValueError('mixed_partition_skeleton')
    expected = []
    for bone in skeleton['bones']:
        local=bone['setup_local']; row=dict(name=bone['id'],x=local['x'],y=-local['y'],rotation=-local['rotation_degrees'],length=bone['length'])
        if bone['parent_id'] is not None: row['parent']=bone['parent_id']
        expected.append(row)
    if doc['bones'] != expected: raise ValueError('mixed_bone_setup')
    owners={p['id']:l['layer_id'] for l in atlas['layers'] for p in l['partitions']}
    if set(owners) != set(doc['skins'][0]['attachments']): raise ValueError('mixed_partition_inventory')
    result=deepcopy(doc); attachments=result['skins'][0]['attachments']
    originals={r['layer_id']:r for r in source['layers']}; options={r['layer_id']:r for r in bindings['bindings']}
    indices={b['name']:i for i,b in enumerate(doc['bones'])}; rigid=[]; excluded=[]
    represented=set(owners.values())
    for record in draft['records']:
        name=record['layer_id']
        if name in represented: continue  # Existing partition candidates retain their own review status.
        if record['action']!='bind':
            excluded.append(dict(layer_id=name,reason_code='binding_'+record['action']));continue
        option=next(o for o in options[name]['options'] if o['id']==record['option_id'])
        if option['mode']!='rigid':
            excluded.append(dict(layer_id=name,reason_code='selected_mesh_candidate_not_integrated'));continue
        x,y,r,b=originals[name]['bbox'];w,h=r-x,b-y
        if min(w,h)<=0:raise ValueError('mixed_empty_region')
        local=option['setup_local'];angle=math.radians(-local['rotation_degrees']);vertices=[]
        bone=option['bone_ids'][0]
        for px,py in ((-w/2,h/2),(w/2,h/2),(w/2,-h/2),(-w/2,-h/2)):
            lx=local['x']+px*math.cos(angle)-py*math.sin(angle)
            ly=-local['y']+px*math.sin(angle)+py*math.cos(angle)
            if not all(math.isfinite(v) for v in (lx,ly)):raise ValueError('mixed_nonfinite')
            vertices.extend([1,indices[bone],lx,ly,1])
        attachments[name]={name:dict(type='mesh',path=name,uvs=[0,0,1,0,1,1,0,1],triangles=[0,1,2,0,2,3],vertices=vertices,width=w,height=h)}
        result['slots'].append(dict(name=name,bone=bone,attachment=name));rigid.append(name);owners[name]=name
    order={r['layer_id']:i for i,r in enumerate(source['layers'])}
    result['slots'].sort(key=lambda s:order[owners[s['name']]])
    return result,rigid,excluded
