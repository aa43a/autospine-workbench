"""Compare bounded joint solves against exact prior source-qualified anchors."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.motion2d.phase_support import inspect
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.joint_support_solver import solve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prior', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    parser.add_argument('--rotation-speed', type=float, default=None)
    args = parser.parse_args()
    raw = args.prior.read_bytes(); prior = json.loads(raw)
    files = AnimatedStore(args.state_root).read(prior['input_artifact_sha256'])
    if sha256(files['motion-ir.json']).hexdigest() != prior['input_motion_sha256']:
        raise ValueError('joint_support_motion_mismatch')
    identity = prior['motion_identity']
    bundle = VerifiedMotionBundleReader(args.state_root).load(identity['clip_sha256'], identity['bundle_sha256'])
    contact = json.loads(files['motion-contact.json'])
    support = inspect(parse_bvh(bundle.raw_bvh), bundle.bvh_map, contact['hypothesis'])
    if support != prior['source_support']:
        raise ValueError('joint_support_source_evidence_changed')
    document = json.loads(files['skeleton.json'])
    length = contact['before']['drift_limit_px']*100
    experiment = next(e for e in prior['experiments'] if e['root_enabled'])
    eligible = {(r['limb'], r['start_tick']/1e6, r['end_tick']/1e6) for r in support['records'] if r['eligible']}
    by_time = {}
    for interval in experiment['intervals']:
        if (interval['limb'], interval['start'], interval['end']) not in eligible:
            raise ValueError('joint_support_unqualified_interval')
        side = 'l' if interval['limb'] == 'leg.left' else 'r'
        for sample in interval['samples']:
            by_time.setdefault(sample['time'], []).append(dict(upper='thigh_'+side, lower='calf_'+side,
                                                              tip='foot_'+side, target=interval['anchor']))
    rows = []; previous = None
    for i, (time, contacts) in enumerate(sorted(by_time.items())):
        result = solve(document, 'external-motion', time, contacts, length, previous=previous,
                       maximum_rotation_speed=args.rotation_speed)
        rows.append(dict(time=time, **result))
        if result['solution']:
            previous = dict(time=time, **result['solution'])
        else:
            # Stop: skipping an unsolved frame would hide a continuity break.
            break
        if i % 50 == 0: print('frames', i, flush=True)
    speed = max((math.dist(a['solution']['root_shift'], b['solution']['root_shift'])/(b['time']-a['time'])
                 for a, b in zip(rows, rows[1:]) if a['solution'] and b['solution']), default=0.)
    angular = []
    for a, b in zip(rows, rows[1:]):
        if not a['solution'] or not b['solution']: continue
        previous_legs = {v['upper']: v for v in a['solution']['legs']}
        for leg in b['solution']['legs']:
            if leg['upper'] not in previous_legs: continue
            for key in ('upper_delta_degrees', 'lower_delta_degrees'):
                angular.append(dict(time=b['time'], bone=leg['upper'] if key.startswith('upper') else leg['lower'],
                    degrees_per_second=abs(leg[key]-previous_legs[leg['upper']][key])/(b['time']-a['time'])))
    report = dict(profile='source-qualified-joint-support-diagnostic-v2' if args.rotation_speed is not None else 'source-qualified-joint-support-diagnostic-v1', selected=False, authority='none',
        input_artifact_sha256=prior['input_artifact_sha256'], prior_evidence_sha256=sha256(raw).hexdigest(),
        motion_identity=identity, source_support=support, rows=rows, expected_frames=len(by_time),
        solved_frames=sum(r['solution'] is not None for r in rows), root_speed_px_per_second=speed,
        root_speed_limit_px_per_second=2*length,
        root_speed_passed=speed <= 2*length,
        maximum_rotation_speed=max(angular, key=lambda r: r['degrees_per_second'], default=None),
        rotation_speed_limit=args.rotation_speed,
        scope='contact_sample_endpoints_only_no_release_rotation_speed_mesh_or_runtime_validation')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('expected_frames', 'solved_frames', 'root_speed_px_per_second', 'root_speed_limit_px_per_second')}))


if __name__ == '__main__': main()
