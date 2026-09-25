"""Bounded, identity-checked interpolation feedback for shoulder experiments."""
from bisect import bisect_right
from hashlib import sha256
import json
import math
from autospine_workbench.targets.character43.runtime_storage_reference import f32


def solve_times(report):
    """Recover cumulative correction knots, including older report formats."""
    times=report.get('solve_times')
    if times is None:
        times=sorted({f32(t) for t in report['source_times']}|
                     {f32(t) for t in (report.get('feedback') or {}).get('extra_times',[])})
    if (len(times)<2 or len(times)>512 or
            any(not math.isfinite(t) for t in times) or
            any(b<=a for a,b in zip(times,times[1:]))):
        raise ValueError('shoulder_feedback_solve_grid_invalid')
    return times


def validation_grid(reference_times,source_times,times,previous=()):
    # Densify correction/reference intervals, not the already dense prior grid.
    base=sorted(set(reference_times)|set(source_times)|set(times))
    result=sorted(set(previous)|set(base)|{(a+b)/2 for a,b in zip(base,base[1:])})
    if len(result)>16385:raise ValueError('material_shoulder_validation_sample_bound')
    return result


def select(report,source,motion_source,owners,source_times):
    if (report['source_candidate']!=source or report['motion_source_candidate']!=motion_source
            or report['material_owners']!=owners or report['source_times']!=source_times
            or report['solver_failures']):
        raise ValueError('shoulder_feedback_identity_or_solver_failure')
    validation=report['validation'];ratio=validation['max_region_ratio']
    if validation.get('contact_frame')!='verified_material_affine' or validation.get('material_owners')!=owners:
        raise ValueError('shoulder_feedback_material_frame_mismatch')
    if not math.isfinite(ratio) or ratio<0:raise ValueError('shoulder_feedback_region_ratio')
    margin=max(1e-5,report.get('region_margin',1e-5)+2*max(0,ratio-1))
    if margin>.05:raise ValueError('shoulder_feedback_region_margin_bound')
    selected={};knots=solve_times(report)
    for row in validation['failures']:
        time=row['time'];g=row['geometry']
        if row['slot'] not in owners or any(not math.isfinite(g[k]) for k in ('min_area_ratio','max_area_ratio','max_edge_stretch')):
            raise ValueError('shoulder_feedback_geometry_invalid')
        if not math.isfinite(time) or not source_times[0]<=time<=f32(source_times[-1]):
            raise ValueError('shoulder_feedback_time_outside_source')
        severity=max(.5-g['min_area_ratio'],g['max_area_ratio']-2,g['max_edge_stretch']-2,0)
        if severity<=0:continue
        key=(row['slot'],min(len(knots)-2,max(0,bisect_right(knots,time)-1)))
        if key not in selected or severity>selected[key][0]:selected[key]=(severity,time)
    extra=sorted({time for _,time in selected.values()})
    if len(extra)>128:raise ValueError('shoulder_feedback_extra_sample_bound')
    return extra,margin


def load(folder,source,motion_source,owners,source_times,reference_times):
    raw=(folder/'report.json').read_bytes();report=json.loads(raw)
    if sha256((folder/'skeleton.json').read_bytes()).hexdigest()!=report['skeleton_sha256']:
        raise ValueError('shoulder_feedback_skeleton_mismatch')
    extra,margin=select(report,source,motion_source,owners,source_times)
    previous=report.get('validation_times')
    if previous is None:
        # Exact construction of the first experiment's declared validation grid.
        base=sorted(set(reference_times)|set(source_times)|{f32(t) for t in source_times})
        previous=sorted(set(base)|{(a+b)/2 for a,b in zip(base,base[1:])})
    if (len(previous)!=report['validation']['frames'] or not previous
            or any(not math.isfinite(t) or not 0<=t<=f32(source_times[-1]) for t in previous)
            or any(b<=a for a,b in zip(previous,previous[1:]))):
        raise ValueError('shoulder_feedback_validation_grid_mismatch')
    return dict(report_sha256=sha256(raw).hexdigest(),skeleton_sha256=report['skeleton_sha256'],
                extra_times=extra,region_margin=margin,previous_validation_times=previous,
                previous_solve_times=solve_times(report))
