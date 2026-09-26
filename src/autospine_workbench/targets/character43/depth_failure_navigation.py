"""Navigate recorded depth evidence at its measured time, without reclassifying QA."""
from hashlib import sha256
import json
import math

from .depth_failure_records import collect

PROFILE='external-motion-depth-navigation-v1'
MAX_LOCATIONS=100_000


def _time(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value<0:
        raise ValueError('depth_navigation_time_invalid')
    return value


def _pair(value):
    if not isinstance(value,list) or (value and (len(value)!=2 or
            any(not isinstance(v,str) or not v for v in value))):
        raise ValueError('depth_navigation_pair_invalid')
    return tuple(value)


def locations(failure):
    """Keep interval anchors distinct from actual overlap/missing-check samples."""
    anchor=_time(failure.get('time'));pair=list(_pair(failure.get('pair',[])))
    result=[]
    def add(time,names,kind):
        row=dict(time=_time(time),pair=list(_pair(names)),time_source=kind,order_time=anchor)
        if row not in result:result.append(row)
    if 'sample_time' in failure:
        add(failure['sample_time'],pair,'requested_sample')
    overlap=failure.get('overlap')
    if overlap is not None:
        add(overlap.get('time'),pair,'overlap_sample')
    budget=failure.get('raster_budget')
    if budget is not None:
        add(budget.get('time'),budget.get('pair',pair),'unmeasured_sample')
    for sample in failure.get('samples',[]):
        add(sample.get('overlap',{}).get('time'),pair,'overlap_sample')
    for edge in (failure.get('conflict') or {}).get('edges',[]):
        names=[edge['back'],edge['front']]
        if edge.get('overlap') is not None:
            add(edge['overlap'].get('time'),names,'constraint_sample')
        for overlap in edge.get('interval_overlaps',[]):
            add(overlap.get('time'),names,'constraint_sample')
    if not result:add(anchor,pair,'record_time')
    return result


def build(files,artifact):
    raw=files.get('motion-depth.json')
    if raw is None:raise ValueError('depth_navigation_evidence_missing')
    depth=json.loads(raw);skeleton=sha256(files['skeleton.json']).hexdigest()
    if depth.get('skeleton_sha256')!=skeleton:raise ValueError('depth_navigation_identity')
    failures=collect(depth);groups={};location_count=0
    for index,failure in enumerate(failures):
        reason=failure.get('reason_code','unknown')
        if not isinstance(reason,str):raise ValueError('depth_navigation_reason_invalid')
        for point in locations(failure):
            location_count+=1
            if location_count>MAX_LOCATIONS:raise ValueError('depth_navigation_resource_limit')
            key=(tuple(point['pair']),reason,point['time_source'])
            group=groups.setdefault(key,dict(pair=point['pair'],reason=reason,
                time_source=point['time_source'],samples={},record_ids=set()))
            group['record_ids'].add(index)
            group['samples'].setdefault(point['time'],set()).add(point['order_time'])
    rows=[]
    for group in groups.values():
        rows.append(dict(pair=group['pair'],reason=group['reason'],time_source=group['time_source'],
            record_count=len(group['record_ids']),samples=[dict(time=time,order_times=sorted(anchors))
                for time,anchors in sorted(group['samples'].items())]))
    return dict(profile=PROFILE,artifact_sha256=artifact,skeleton_sha256=skeleton,
        source_report_sha256=sha256(raw).hexdigest(),groups=rows,
        original_order_records=len(depth.get('order',{}).get('failures',[])),
        diagnostic_records=len(failures),location_count=location_count,
        navigable_samples=sum(len(row['samples']) for row in rows),
        order_changed=False,authority='none',production_authorized=False,
        scope='recorded_diagnostics_not_visual_errors_or_continuous_time_validation')
