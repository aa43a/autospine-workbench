"""Fit end-effector world orientation while cancelling inherited affine distortion."""
from copy import deepcopy
import math
from .affine_pose import matrices
from ...resolved_project import canonical_sha256


def fit(document,name,observations):
    result=deepcopy(document);setup=deepcopy(document);setup['animations'][name]={'bones':{}}
    rest=matrices(setup,name,0);bones={b['name']:b for b in document['bones']}
    times=observations['times'];selected=observations['tracks']
    if (len(times)<2 or times[0]!=0 or any(not math.isfinite(t) for t in times)
            or any(b<=a for a,b in zip(times,times[1:])) or set(selected)!={'foot_l','foot_r'}):
        raise ValueError('foot_fit_observations_invalid')
    output=result['animations'][name].setdefault('bones',{});max_error=0.
    for n,angles in selected.items():
        if len(angles)!=len(times) or not all(math.isfinite(v) for v in angles):raise ValueError('foot_fit_angles_invalid')
        if n not in bones or bones[n].get('parent')!='calf_'+n[-1]:raise ValueError('foot_fit_topology')
        track=output.setdefault(n,{})
        if any(track.get(k) for k in ('rotate','scale','shear')):raise ValueError('foot_fit_existing_channels')
        for k in ('rotate','scale','shear'):track[k]=[]
        for t,delta in zip(times,angles):
            parent=matrices(result,name,t)[bones[n]['parent']];a,b,c,d=parent[:4];det=a*d-b*c
            if det<=1e-10:raise ValueError('foot_fit_parent_singular')
            co,si=math.cos(math.radians(delta)),math.sin(math.radians(delta));r=rest[n]
            wanted=(co*r[0]-si*r[2],co*r[1]-si*r[3],si*r[0]+co*r[2],si*r[1]+co*r[3])
            u,v,w,z=wanted;local=((d*u-b*w)/det,(d*v-b*z)/det,(-c*u+a*w)/det,(-c*v+a*z)/det)
            x=math.degrees(math.atan2(local[2],local[0]));y=math.degrees(math.atan2(local[3],local[1]))
            value=x-bones[n]['rotation']
            if track['rotate']:value=track['rotate'][-1]['value']+(value-track['rotate'][-1]['value']+180)%360-180
            track['rotate'].append(dict(time=t,value=value))
            track['scale'].append(dict(time=t,x=math.hypot(local[0],local[2])/bones[n].get('scaleX',1),
                                       y=math.hypot(local[1],local[3])/bones[n].get('scaleY',1)))
            track['shear'].append(dict(time=t,x=0.,y=(y-x-90+180)%360-180))
            actual=matrices(result,name,t)[n]
            max_error=max(max_error,*(abs(k-l) for k,l in zip(actual[:4],wanted)))
    return result,dict(profile='source-foot-world-frame-fit-v1',authority='none',selected=False,
        input_sha256=canonical_sha256(dict(document=document,observations=observations)),
        output_sha256=canonical_sha256(result),maximum_matrix_error=max_error,
        limitations=['sampled_world_frame_fit_not_sole_contact','interpolation_mesh_and_runtime_require_recheck'])
