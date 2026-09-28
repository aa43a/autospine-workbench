"""Declared knuckle plane observations; no claim about texture palm/back identity."""
import json
import math
from ...bvh_parser import parse_bvh
from ...bvh_fk import _world_matrices,_origin,bvh_frame_ticks
from .oblique_source import _basis
from .oblique_motion import project


def plane(wrist,index,pinky):
    if any(len(v)!=3 or not all(math.isfinite(x) for x in v) for v in (wrist,index,pinky)):
        raise ValueError('palm_plane_points_invalid')
    a=[x-y for x,y in zip(index,wrist)];b=[x-y for x,y in zip(pinky,wrist)]
    cross=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
    size=math.hypot(*cross);scale=math.hypot(*a)*math.hypot(*b)
    if scale<=1e-12 or size/scale<1e-4:raise ValueError('palm_plane_degenerate')
    normal=[v/size for v in cross]
    return dict(normal=normal,projected_area_fraction=abs(normal[2]),signed_facing=normal[2])


def extract(bundle,*,yaw=0,camera_keys=None):
    if not math.isfinite(yaw) or abs(yaw)>90:raise ValueError('palm_plane_yaw_invalid')
    if bundle.source_kind!='bvh':raise ValueError('palm_plane_source_unsupported')
    mapping=json.loads((bundle.path/'map.json').read_bytes())
    if mapping['map_id']!='mixamo-declared-body-v1':raise ValueError('palm_plane_map_unsupported')
    bvh=parse_bvh(bundle.raw_bvh);lookup={j.name:i for i,j in enumerate(bvh.joints)}
    roles={r['role']:r for r in mapping['bones']};chains={}
    for side in ('left','right'):
        aim=roles['humanoid.arm.lower.'+side]['aim'];w=aim.get('joint_name');expected=side.title()+'Hand'
        if aim['kind']!='joint' or w not in (expected,'mixamorig:'+expected):raise ValueError('palm_plane_wrist_undeclared')
        joints=[w,w+'Index1',w+'Pinky1']
        if any(n not in lookup for n in joints) or any(bvh.joints[lookup[n]].parent_index!=lookup[w] for n in joints[1:]):
            raise ValueError('palm_plane_knuckles_missing')
        chains[side]=joints
    rows=[]
    ticks=bvh_frame_ticks(bvh)
    from .camera_track import at_times
    if camera_keys is not None and yaw!=0:raise ValueError('palm_plane_camera_conflict')
    yaws=at_times(camera_keys,[t/1e6 for t in ticks],ticks[-1]/1e6) if camera_keys is not None else [yaw]*len(ticks)
    for tick,frame,angle in zip(ticks,bvh.frames,yaws):
        pose=_world_matrices(bvh,frame);hands={}
        for side,names in chains.items():
            points=[project(_basis(_origin(pose[lookup[n]]),mapping['basis']),angle) for n in names]
            hands[side]=plane(*points)
        rows.append(dict(time=tick/1e6,hands=hands))
    return dict(profile='mixamo-knuckle-plane-observation-v1',yaw=yaw if camera_keys is None else None,camera_keys=camera_keys,rows=rows,chains=chains,
        authority='none',selected=False,limitations=['knuckle_plane_not_full_hand_surface',
        'normal_sign_not_labeled_palm_or_back','source_pose_not_target_texture_registration'])
