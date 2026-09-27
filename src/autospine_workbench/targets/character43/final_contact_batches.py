"""Bounded final-contact checks with exact union and contact-start anchors."""
from copy import deepcopy
import math
from ...resolved_project import canonical_sha256
from .final_motion_contact import recheck


def inspect(document,name,motion,contact,times,reference_length,*,batch_size=1024):
    duration=motion['duration_ticks']/motion['ticks_per_second']
    if (type(batch_size) is not int or not 1<=batch_size<=4095 or not 2<=len(times)<=65536 or
            times[0]!=0 or not math.isclose(times[-1],duration,abs_tol=1e-6,rel_tol=0) or
            any(not math.isfinite(t) or t<0 or t>duration+1e-6 for t in times) or
            any(a>=b for a,b in zip(times,times[1:]))):
        raise ValueError('final_contact_batch_times')
    intervals=None;batches=[];covered=[];template=None
    for offset in range(0,len(times),batch_size):
        original=times[offset:offset+batch_size]
        selected=sorted(set(original)|{times[0],times[-1]})
        report=recheck(document,name,motion,contact,selected,reference_length)
        rows=report['after']['intervals'];template=report
        if intervals is None:
            intervals=[dict(r,samples=[]) for r in deepcopy(rows)]
        if [(r['limb'],r['start'],r['end'],r['bone'],r['anchor']) for r in rows]!=[
                (r['limb'],r['start'],r['end'],r['bone'],r['anchor']) for r in intervals]:
            raise ValueError('final_contact_batch_interval_identity')
        for aggregate,row in zip(intervals,rows):
            aggregate['samples'].extend(s for s in row['samples'] if s['time'] in original)
        batches.append(dict(samples=len(selected),times_sha256=canonical_sha256(selected),
                            passed=report['after']['passed']))
        covered.extend(original)
    if covered!=times:raise ValueError('final_contact_batch_coverage')
    limit=template['after']['drift_limit_px']
    for row in intervals:
        if not row['samples']:continue
        worst=max(row['samples'],key=lambda s:s['drift_px'])
        row.update(max_drift_px=worst['drift_px'],worst_time=worst['time'],passed=worst['drift_px']<=limit)
        row.pop('reason_code',None)
    failed=any(r['passed'] is False for r in intervals);missing=any(r['passed'] is None for r in intervals)
    result=dict(status='unavailable_no_labels' if not intervals else 'needs_changes' if failed else
        'insufficient_contact_samples' if missing else 'ankle_proxy_passed',
        passed=False if failed else None if missing or not intervals else True,intervals=intervals,
        max_drift_px=max((r['max_drift_px'] for r in intervals if r['max_drift_px'] is not None),default=None),
        drift_limit_px=limit,samples=len(times))
    return dict(profile='final-contact-exact-batches-v1',after=result,batches=batches,
        skeleton_sha256=canonical_sha256(document),times_sha256=canonical_sha256(times),
        exact_time_coverage=True,authority='none',selected=False,production_authorized=False,
        scope='final_cpu_ankle_proxy_not_mesh_seam_sole_floor_or_depth')
