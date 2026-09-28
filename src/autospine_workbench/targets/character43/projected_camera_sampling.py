"""Next-version grid foundation: refine visible direction, not just camera yaw.

Not yet selected by public tasks. Degenerate directions fail rather than invent
a limb orientation; interpolated samples remain observations, not new artwork.
"""
import math
from .camera_sampling import schedule,interpolate,MAX_SAMPLES,TICKS
from .camera_track import sample
from .oblique_motion import project

PROFILE='camera-world-projected-adaptive-v2'
MAX_DIRECTION=12.0
MAX_MIDPOINT_ERROR=2.0


def refine(times,vectors,keys,duration,reference):
    if not vectors or not math.isfinite(reference) or reference<=0:
        raise ValueError('camera_refinement_input_invalid')
    initial=schedule(times,keys,duration)
    ticks={round(t*TICKS) for t in initial};cache={}
    def angles(tick):
        if tick not in cache:
            t=tick/TICKS;result=[]
            for role,values in sorted(vectors.items()):
                v=interpolate(values,times,[t])[0];x,y,z=project(v,sample(keys,t))
                length=math.sqrt(x*x+y*y+z*z)
                if math.hypot(x,y)<=max(1e-12,length*1e-6,reference*1e-9):
                    raise ValueError('camera_refinement_direction_unobservable:'+role)
                result.append(math.degrees(math.atan2(y,x)))
            cache[tick]=result
        return cache[tick]
    delta=lambda a,b:(b-a+180)%360-180
    pending=list(zip(sorted(ticks),sorted(ticks)[1:]))
    while pending:
        a,b=pending.pop();m=(a+b)//2
        first,last=angles(a),angles(b)
        middle=angles(m) if a<m<b else first
        needs=any(abs(delta(x,y))>MAX_DIRECTION or
            (a<m<b and (abs(delta(x,z))>MAX_DIRECTION or abs(delta(z,y))>MAX_DIRECTION or
             abs(delta(x,z)-delta(x,y)*((m-a)/(b-a)))>MAX_MIDPOINT_ERROR))
            for x,y,z in zip(first,last,middle))
        if not needs:continue
        if not a<m<b:raise ValueError('camera_refinement_tick_resolution_exceeded')
        if len(ticks)>=MAX_SAMPLES:raise ValueError('camera_sampling_budget_exceeded')
        ticks.add(m);pending.extend(((a,m),(m,b)))
    return [t/TICKS for t in sorted(ticks)]
