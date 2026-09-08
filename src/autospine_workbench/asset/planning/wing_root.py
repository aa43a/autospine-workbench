"""Torso-facing component roots with projected coverage, never inferred hidden pixels."""
import math
from ...resolved_project import canonical_sha256
from .mount_contact import mask, boundary, local_pair

PROFILE='wing-component-inward-root-v1'
PARAMETERS={'inward_band_height':.01,'minimum_component_pixels':16,'root_limit_per_component':3,
            'spacing_height':.01,'corridor_samples':33,'component_limit':4096}


def components(points):
    remaining=set(points);groups=[]
    # Seed ordering is applied to groups afterward; component membership is order-independent.
    while remaining:
        seed=remaining.pop();group={seed};stack=[seed]
        while stack:
            x,y=stack.pop()
            for q in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if q in remaining:remaining.remove(q);group.add(q);stack.append(q)
        groups.append(group)
        if len(groups)>4096:raise ValueError('wing_root_component_limit')
    return sorted(groups,key=lambda g:(-len(g),min((y,x) for x,y in g)))


def analyze(source,target,anchor,height):
    if not math.isfinite(height) or height<=0 or not all(math.isfinite(v) for v in anchor):
        raise ValueError('wing_root_geometry_invalid')
    rows=[]
    for index,group in enumerate(components(source)):
        centroid=[sum(p[j]+.5 for p in group)/len(group) for j in (0,1)]
        row={'component_id':index,'area_pixels':len(group),'centroid_xy':centroid,
             'projected_target_coverage':round(len(group & target)/len(group),8),'roots':[]}
        if len(group)<16:
            row['reason_code']='small_component_retained_without_root';rows.append(row);continue
        direction=[anchor[j]-centroid[j] for j in (0,1)]
        edge=boundary(group)
        inward={p for p in edge if sum((p[j]+.5-centroid[j])*direction[j] for j in (0,1))>0}
        if not inward:
            row['reason_code']='inward_direction_unobservable';rows.append(row);continue
        distance=lambda p:math.dist((p[0]+.5,p[1]+.5),anchor)
        closest=min(map(distance,inward));band=height*.01
        ordered=sorted((p for p in inward if distance(p)<=closest+band),key=lambda p:(distance(p),p[1],p[0]))
        for p in ordered:
            xy=[p[0]+.5,p[1]+.5]
            if any(math.dist(xy,r['source_xy'])<max(8,height*.01) for r in row['roots']):continue
            samples=[(math.floor(xy[0]+(anchor[0]-xy[0])*i/32),math.floor(xy[1]+(anchor[1]-xy[1])*i/32)) for i in range(33)]
            local=local_pair(group,target,xy,max(1,math.ceil(height*.02)))
            row['roots'].append({'source_xy':xy,'anchor_distance_px':round(distance(p),6),
              'target_opaque_at_root':p in target,'target_corridor_samples':sum(q in target for q in samples),
              'local_evidence':local})
            if len(row['roots'])==3:break
        row['reason_code']='inward_roots_need_attachment_and_occlusion_review';rows.append(row)
    return rows


def build(candidate,mounts,contacts,previous,images):
    if (canonical_sha256(contacts)!=previous['source_contact_sha256']
            or canonical_sha256(mounts)!=contacts['source_mount_sha256']
            or previous['authority']!='none' or previous['production_authorized'] is not False):
        raise ValueError('wing_root_source_mismatch')
    layers={r['layer_id']:r for r in candidate['layers']};kinds={r['layer_id']:r['category'] for r in mounts['layers']};rows=[]
    for row in contacts['rows']:
        if kinds[row['layer_id']]!='wing':continue
        source=mask(layers[row['layer_id']],images[row['layer_id']])
        for relation in row['relations']:
            target_id=relation['target_layer_id'];target=mask(layers[target_id],images[target_id])
            prior=next(r for r in previous['rows'] if r['layer_id']==row['layer_id'] and r['target_layer_id']==target_id and r['bone_id']==row['bone_id'])
            rows.append({'layer_id':row['layer_id'],'name':row['name'],'target_layer_id':target_id,
              'bone_id':row['bone_id'],'anchor_xy':row['anchor_xy'],
              'previous_points':[c['source_xy'] for c in prior['candidates']],
              'components':analyze(source,target,row['anchor_xy'],mounts['character_height_px']),
              'selected_root':None,'draw_order_reviewed':False,'occlusion_verified':False})
    return {'schema':'autospine.wing-root/v1','profile':PROFILE,
            'source_search_sha256':canonical_sha256(previous),'character_id':candidate['character_id'],
            'parameters':dict(PARAMETERS),'rows':rows,'authority':'none','production_authorized':False,'status':'needs_review'}


def validate(candidate,mounts,contacts,previous,images,document):
    if document!=build(candidate,mounts,contacts,previous,images):raise ValueError('wing_root_replay_mismatch')
    return document
