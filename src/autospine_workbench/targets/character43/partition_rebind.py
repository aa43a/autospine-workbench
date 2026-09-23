"""Duplicate selected triangle vertices and rebind only that region in setup space."""
from copy import deepcopy
from .affine_pose import matrices
from .deform_addition import entries,value
from ...resolved_project import canonical_sha256


def apply(document,plan,setup):
    slot,name=plan['slot'],plan['animation'];part=plan['partition']
    source=document['skins'][0]['attachments'][slot][slot]
    if canonical_sha256(source)!=part['mesh_sha256']:raise ValueError('partition_mesh_changed')
    if len(source['vertices'])==len(source['uvs']):raise ValueError('partition_weighted_mesh_required')
    triangles=[source['triangles'][i:i+3] for i in range(0,len(source['triangles']),3)]
    selected=set(part['triangles'])
    if not selected or len(selected)!=len(part['triangles']) or any(type(i) is not int or not 0<=i<len(triangles) for i in selected):
        raise ValueError('partition_selection_invalid')
    influences=entries(source);count=len(influences)
    if len(setup)!=count:raise ValueError('partition_setup_inventory')
    indices={b['name']:i for i,b in enumerate(document['bones'])}
    if part['bone'] not in indices:raise ValueError('partition_bone_missing')
    rest=deepcopy(document);rest['animations']={name:{}}
    a,b,c,d,x,y=matrices(rest,name,0)[part['bone']];det=a*d-b*c
    if abs(det)<1e-10:raise ValueError('partition_bind_singular')
    chosen=sorted({v for i in selected for v in triangles[i]})
    other={v for i,t in enumerate(triangles) if i not in selected for v in t}
    result=deepcopy(document);mesh=result['skins'][0]['attachments'][slot][slot]
    mapping={v:count+i for i,v in enumerate(chosen)};new_setup=deepcopy(setup)
    for v in chosen:
        px,py=setup[v][0]-x,setup[v][1]-y
        mesh['vertices'].extend([1,indices[part['bone']],(d*px-b*py)/det,(-c*px+a*py)/det,1.])
        mesh['uvs'].extend(source['uvs'][2*v:2*v+2]);new_setup.append(list(setup[v]))
    mesh['triangles']=[mapping[v] if i in selected else v for i,t in enumerate(triangles) for v in t]
    animation=result['animations'][name]
    if animation.get('deform'):raise ValueError('partition_legacy_deform_unsupported')
    tracks=animation.get('attachments',{}).get('default',{}).get(slot,{}).get(slot,{})
    old=tracks.get('deform',[]);size=2*sum(len(row) for row in influences)
    if old:tracks['deform']=[dict(time=k['time'],vertices=value(old,k['time'],size)+[0.]*(2*len(chosen))) for k in old]
    return result,new_setup,dict(selected_triangles=sorted(selected),target_bone=part['bone'],
        duplicated_vertices=mapping,boundary_pairs=[[v,mapping[v]] for v in chosen if v in other],
        original_vertex_count=count,shared_texture=True,unchanged_unselected_weights=True)
