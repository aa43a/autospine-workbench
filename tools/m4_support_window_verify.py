"""Independently replay a window's emitted rows through full skeleton FK."""
from copy import deepcopy
import math
from autospine_workbench.targets.character43.support_row_tracks import apply
from autospine_workbench.targets.character43.motion_contacts import analyze, schedule
from autospine_workbench.targets.character43.motion_direction_audit import audit


def verify(fitted, final, motion, pose, contact, report, reference):
    original = contact['phase_attempt']['rows']
    replacement = {r['time']: r for r in report['candidate_rows']}
    if len(replacement)!=len(report['candidate_rows']) or set(replacement)-{r['time'] for r in original}:
        raise ValueError('window_verify_replacement_times_invalid')
    rows = [replacement.get(r['time'], r) for r in original]
    name = 'external-motion'; doc = apply(fitted,name,rows)
    names = ('thigh_l','calf_l','thigh_r','calf_r')
    measured = deepcopy(motion)
    if contact['hypothesis']['ticks_per_second'] != motion['ticks_per_second']:
        raise ValueError('window_verify_tick_rate_mismatch')
    measured['markers'] = deepcopy(contact['hypothesis']['markers'])
    times = schedule(measured, sorted({r['time'] for r in rows}|set(report.get('check_times',[]))))
    if 'verification_time_grid' in report:
        explicit=report['verification_time_grid'];duration=motion['duration_ticks']/motion['ticks_per_second']
        if (not 2<=len(explicit)<=4096 or any(not math.isfinite(t) or not 0<=t<=duration for t in explicit)
                or any(b<=a for a,b in zip(explicit,explicit[1:])) or set(times)-set(explicit)):
            raise ValueError('window_verify_explicit_grid_invalid')
        times=explicit
    old = analyze(final,name,measured,times,reference); new = analyze(doc,name,measured,times,reference)
    root_speed = max(math.dist(a['root_shift'],b['root_shift'])/(b['time']-a['time']) for a,b in zip(rows,rows[1:]))
    speed = max(abs(a['angles'][n]-b['angles'][n])/(b['time']-a['time']) for a,b in zip(rows,rows[1:]) for n in names)
    root_ratio = max(math.hypot(*r['root_shift'])/reference for r in rows)
    angle = max(abs(r['angles'][n]) for r in rows for n in names)
    endpoint={}
    if report.get('endpoint_guard')=='per_sample_per_leg_hip_relative_no_regression':
        from autospine_workbench.targets.character43.affine_pose import matrices
        before=apply(fitted,name,original)
        knots=[r['time'] for r in report['candidate_rows']]
        check=sorted(set(knots)|{(a+b)/2 for a,b in zip(knots,knots[1:])})
        explicit=report.get('endpoint_check_times',check)
        if (not explicit or len(explicit)>4097 or any(not math.isfinite(t) or not knots[0]<=t<=knots[-1] for t in explicit)
                or any(b<=a for a,b in zip(explicit,explicit[1:])) or set(check)-set(explicit)):
            raise ValueError('window_verify_endpoint_time_grid_invalid')
        check=explicit
        regressions=[]
        for t in check:
            poses=[matrices(d,name,t) for d in (fitted,before,doc)]
            for side in ('l','r'):
                vectors=[tuple(p['foot_'+side][4+i]-p['thigh_'+side][4+i] for i in (0,1)) for p in poses]
                limit=max(math.dist(vectors[0],vectors[1]),report['endpoint_floor_px'])
                regressions.append(math.dist(vectors[0],vectors[2])-limit)
        endpoint=dict(endpoint_maximum_regression_px=max(regressions),endpoint_samples=len(check),
                      endpoint_passed=max(regressions)<=1e-9,endpoint_fk_tolerance_px=1e-9)
    return dict(profile='window-full-fk-verification-v1', authority='none', contact_before=old, contact_after=new,
                contact_not_increased=new['max_drift_px'] <= old['max_drift_px'],
                root_speed_ratio=root_speed/reference, rotation_speed_deg=speed,
                speed_passed=root_speed<=2*reference and speed<=180,
                maximum_root_ratio=root_ratio, maximum_rotation_delta_deg=angle,
                support_limits_passed=root_ratio<=.15+1e-9 and angle<=30+1e-9 and root_speed<=2*reference and speed<=180,
                direction=audit(doc,name,pose['vectors'],pose['times']),**endpoint,
                scope='bone_tracks_only_not_corrected_mesh_runtime_or_visual_acceptance')
