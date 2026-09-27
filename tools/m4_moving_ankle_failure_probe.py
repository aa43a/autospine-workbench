"""Read-only counterfactual diagnosis; never adopts a relaxed timeline."""
import argparse
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.joint_support_solver import solve
from autospine_workbench.targets.spine43.continuous_pose import interpolate


def probe(files):
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
    return dict(schema='autospine.moving-ankle-failure-probe/v1', time=time,
                input_skeleton_sha256=canonical_sha256(document), targets=contacts,
                variants=variants, authority='none', selected=False,
                scope='single_frame_counterfactual_not_feasibility_proof_or_timeline_acceptance')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact')
    parser.add_argument('output', type=Path)
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    args = parser.parse_args()
    result = probe(AnimatedStore(args.state_root).read(args.artifact))
    result['artifact_sha256'] = args.artifact
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: dict(status=v['status'], errors=v['best_errors_px'],
                             failed=v['failed_checks']) for k, v in result['variants'].items()}))
