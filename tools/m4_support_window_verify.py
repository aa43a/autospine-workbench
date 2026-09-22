"""Independently replay a window's emitted rows through full skeleton FK."""
from copy import deepcopy
import math
from autospine_workbench.targets.spine43.continuous_pose import interpolate
from autospine_workbench.targets.character43.motion_contacts import analyze, schedule
from autospine_workbench.targets.character43.motion_direction_audit import audit


def verify(fitted, final, motion, pose, contact, report, reference):
    original = contact['phase_attempt']['rows']
    replacement = {r['time']: r for r in report['candidate_rows']}
    rows = [replacement.get(r['time'], r) for r in original]
    doc = deepcopy(fitted); name = 'external-motion'
    source = fitted['animations'][name]['bones']; tracks = doc['animations'][name]['bones']
    names = ('thigh_l','calf_l','thigh_r','calf_r')
    root = [dict(time=k['time'],vertices=[k['x'],k['y']]) for k in source['root']['translate']]
    tracks['root']['translate'] = []
    for n in names: tracks[n]['rotate'] = []
    for row in rows:
        t = row['time']; xy = interpolate(root,t,'vertices')
        tracks['root']['translate'].append(dict(time=t,x=xy[0]+row['root_shift'][0],y=xy[1]+row['root_shift'][1]))
        for n in names:
            value = interpolate(source[n]['rotate'],t,'value')+row['angles'][n]
            tracks[n]['rotate'].append(dict(time=t,value=value))
    measured = deepcopy(motion)
    if contact['hypothesis']['ticks_per_second'] != motion['ticks_per_second']:
        raise ValueError('window_verify_tick_rate_mismatch')
    measured['markers'] = deepcopy(contact['hypothesis']['markers'])
    times = schedule(measured, [r['time'] for r in rows])
    old = analyze(final,name,measured,times,reference); new = analyze(doc,name,measured,times,reference)
    root_speed = max(math.dist(a['root_shift'],b['root_shift'])/(b['time']-a['time']) for a,b in zip(rows,rows[1:]))
    speed = max(abs(a['angles'][n]-b['angles'][n])/(b['time']-a['time']) for a,b in zip(rows,rows[1:]) for n in names)
    return dict(profile='window-full-fk-verification-v1', authority='none', contact_before=old, contact_after=new,
                contact_not_increased=new['max_drift_px'] <= old['max_drift_px'],
                root_speed_ratio=root_speed/reference, rotation_speed_deg=speed,
                speed_passed=root_speed<=2*reference and speed<=180,
                direction=audit(doc,name,pose['vectors'],pose['times']),
                scope='bone_tracks_only_not_corrected_mesh_runtime_or_visual_acceptance')
