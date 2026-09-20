"""Small distal translations after shared root correction; candidate only."""
from copy import deepcopy
import math

from .affine_pose import matrices
from .contact_root_candidate import build as root_candidate
from .motion_contacts import analyze, schedule
from ..spine43.continuous_pose import interpolate

PROFILE = 'bilateral-stationary-ankle-translation-v1'


def _translation(tracks, bone, time):
    keys = tracks.get(bone, {}).get('translate')
    return interpolate([dict(time=k['time'], vertices=[k['x'], k['y']]) for k in keys], time, 'vertices') if keys else (0., 0.)


def build(document, name, motion, times, reference_length):
    duration = motion['duration_ticks']/motion['ticks_per_second']
    contacts = [m for m in motion['markers'] if m['kind'] == 'contact']
    if (len(contacts) != 2 or {m['limb'] for m in contacts} != {'leg.left', 'leg.right'}
            or any(m['start_tick'] != 0 or m['end_tick'] != motion['duration_ticks'] for m in contacts)):
        raise ValueError('stationary_ankle_full_bilateral_interval_required')
    if any(any('curve' in k for k in keys) for row in document['animations'][name]['bones'].values() for keys in row.values()):
        raise ValueError('stationary_ankle_linear_timeline_required')
    intervals = [dict(limb=m['limb'], start=0., end=duration) for m in contacts]
    candidate, root = root_candidate(document, name, intervals, reference_length=reference_length,
        max_residual_px=.02*reference_length, samples=257)
    report = dict(profile=PROFILE, authority='none', selected=False, status='blocked', root=root,
                  limits=dict(root_ratio=.15, endpoint_ratio=.02, speed_ratio=2., drift_ratio=.01))
    if candidate is None:
        return None, report
    knots = sorted(set(times) | {r['time'] for r in root['rows']})
    anchors = matrices(document, name, 0)
    tracks = candidate['animations'][name]['bones']
    original_tracks = deepcopy(tracks)
    bones = {b['name']: b for b in document['bones']}
    output = {name: [] for name in ('foot_l', 'foot_r')}
    corrections = {name: [] for name in output}
    for t in knots:
        pose = matrices(candidate, name, t)
        for foot in output:
            parent = bones[foot]['parent']
            a, b, c, d = pose[parent][:4]
            determinant = a*d-b*c
            if abs(determinant) < 1e-10:
                raise ValueError('stationary_ankle_singular_parent')
            dx, dy = [anchors[foot][i]-pose[foot][i] for i in (4, 5)]
            local = ((d*dx-b*dy)/determinant, (-c*dx+a*dy)/determinant)
            base = _translation(original_tracks, foot, t)
            output[foot].append(dict(time=t, x=base[0]+local[0], y=base[1]+local[1]))
            corrections[foot].append(dict(time=t, world=[dx, dy]))
    for foot, keys in output.items():
        tracks.setdefault(foot, {})['translate'] = keys
    peak = max(math.hypot(*r['world']) for rows in corrections.values() for r in rows)
    speed = max((math.dist(a['world'], b['world'])/(b['time']-a['time'])
                 for rows in corrections.values() for a, b in zip(rows, rows[1:])), default=0.)
    root_speed = max((math.dist(a['correction'], b['correction'])/(b['time']-a['time'])
                     for a, b in zip(root['rows'], root['rows'][1:])), default=0.)
    checked = analyze(candidate, name, motion, schedule(motion, knots), reference_length)
    passed = checked['passed'] and peak <= .02*reference_length and max(speed, root_speed) <= 2*reference_length
    report.update(status='candidate' if passed else 'blocked', after=checked, endpoint_corrections=corrections,
                  max_endpoint_shift_px=peak, max_endpoint_speed=speed, max_root_speed=root_speed)
    return (candidate if passed else None), report
