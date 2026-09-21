"""Declared BVH foot frames, reduced to relative camera-plane rotation."""
import json
import math
from ...bvh_parser import parse_bvh
from ...bvh_fk import _world_matrices,bvh_frame_ticks


def extract(bundle):
    if bundle.source_kind!='bvh':raise ValueError('foot_orientation_source_not_supported')
    mapping=json.loads((bundle.path/'map.json').read_bytes())
    roles={r['role']:r for r in mapping['bones']};names={}
    for side,suffix in [('left','l'),('right','r')]:
        aim=roles['humanoid.leg.lower.'+side]['aim']
        if aim['kind']!='joint':raise ValueError('foot_orientation_joint_required')
        names['foot_'+suffix]=aim['joint_name']
    bvh=parse_bvh(bundle.raw_bvh);lookup={j.name:i for i,j in enumerate(bvh.joints)}
    poses=[_world_matrices(bvh,f) for f in bvh.frames]
    basis=mapping['basis'];axes=[]
    for key in ('screen_x','screen_y','depth'):
        value=basis[key];axes.append(('XYZ'.index(value[1]),(-1 if value[0]=='-' else 1)*(-1 if key=='screen_y' else 1)))
    tracks={};records=[]
    for target,source in names.items():
        initial=poses[0][lookup[source]];angles=[];max3d=0.;strengths=[]
        for frame in poses:
            m=frame[lookup[source]]
            relative=[[sum(m[i][k]*initial[j][k] for k in range(3)) for j in range(3)] for i in range(3)]
            camera=[[si*sj*relative[i][j] for j,sj in axes] for i,si in axes]
            x=camera[0][0]+camera[1][1];y=camera[1][0]-camera[0][1]
            strength=math.hypot(x,y)/2
            if strength<.2:raise ValueError('foot_orientation_plane_unobservable')
            value=math.degrees(math.atan2(y,x))
            angles.append(value if not angles else angles[-1]+(value-angles[-1]+180)%360-180)
            max3d=max(max3d,math.degrees(math.acos(max(-1,min(1,(sum(relative[i][i] for i in range(3))-1)/2)))))
            strengths.append(strength)
        tracks[target]=angles
        records.append(dict(bone=target,source_joint=source,maximum_3d_rotation_deg=max3d,
                            minimum_planar_strength=min(strengths)))
    return dict(profile='declared-bvh-relative-foot-frame-v1',times=[t/1e6 for t in bvh_frame_ticks(bvh)],
                tracks=tracks,records=records,authority='none',
                limitation='camera_plane_rotation_not_sole_geometry_or_hidden_foot_artwork')
