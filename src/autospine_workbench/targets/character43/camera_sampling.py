"""Versioned camera sampling; interpolate world observations before projection.

Original source samples remain exact. Added samples are interpolation, not new
measurements or reconstructed artwork. Legacy jobs do not opt in implicitly.
"""
from bisect import bisect_right
from copy import deepcopy
import math
from .camera_track import validate, sample

PROFILE='camera-world-linear-adaptive-v1'
MAX_SAMPLES=4096
MAX_TRAVEL=14.0  # margin below the downstream 15-degree guard after tick rounding
TICKS=1_000_000


def schedule(times,keys,duration):
    keys=validate(keys,duration)
    if (not isinstance(times,(list,tuple)) or not 2<=len(times)<=MAX_SAMPLES
            or times[0]!=0 or times[-1]!=duration
            or any(type(t) not in (int,float) or not math.isfinite(t) for t in times)
            or any(b<=a for a,b in zip(times,times[1:]))):
        raise ValueError('camera_sampling_source_times_invalid')
    tick=lambda t:math.floor(t*TICKS+.5)
    native=[tick(t) for t in times]
    if any(abs(t-n/TICKS)>1e-10 for t,n in zip(times,native)):
        raise ValueError('camera_sampling_source_time_precision')
    knots=sorted(set(native+[tick(k['time']) for k in keys]))
    ticks=set(knots)
    for a,b in zip(knots,knots[1:]):
        first,last=a/TICKS,b/TICKS
        split=[first]+[k['time'] for k in keys if first<k['time']<last]+[last]
        travel=sum(abs(sample(keys,y)-sample(keys,x)) for x,y in zip(split,split[1:]))
        parts=max(1,math.ceil(travel/MAX_TRAVEL))
        if parts>b-a:raise ValueError('camera_sampling_tick_resolution_exceeded')
        if len(ticks)+parts-1>MAX_SAMPLES:raise ValueError('camera_sampling_budget_exceeded')
        for i in range(1,parts):ticks.add(a+math.floor((b-a)*i/parts+.5))
    values=[n/TICKS for n in sorted(ticks)]
    return values


def interpolate(values,times,wanted):
    if len(values)!=len(times):raise ValueError('camera_sampling_observation_count')
    def mix(a,b,f):
        if isinstance(a,(list,tuple)) and isinstance(b,(list,tuple)) and len(a)==len(b):
            return [mix(x,y,f) for x,y in zip(a,b)]
        if type(a) not in (int,float) or type(b) not in (int,float) or not math.isfinite(a) or not math.isfinite(b):
            raise ValueError('camera_sampling_observation_invalid')
        return a+(b-a)*f
    result=[]
    for t in wanted:
        if t<times[0] or t>times[-1]:raise ValueError('camera_sampling_extrapolation_forbidden')
        i=min(len(times)-2,max(0,bisect_right(times,t)-1))
        if t==times[i]:result.append(deepcopy(values[i]))
        elif t==times[i+1]:result.append(deepcopy(values[i+1]))
        else:result.append(mix(values[i],values[i+1],(t-times[i])/(times[i+1]-times[i])))
    return result


def motion_grid(motion,times,wanted):
    if motion['ticks_per_second']!=TICKS:raise ValueError('camera_sampling_tick_rate_unsupported')
    result=deepcopy(motion)
    for track in result['tracks']:
        if [k['tick']/TICKS for k in track['keys']]!=list(times) or track['interpolation']!='linear':
            raise ValueError('camera_sampling_motion_grid_mismatch')
        values=interpolate([k['value'] for k in track['keys']],times,wanted)
        track['keys']=[dict(tick=math.floor(t*TICKS+.5),value=v) for t,v in zip(wanted,values)]
    return result
