"""Required motion coverage from actual Runtime samples, not clip names alone."""
import math


def motion_rows(job, report, required):
    result=[]
    for animation in required:
        samples=[r for r in (report or {}).get('results',[]) if r.get('animation')==animation]
        valid=bool(samples) and all(type(r.get('index')) is int and r['index']>=0
            and type(r.get('time')) in (int,float) and math.isfinite(r['time']) and r['time']>=0 for r in samples)
        if valid:
            ordered=sorted(samples,key=lambda r:r['index'])
            valid=([r['index'] for r in ordered]==list(range(len(samples))) and len(samples)>1
                   and ordered[0]['time']==0 and all(a['time']<b['time'] for a,b in zip(ordered,ordered[1:])))
        status=('missing' if animation not in job.get('animations',[]) else
                'unmeasured' if not valid else 'passed' if report.get('passed') is True else 'failed')
        result.append(dict(animation=animation,status=status,sampled_frames=len(samples),
                           duration_seconds=max(r['time'] for r in samples) if valid else None))
    return result
