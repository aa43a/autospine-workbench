"""Measure projected pose intent separately from mesh and contact quality."""
import math
from .affine_pose import matrices
from .oblique_motion import project
from .knee_projection import compare


def chain(source, target, rest_lengths):
    if (len(source)!=2 or len(target)!=2 or len(rest_lengths)!=2
            or any(len(v)!=3 for v in source) or any(len(v)!=2 for v in target)
            or any(not math.isfinite(x) for v in [*source,*target,rest_lengths] for x in v)
            or min(rest_lengths)<=0 or any(math.hypot(*v)<=1e-10 for v in source)):
        raise ValueError('pose_fidelity_chain_invalid')
    expected=[];angles=[];visibility=[]
    for observed,actual,length in zip(source,target,rest_lengths):
        size=math.hypot(*observed);screen=math.hypot(*observed[:2])
        expected.append([observed[i]/size*length for i in (0,1)])
        visibility.append(screen/size)
        angles.append(None if screen<=1e-10 or math.hypot(*actual)<=1e-10 else
            abs((math.degrees(math.atan2(actual[1],actual[0])-math.atan2(observed[1],observed[0]))+180)%360-180))
    predicted=[sum(v[i] for v in expected) for i in (0,1)]
    endpoint=[sum(v[i] for v in target) for i in (0,1)]
    reference=sum(rest_lengths)
    return dict(direction_error_degrees=angles,projection_visibility=visibility,
                expected_endpoint=predicted,target_endpoint=endpoint,
                endpoint_error_ratio=math.dist(predicted,endpoint)/reference,
                source_endpoint_height_ratio=-predicted[1]/reference,
                target_endpoint_height_ratio=-endpoint[1]/reference)


def inspect(document,name,vectors,times,yaw=0):
    if (not times or len(times)>2049 or any(not math.isfinite(t) or t<0 for t in times)
            or any(b<=a for a,b in zip(times,times[1:]))):
        raise ValueError('pose_fidelity_times_invalid')
    roles=[f'humanoid.{limb}.{part}.{side}' for limb in ('arm','leg')
           for side in ('left','right') for part in ('upper','lower')]
    if any(r not in vectors or len(vectors[r])!=len(times) for r in roles):
        raise ValueError('pose_fidelity_source_inventory')
    rest=matrices(dict(document,animations={'setup':{}}),'setup',0)
    rows=[]
    for i,t in enumerate(times):
        world=matrices(document,name,t)
        for limb,names in [('arm',('upperarm','forearm','hand')),('leg',('thigh','calf','foot'))]:
            for side,suffix in [('left','l'),('right','r')]:
                ids=[n+'_'+suffix for n in names]
                lengths=[math.dist(rest[a][4:],rest[b][4:]) for a,b in zip(ids,ids[1:])]
                source=[project(vectors[f'humanoid.{limb}.{part}.{side}'][i],yaw) for part in ('upper','lower')]
                target=[(world[b][4]-world[a][4],world[a][5]-world[b][5]) for a,b in zip(ids,ids[1:])]
                row=dict(time=t,limb=limb,side=side,**chain(source,target,lengths))
                if limb=='leg':row['knee']=compare(*source,*[(*v,0) for v in target])
                rows.append(row)
    return dict(profile='source-pose-fidelity-v1',authority='none',selected=False,yaw=yaw,rows=rows,
                scope='source_frame_joint_origins_not_deformed_mesh_or_visual_acceptance',
                limitations=['normalized_source_segment_lengths_use_target_setup_proportions',
                             'camera_depth_sign_is_not_anatomical_forward',
                             'near_camera_direction_errors_require_visibility_context'])
