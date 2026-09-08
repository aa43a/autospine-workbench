"""Constrained boundary hypotheses; preserve old local-contact diagnostics."""
import math
import numpy as np
from ...resolved_project import canonical_sha256
from .mount_contact import boundary, mask, local_pair

PROFILE='upper-edge-hand-window-wing-root-v1'
PARAMETERS={'garment_upper_fraction':.25,'hand_radius_height':.08,'wing_radius_height':.20,
            'candidate_limit':3,'spacing_height':.015,'max_pair_evaluations':50_000_000}


def search(source,target,bbox,anchor,kind,bone_id,height):
    if not math.isfinite(height) or height<=0 or not all(math.isfinite(v) for v in anchor):
        raise ValueError('contact_search_geometry_invalid')
    a=boundary(source);b=boundary(target);x,y,r,bottom=bbox
    if kind=='garment':
        a={p for p in a if p[1]+.5<=y+(bottom-y)*.25}
        policy='source_upper_quarter'
    elif kind=='prop' and bone_id in {'hand_l','hand_r'}:
        radius=height*.08;policy='hand_reference_window'
        a={p for p in a if math.dist((p[0]+.5,p[1]+.5),anchor)<=radius}
        b={p for p in b if math.dist((p[0]+.5,p[1]+.5),anchor)<=radius}
    elif kind=='wing':
        radius=height*.20;policy='torso_root_window'
        a={p for p in a if math.dist((p[0]+.5,p[1]+.5),anchor)<=radius}
        b={p for p in b if math.dist((p[0]+.5,p[1]+.5),anchor)<=radius}
    else:
        return {'policy':'unsupported_relation','reason_code':'requires_other_attachment_evidence','candidates':[]}
    if not a or not b:
        return {'policy':policy,'reason_code':'no_boundary_in_search_window','candidates':[]}
    if len(a)*len(b)>PARAMETERS['max_pair_evaluations']:
        return {'policy':policy,'reason_code':'pair_evaluation_limit','candidates':[]}
    aa=np.array(sorted(a,key=lambda p:(p[1],p[0])),dtype=np.float64)
    bb=np.array(sorted(b,key=lambda p:(p[1],p[0])),dtype=np.float64)
    ranked=[]
    for start in range(0,len(aa),64):
        chunk=aa[start:start+64];dist=((chunk[:,None,:]-bb[None,:,:])**2).sum(axis=2)
        indices=dist.argmin(axis=1)
        for i,j in enumerate(indices):
            p=chunk[i];q=bb[j]
            ranked.append((float(dist[i,j]),float(p[1]),float(p[0]),float(q[1]),float(q[0])))
    picked=[];spacing=max(8,height*.015)
    for d,sy,sx,ty,tx in sorted(ranked):
        point=[sx+.5,sy+.5]
        if any(math.dist(point,row['source_xy'])<spacing for row in picked):continue
        local=local_pair(source,target,point,max(1,math.ceil(height*.04)))
        picked.append({'source_xy':point,'target_xy':[tx+.5,ty+.5],'distance_px':round(math.sqrt(d),6),
                       'local_evidence':local})
        if len(picked)==3:break
    return {'policy':policy,'reason_code':'geometry_candidates_require_semantic_review','candidates':picked}


def build(candidate,mounts,contacts,images):
    if (contacts['source_mount_sha256']!=canonical_sha256(mounts)
            or contacts['authority']!='none' or mounts['authority']!='none'
            or contacts['production_authorized'] is not False or mounts['production_authorized'] is not False):
        raise ValueError('contact_search_source_mismatch')
    layers={r['layer_id']:r for r in candidate['layers']}
    kinds={r['layer_id']:r['category'] for r in mounts['layers']};cache={};rows=[]
    def pixels(key):
        if key not in cache:cache[key]=mask(layers[key],images[key])
        return cache[key]
    for row in contacts['rows']:
        for relation in row['relations']:
            source_id=row['layer_id'];target_id=relation['target_layer_id']
            result=search(pixels(source_id),pixels(target_id),layers[source_id]['bbox'],
                          row['anchor_xy'],kinds[source_id],row['bone_id'],mounts['character_height_px'])
            rows.append({'layer_id':source_id,'name':row['name'],'target_layer_id':target_id,
                         'bone_id':row['bone_id'],'baseline_status':relation['status'],**result,
                         'selected_candidate':None,'status':'needs_review'})
    return {'schema':'autospine.mount-contact-search/v1','profile':PROFILE,
            'source_contact_sha256':canonical_sha256(contacts),'character_id':candidate['character_id'],
            'parameters':dict(PARAMETERS),'rows':rows,'authority':'none','production_authorized':False,'status':'needs_review'}


def validate(candidate,mounts,contacts,images,document):
    if document!=build(candidate,mounts,contacts,images):raise ValueError('contact_search_replay_mismatch')
    return document
