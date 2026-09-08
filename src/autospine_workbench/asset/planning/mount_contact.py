"""Local alpha boundary evidence; projected contact never authorizes a mount."""
from hashlib import sha256
from io import BytesIO
import math
from PIL import Image
from ...resolved_project import canonical_sha256
from ..joints.chain_coverage import MAX_PIXELS

PROFILE='mount-local-boundary-v1'


def mask(layer, raw):
    if sha256(raw).hexdigest()!=layer['image_sha256']:raise ValueError('contact_image_changed')
    x,y,r,b=layer['bbox']
    with Image.open(BytesIO(raw)) as image:
        if image.size!=(r-x,b-y) or image.width*image.height>MAX_PIXELS:raise ValueError('contact_dimensions')
        alpha=image.convert('RGBA').getchannel('A').tobytes();width=image.width
    return {(x+i%width,y+i//width) for i,a in enumerate(alpha) if a>=8}


def boundary(points):
    return {p for p in points if any((p[0]+dx,p[1]+dy) not in points
                                    for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)))}


def local_pair(source, target, anchor, radius):
    if radius<1 or not all(math.isfinite(v) for v in anchor):raise ValueError('contact_roi_invalid')
    edge=boundary(source)
    if not edge:return {'status':'no_source_boundary','roi':None,'boundary_point':None,
                       'overlap_pixels':0,'boundary_near_target_pixels':0,'boundary_pair_pixels':0}
    point=min(edge,key=lambda p:((p[0]+.5-anchor[0])**2+(p[1]+.5-anchor[1])**2,p[1],p[0]))
    x,y=point;roi=[x-radius,y-radius,x+radius+1,y+radius+1]
    inside=lambda p:roi[0]<=p[0]<roi[2] and roi[1]<=p[1]<roi[3]
    local={p for p in source if inside(p)};local_edge={p for p in edge if inside(p)}
    # Boundary is computed before clipping: ROI borders are not attachment boundaries.
    target_edge=boundary(target)
    offsets=[(dx,dy) for dx in range(-3,4) for dy in range(-3,4)]
    near=lambda p,points:any((p[0]+dx,p[1]+dy) in points for dx,dy in offsets)
    count=sum(near(p,target) for p in local_edge)
    pairs=sum(near(p,target_edge) for p in local_edge)
    overlap=len(local & target)
    status=('boundary_pair_support' if pairs else 'boundary_over_target_interior' if count
            else 'overlap_only' if overlap else 'no_local_support')
    return {'status':status,'roi':roi,'boundary_point':[x+.5,y+.5],
            'overlap_pixels':overlap,'boundary_near_target_pixels':count,'boundary_pair_pixels':pairs}


def build(candidate, bindings, plan, mounts, images):
    if (canonical_sha256(plan)!=mounts['source_plan_sha256']
            or canonical_sha256(candidate)!=plan['source_candidate_sha256']
            or canonical_sha256(bindings)!=plan['source_bindings_sha256']
            or mounts['authority']!='none' or mounts['production_authorized'] is not False):
        raise ValueError('contact_source_mismatch')
    layers={r['layer_id']:r for r in candidate['layers']};cache={};rows=[]
    def pixels(layer_id):
        if layer_id not in cache:cache[layer_id]=mask(layers[layer_id],images[layer_id])
        return cache[layer_id]
    radius=max(1,math.ceil(mounts['character_height_px']*.04))
    for source in mounts['layers']:
        for option in source['mount_options']:
            allowed={option['bone_id']}
            if source['category']=='garment':allowed|={'chest','spine'}
            targets=[r for r in bindings['bindings'] if r['layer_id']!=source['layer_id']
                     and any(allowed & set(o['bone_ids']) for o in r['options'])]
            relations=[]
            for target in targets:
                result=local_pair(pixels(source['layer_id']),pixels(target['layer_id']),option['anchor_xy'],radius)
                relations.append({'target_layer_id':target['layer_id'],
                                  'target_image_sha256':target['image_sha256'],**result})
            rows.append({'layer_id':source['layer_id'],'name':source['name'],'bone_id':option['bone_id'],
                         'anchor_xy':option['anchor_xy'],'relations':relations,
                         'reason_code':'candidate_binding_options_not_approved_contacts' if targets else 'no_counterpart_candidate',
                         'selected_target':None,'status':'needs_review'})
    return {'schema':'autospine.mount-contact/v1','profile':PROFILE,
            'source_mount_sha256':canonical_sha256(mounts),'character_id':candidate['character_id'],
            'parameters':{'alpha_threshold':8,'roi_radius_px':radius,'proximity_chebyshev_px':3},
            'rows':rows,'authority':'none','production_authorized':False,'status':'needs_review'}


def validate(candidate, bindings, plan, mounts, images, document):
    if document!=build(candidate,bindings,plan,mounts,images):raise ValueError('contact_replay_mismatch')
    return document
