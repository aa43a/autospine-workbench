"""Rebase foot linear channels after parent IK; retain corrected ankle positions."""
from copy import deepcopy
import math
from ...resolved_project import canonical_sha256
from .affine_pose import matrices
from .pose_geometry_patch import _times


def preserve(candidate, reference, animation, times):
    if candidate['bones']!=reference['bones']:
        raise ValueError('foot_frame_bind_changed')
    if (len(times)<2 or times[0]!=0 or any(not math.isfinite(t) for t in times)
            or any(b<=a for a,b in zip(times,times[1:]))):
        raise ValueError('foot_frame_times_invalid')
    feet=('foot_l','foot_r');bones={b['name']:b for b in candidate['bones']}
    if any(bones[n].get('parent')!='calf_'+n[-1] for n in feet):
        raise ValueError('foot_frame_topology')
    grid=set(times)
    for doc in (candidate,reference):
        grid.update(t for t in _times(doc['animations'][animation].get('bones',{})) if 0<=t<=times[-1])
    desired={};parents={}
    def targets(t):
        if t not in desired:desired[t]=matrices(reference,animation,t)
        return desired[t]
    def parent_at(t):
        if t not in parents:parents[t]=matrices(candidate,animation,t)
        return parents[t]
    for iteration in range(9):
        if len(grid)>4097:raise ValueError('foot_frame_budget_exceeded')
        ordered=sorted(grid);result=deepcopy(candidate)
        output=result['animations'][animation].setdefault('bones',{})
        for name in feet:
            bone=bones[name];track=output.setdefault(name,{})
            for channel in ('rotate','scale','shear'):track[channel]=[]
            for t in ordered:
                a,b,c,d,_,_=parent_at(t)[bone['parent']];det=a*d-b*c
                if det<=1e-10:raise ValueError('foot_frame_parent_singular')
                u,v,w,z=targets(t)[name][:4]
                local=((d*u-b*w)/det,(d*v-b*z)/det,(-c*u+a*w)/det,(-c*v+a*z)/det)
                x=math.degrees(math.atan2(local[2],local[0]));y=math.degrees(math.atan2(local[3],local[1]))
                rotation=x-bone['rotation']
                if track['rotate']:
                    previous=track['rotate'][-1]['value'];rotation=previous+(rotation-previous+180)%360-180
                track['rotate'].append(dict(time=t,value=rotation))
                track['scale'].append(dict(time=t,x=math.hypot(local[0],local[2])/bone.get('scaleX',1),
                    y=math.hypot(local[1],local[3])/bone.get('scaleY',1)))
                track['shear'].append(dict(time=t,x=0.,y=(y-x-90+180)%360-180))
        checked=sorted(grid | {a+(b-a)*f for a,b in zip(ordered,ordered[1:]) for f in (.25,.5,.75)})
        failures=set();maximum=position_error=0.
        for t in checked:
            actual=matrices(result,animation,t);expected=targets(t);before=parent_at(t)
            for name in feet:
                scale=max(abs(v) for v in expected[name][:4])
                error=max(abs(a-b) for a,b in zip(actual[name][:4],expected[name][:4]))/scale
                maximum=max(maximum,error)
                position_error=max(position_error,math.dist(actual[name][4:],before[name][4:]))
                if error>1e-3:failures.add(t)
        if not failures:
            return result,dict(profile='foot-world-frame-preservation-v1',authority='none',selected=False,
                reference_sha256=canonical_sha256(reference),input_sha256=canonical_sha256(candidate),
                output_sha256=canonical_sha256(result),key_count=len(ordered),checked_samples=len(checked),
                maximum_relative_matrix_error=maximum,maximum_ankle_position_change_px=position_error,
                refinement_passes=iteration,scope='sampled_reference_frame_preservation_not_sole_lock_or_visual_acceptance')
        grid.update(failures)
    raise ValueError('foot_frame_budget_exceeded')
