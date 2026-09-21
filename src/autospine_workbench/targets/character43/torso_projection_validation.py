"""Fresh contact-preservation and coarse depth checks for a baked torso candidate."""
from hashlib import sha256
import math

from .affine_pose import sample
from .motion_depth import build as build_depth
from .motion_depth_overlap import inspect as inspect_overlap
from .motion_depth_order import build as order_candidate


def foot_vertices(document):
    feet={i for i,b in enumerate(document['bones']) if b['name'] in ('foot_l','foot_r')}
    output={}
    for slot,choices in document['skins'][0]['attachments'].items():
        data=choices[slot]['vertices']; i=vertex=0; selected=[]
        while i<len(data):
            count=data[i];i+=1; included=False
            for _ in range(count):
                bone,_,_,weight=data[i:i+4];i+=4
                included |= bone in feet and weight>0
            if included:selected.append(vertex)
            vertex+=1
        if selected:output[slot]=selected
    return output


def contact_preservation(original,candidate,animation,times):
    if (not times or len(times)>4096 or any(not math.isfinite(t) for t in times)
            or any(b<=a for a,b in zip(times,times[1:]))):
        raise ValueError('torso_contact_times_invalid')
    if ({k:v for k,v in original.items() if k!='animations'} !=
            {k:v for k,v in candidate.items() if k!='animations'}):
        raise ValueError('torso_contact_rig_changed')
    before,after=original['animations'][animation],candidate['animations'][animation]
    if {k:v for k,v in before.items() if k!='attachments'}!={k:v for k,v in after.items() if k!='attachments'}:
        raise ValueError('torso_contact_non_deform_change')
    selected=foot_vertices(original)
    maxima={slot:dict(slot=slot,vertex_count=len(indices),maximum_displacement_px=0.,worst_time=None)
            for slot,indices in selected.items()}
    for time in times:
        a=sample(original,animation,time)[0];b=sample(candidate,animation,time)[0]
        for slot,indices in selected.items():
            delta=max(math.dist(a[slot][i],b[slot][i]) for i in indices)
            if delta>maxima[slot]['maximum_displacement_px']:
                maxima[slot].update(maximum_displacement_px=delta,worst_time=time)
    records=list(maxima.values())
    return dict(profile='torso-bake-contact-preservation-v1',authority='none',
        status='foot_surface_unmeasured' if not records else
               'sampled_paths_preserved' if all(r['maximum_displacement_px']<=1e-7 for r in records) else 'foot_surface_changed',
        bone_animation_unchanged=True,records=records,sample_count=len(times),tolerance_px=1e-7,
        scope='unchanged_ankle_animation_and_sampled_foot_weighted_vertices_not_floor_or_sole_contact')


def depth_check(candidate,files,animation,bvh,mapping,*,kimodo=None,clip_bounds=None,yaw_degrees=None):
    depth=build_depth(candidate,bvh,mapping,kimodo=kimodo,clip_bounds=clip_bounds,yaw_degrees=yaw_degrees)
    depth,probe=inspect_overlap(candidate,files,animation,depth)
    proposed,order=order_candidate(candidate,animation,depth,probe)
    depth.update(order=order,selected=False,order_candidate_available=proposed is not None,
        scope='fresh_coarse_source_depth_and_deformed_alpha_overlap_not_local_torso_plane_or_gpu_depth',
        skeleton_sha256=sha256(files['skeleton.json']).hexdigest())
    return depth
