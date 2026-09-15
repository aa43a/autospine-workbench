"""Deterministic waist proposal for an isolated, chest-spanning garment component."""
import math
from statistics import median


def propose(alpha, origin, pose):
    if not {'chest','thigh_l','thigh_r'}<=set(pose):raise ValueError('skirt_body_reference_missing')
    chest=pose['chest'][:2];hips=[pose[k][:2] for k in ('thigh_l','thigh_r')]
    chest_y=origin[1]-chest[1];hip_y=origin[1]-sum(p[1] for p in hips)/2
    span=hip_y-chest_y
    if not math.isfinite(span) or span<8:raise ValueError('skirt_dress_body_span_invalid')
    cx=math.floor(chest[0]-origin[0]);cy=math.floor(chest_y)
    if not (0<=cx<alpha.width and 0<=cy<alpha.height) or alpha.getpixel((cx,cy))<8:
        raise ValueError('skirt_dress_chest_support_missing')
    # Search inside the torso, not the hanging hem or the anatomical pelvis origin.
    lo=max(1,math.ceil(chest_y+.2*span));hi=min(alpha.height-2,math.floor(chest_y+.6*span))
    rows={}
    for y in range(lo-1,hi+2):
        xs=[x for x in range(alpha.width) if alpha.getpixel((x,y))>=8]
        if xs and min(xs)<=cx<=max(xs):rows[y]=(min(xs),max(xs))
    candidates=[(median(rows[t][1]-rows[t][0]+1 for t in (y-1,y,y+1)),y)
                for y in range(lo,hi+1) if all(t in rows for t in (y-1,y,y+1))]
    if not candidates:raise ValueError('skirt_dress_waist_unobservable')
    _,y=min(candidates);left,right=rows[y]
    if right-left<2 or not any(alpha.getpixel((x,t))>=8 for t in range(math.ceil(hip_y),alpha.height) for x in range(alpha.width)):
        raise ValueError('skirt_dress_hem_missing')
    return dict(profile='isolated-dress-torso-width-v1',waist_y=y,overlap_x=[left,right],
        overlap_pixels=right-left+1,chest_local_y=chest_y,hip_hint_local_y=hip_y,
        search_interval=[lo,hi],authority='none',status='needs_review',
        reason_code='skirt_waist_anchor_review_required')
