"""Causal joint-support candidate with explicit entry and release transitions."""
from copy import deepcopy
import math

from .affine_pose import matrices
from .joint_support_solver import solve
from ..spine43.continuous_pose import interpolate


def build(document, animation, motion, times, reference_length, *, release_seconds=.25,
          preserve_pose=False, maximum_error_px=None):
    if type(preserve_pose) is not bool:
        raise ValueError('joint_support_pose_mode_invalid')
    if maximum_error_px is not None and not preserve_pose:
        raise ValueError('joint_support_residual_requires_pose_mode')
    profile = 'causal-source-axis-support-v1-experiment' if preserve_pose else 'causal-joint-support-timeline-v1'
    if not math.isfinite(release_seconds) or release_seconds <= 0:
        raise ValueError('joint_support_release_invalid')
    rate = motion['ticks_per_second']; duration = motion['duration_ticks']/rate
    contacts = sorted([dict(limb=m['limb'], start=m['start_tick']/rate, end=m['end_tick']/rate)
                       for m in motion['markers'] if m['kind'] == 'contact'], key=lambda c: (c['start'], c['limb']))
    for i, row in enumerate(contacts):
        if row['limb'] not in ('leg.left', 'leg.right') or not 0 <= row['start'] < row['end'] <= duration:
            raise ValueError('joint_support_interval_invalid')
        if any(c['limb'] == row['limb'] and row['start'] < c['end'] for c in contacts[:i]):
            raise ValueError('joint_support_interval_overlap')
    if not contacts: raise ValueError('joint_support_contacts_missing')
    names = ('thigh_l', 'calf_l', 'thigh_r', 'calf_r')
    tracks = document['animations'][animation].get('bones', {})
    if any('curve' in key for bone in tracks.values() for track in bone.values() for key in track):
        raise ValueError('joint_support_linear_required')
    root_keys = tracks.get('root', {}).get('translate', [])
    if not root_keys: raise ValueError('joint_support_root_timeline_missing')
    knots = set(times) | {0., duration} | {duration*i/256 for i in range(257)}
    knots.update(key['time'] for bone in tracks.values() for track in bone.values() for key in track)
    for row in contacts: knots.update((row['start'], row['end'], min(duration, row['end']+release_seconds)))
    if len(knots) > 2048 or any(not math.isfinite(t) or not 0 <= t <= duration for t in knots):
        raise ValueError('joint_support_timeline_limit')
    def base_root(t):
        return interpolate([dict(time=k['time'], vertices=[k['x'], k['y']]) for k in root_keys], t, 'vertices')
    def base_angle(n, t):
        keys = tracks.get(n, {}).get('rotate', [])
        return interpolate(keys, t, 'value') if keys else 0.
    candidate = deepcopy(document)
    output = candidate['animations'][animation].setdefault('bones', {})
    output.setdefault('root', {})['translate'] = []
    for n in names: output.setdefault(n, {})['rotate'] = []
    shift = [0., 0.]; angles = {n: 0. for n in names}
    active = {}; release = {}; root_release = None; previous_time = 0.; rows = []; anchors = []
    for t in sorted(knots):
        for side, entry in list(active.items()):
            if t >= entry['end']:
                release[side] = dict(time=entry['end'], values=[angles['thigh_'+side], angles['calf_'+side]])
                del active[side]
                if not active: root_release = dict(time=entry['end'], values=list(shift))
        def fade(entry):
            u = min(1., max(0., (t-entry['time'])/release_seconds))
            return 1-u*u*(3-2*u)
        for side, entry in release.items():
            for n, value in zip(('thigh_'+side, 'calf_'+side), entry['values']): angles[n] = value*fade(entry)
        if not active and root_release:
            shift = [v*fade(root_release) for v in root_release['values']]
        entering = [c for c in contacts if c['start'] == t]
        if entering:
            current = deepcopy(document); channels = current['animations'][animation]['bones']
            base = base_root(t)
            channels.setdefault('root', {})['translate'] = [dict(time=0, x=base[0]+shift[0], y=base[1]+shift[1])]
            for n in names: channels.setdefault(n, {})['rotate'] = [dict(time=0, value=base_angle(n, t)+angles[n])]
            pose = matrices(current, animation, t)
            for c in entering:
                side = 'l' if c['limb'] == 'leg.left' else 'r'
                point = list(pose['foot_'+side][4:6]); active[side] = dict(c, target=point)
                anchors.append(dict(c, target=point)); release.pop(side, None)
            root_release = None
        if active:
            requested = [dict(upper='thigh_'+s, lower='calf_'+s, tip='foot_'+s, target=c['target'])
                         for s, c in sorted(active.items())]
            previous = None
            if rows:
                previous = dict(time=previous_time, root_shift=rows[-1]['root_shift'], legs=[
                    dict(upper='thigh_'+s, lower='calf_'+s, tip='foot_'+s,
                         upper_delta_degrees=rows[-1]['angles']['thigh_'+s], lower_delta_degrees=rows[-1]['angles']['calf_'+s])
                    for s in ('l', 'r')])
            result = solve(document, animation, t, requested, reference_length,
                           previous=previous, maximum_rotation_speed=180,
                           **(dict(preserve_pose=True, maximum_error_px=maximum_error_px) if preserve_pose else {}))
            if not result['solution']:
                return None, dict(profile=profile, selected=False, authority='none',
                                  status='blocked', failure=dict(time=t, **result), rows=rows, anchors=anchors)
            shift = result['solution']['root_shift']
            for leg in result['solution']['legs']:
                angles[leg['upper']] = leg['upper_delta_degrees']; angles[leg['lower']] = leg['lower_delta_degrees']
        base = base_root(t)
        output['root']['translate'].append(dict(time=t, x=base[0]+shift[0], y=base[1]+shift[1]))
        for n in names: output[n]['rotate'].append(dict(time=t, value=base_angle(n, t)+angles[n]))
        rows.append(dict(time=t, root_shift=list(shift), angles=dict(angles)))
        previous_time = t
    speed = max(math.dist(a['root_shift'], b['root_shift'])/(b['time']-a['time']) for a, b in zip(rows, rows[1:]))
    angular = max(abs(a['angles'][n]-b['angles'][n])/(b['time']-a['time']) for a, b in zip(rows, rows[1:]) for n in names)
    reasons = []
    if speed > 2*reference_length: reasons.append('root_speed')
    if angular > 180: reasons.append('rotation_speed')
    report = dict(profile=profile, selected=False, authority='none',
                  status='blocked' if reasons else 'candidate', reason_codes=reasons, rows=rows, anchors=anchors,
                  root_speed_px_per_second=speed, rotation_speed_degrees_per_second=angular,
                  limits=dict(root_ratio=.15, root_speed_ratio=2, rotation_degrees=30,
                              rotation_speed_degrees_per_second=180, release_seconds=release_seconds),
                  scope='candidate_timeline_not_mesh_or_runtime_validation')
    return (None if reasons else candidate), report
