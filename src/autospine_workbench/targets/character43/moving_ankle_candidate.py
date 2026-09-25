"""Bounded root/leg timeline driven by observed ankle motion, not static locks."""
from copy import deepcopy
import math
from .joint_support_solver import solve
from ..spine43.continuous_pose import interpolate


def build(document, name, trajectory, times, reference_length):
    source_times = [r['time'] for r in trajectory]
    if (len(source_times) < 2 or source_times[0] != 0
            or any(not math.isfinite(t) for t in source_times)
            or any(b <= a for a, b in zip(source_times, source_times[1:]))
            or any(len(r['targets']) != 2 or any(len(p) != 2 or any(not math.isfinite(v) for v in p)
                                               for p in r['targets']) for r in trajectory)):
        raise ValueError('moving_ankle_trajectory_invalid')
    tracks = document['animations'][name]['bones']
    if any('curve' in k for row in tracks.values() for keys in row.values() for k in keys):
        raise ValueError('moving_ankle_linear_required')
    knots = sorted(set(times) | set(source_times) |
                   {k.get('time', 0) for row in tracks.values() for keys in row.values() for k in keys})
    if (len(knots) > 2048 or knots[0] != 0 or knots[-1] != source_times[-1]
            or any(not math.isfinite(t) for t in knots)):
        raise ValueError('moving_ankle_timeline_limit')
    candidate = deepcopy(document)
    output = candidate['animations'][name]['bones']
    root_keys = tracks.get('root', {}).get('translate')
    if not root_keys:
        raise ValueError('moving_ankle_root_timeline_missing')
    root_values = [dict(time=k['time'], vertices=[k['x'], k['y']]) for k in root_keys]
    feet = [[dict(time=r['time'], vertices=r['targets'][s]) for r in trajectory] for s in (0, 1)]
    names = ('thigh_l', 'calf_l', 'thigh_r', 'calf_r')
    output['root']['translate'] = []
    for bone in names:
        output.setdefault(bone, {})['rotate'] = []
    previous = None
    rows = []
    report = dict(profile='moving-source-ankle-timeline-v1', selected=False, authority='none',
                  status='blocked', rows=rows, input_samples=len(times), required_knots=len(knots),
                  scope='bounded_timeline_not_mesh_runtime_or_visual_acceptance')
    for t in knots:
        requested = [dict(upper='thigh_'+s, lower='calf_'+s, tip='foot_'+s,
                          target=interpolate(feet[i], t, 'vertices')) for i, s in enumerate(('l', 'r'))]
        result = solve(document, name, t, requested, reference_length, previous=previous,
                       maximum_rotation_speed=180)
        solution = result['solution']
        if solution is None:
            report['failure'] = dict(time=t, **result)
            return None, report
        previous = dict(time=t, **solution)
        base = interpolate(root_values, t, 'vertices')
        output['root']['translate'].append(dict(time=t, x=base[0]+solution['root_shift'][0],
                                                y=base[1]+solution['root_shift'][1]))
        for leg in solution['legs']:
            for part in ('upper', 'lower'):
                bone = leg[part]
                keys = tracks.get(bone, {}).get('rotate')
                angle = interpolate(keys, t, 'value') if keys else 0
                output[bone]['rotate'].append(dict(time=t, value=angle+leg[part+'_delta_degrees']))
        rows.append(previous)
    report.update(status='candidate', maximum_root_shift_px=max(math.hypot(*r['root_shift']) for r in rows),
                  maximum_endpoint_error_px=max(leg['endpoint_error_px'] for r in rows for leg in r['legs']))
    return candidate, report
