"""Read-only counterfactual diagnosis; never adopts a relaxed timeline."""
import argparse
import json
import math
from copy import deepcopy
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.joint_support_solver import solve
from autospine_workbench.targets.character43.ankle_window_solver import solve_window
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.spine43.continuous_pose import interpolate


def probe(files, window=False):
    report = json.loads(files['motion-moving-ankles.json'])
    document = json.loads(files['skeleton.json'])
    if report['applied'] or 'failure' not in report:
        raise ValueError('requires_unapplied_failed_candidate')
    if canonical_sha256(document) != report['input_skeleton_sha256']:
        raise ValueError('input_skeleton_changed')
    animations = list(document['animations'])
    if len(animations) != 1:
        raise ValueError('requires_unambiguous_animation')
    time = report['failure']['time']
    reference = report['final_check']['limit_px'] / .01
    trajectory = report['trajectory']
    contacts = []
    for i, side in enumerate(('l', 'r')):
        keys = [dict(time=r['time'], vertices=r['targets'][i]) for r in trajectory]
        contacts.append(dict(upper='thigh_'+side, lower='calf_'+side, tip='foot_'+side,
                             target=interpolate(keys, time, 'vertices')))
    previous = report['rows'][-1] if report['rows'] else None
    variants = {}
    for label, prior, speed in (
            ('original_temporal_limits', previous, 180),
            ('root_continuity_only', previous, None),
            ('independent_frame', None, None)):
        variants[label] = solve(document, animations[0], time, contacts, reference,
                                previous=prior, maximum_rotation_speed=speed)
    output = dict(schema='autospine.moving-ankle-failure-probe/v1', time=time,
                input_skeleton_sha256=canonical_sha256(document), targets=contacts,
                variants=variants, authority='none', selected=False,
                scope='single_frame_counterfactual_not_feasibility_proof_or_timeline_acceptance')
    if window:
        times = [r['time'] for r in report['rows']] + [time]
        feet = [[dict(time=r['time'], vertices=r['targets'][i]) for r in trajectory] for i in (0, 1)]
        result = solve_window(document, animations[0], times,
                             [[interpolate(k, t, 'vertices') for k in feet] for t in times], reference)
        output['window'] = result
        if result['solution'] is not None:
            changed = deepcopy(document)
            tracks = document['animations'][animations[0]]['bones']
            target = changed['animations'][animations[0]]['bones']
            roots = [dict(time=k['time'], vertices=[k['x'], k['y']]) for k in tracks['root']['translate']]
            target['root']['translate'] = []
            names = ('thigh_l', 'calf_l', 'thigh_r', 'calf_r')
            for bone in names:
                target.setdefault(bone, {})['rotate'] = []
            for t, v in zip(times, result['solution']):
                base = interpolate(roots, t, 'vertices')
                target['root']['translate'].append(dict(time=t, x=base[0]+v[0]*reference, y=base[1]+v[1]*reference))
                for i, bone in enumerate(names):
                    keys = tracks.get(bone, {}).get('rotate')
                    angle = interpolate(keys, t, 'value') if keys else 0
                    target[bone]['rotate'].append(dict(time=t, value=angle+math.degrees(v[i+2])))
            samples = sorted(set(times) | {(a+b)/2 for a, b in zip(times, times[1:])})
            errors = [dict(time=t, side=s, error_px=math.dist(
                matrices(changed, animations[0], t)['foot_'+s][4:6], interpolate(feet[i], t, 'vertices')))
                for t in samples for i, s in enumerate(('l', 'r'))]
            result['independent_fk_check'] = dict(samples=len(samples), limit_px=reference*.01,
                worst=max(errors, key=lambda r: r['error_px']), passed=all(r['error_px'] <= reference*.01 for r in errors))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact')
    parser.add_argument('output', type=Path)
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    parser.add_argument('--window', action='store_true')
    args = parser.parse_args()
    result = probe(AnimatedStore(args.state_root).read(args.artifact), args.window)
    result['artifact_sha256'] = args.artifact
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: dict(status=v['status'], errors=v['best_errors_px'],
                             failed=v['failed_checks']) for k, v in result['variants'].items()}))
    if args.window:
        print(json.dumps({k: v for k, v in result['window'].items() if k not in ('solution', 'trials')}))
