"""Bounded leg-only feasibility against moving source ankles; never publishes a rig."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.affine_leg_ik import solve
from autospine_workbench.targets.character43.source_ankle_targets import extract, targets
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.spine43.continuous_pose import interpolate


def run(folder, state, output, *, timeline=False):
    receipt = json.loads((folder/'report.json').read_bytes())
    digest = receipt['candidate_bundle_sha256']
    files = AnimatedStore(folder/'isolated-store').read(digest)
    provenance = json.loads(files['motion-torso-reference.json'])
    identity = provenance['source_identity']
    if identity != receipt['source_identity']:
        raise ValueError('source_ankle_receipt_mismatch')
    bundle = VerifiedMotionBundleReader(state).load(identity['clip_sha256'], identity['bundle_sha256'])
    document = json.loads(files['skeleton.json'])
    initial = matrices(document, 'external-motion', 0)
    bones = {b['name']:b for b in document['bones']}
    length = sum(math.hypot(bones[n]['x'],bones[n]['y'])
                 for n in ('calf_l','foot_l','calf_r','foot_r'))/2
    observation = extract(bundle, provenance['yaw_degrees'])
    trajectory = targets(observation, [initial['foot_'+s][4:6] for s in ('l','r')], length)
    runtime = json.loads((folder/'runtime/report.json').read_bytes())
    if runtime['bundle_sha256'] != digest:
        raise ValueError('source_ankle_runtime_mismatch')
    reference = read(files)
    if (reference['skeleton_sha256'] != sha256(files['skeleton.json']).hexdigest()
            or set(reference['animations']) != {'external-motion'}
            or [r['time'] for r in reference['animations']['external-motion']] !=
               [r['time'] for r in runtime['results']]):
        raise ValueError('source_ankle_reference_mismatch')
    if timeline:
        from autospine_workbench.targets.character43.moving_ankle_candidate import build
        if any(r['animation'] != 'external-motion' for r in runtime['results']):
            raise ValueError('source_ankle_animation_mismatch')
        candidate, report = build(document, 'external-motion', trajectory,
                                  [r['time'] for r in runtime['results']], length)
        report.update(artifact_sha256=digest, source_observation=observation)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf8') as stream: json.dump(report, stream)
        if candidate is not None:
            with output.with_suffix('.candidate.json').open('x', encoding='utf8') as stream:
                json.dump(candidate, stream)
        print(json.dumps(dict(status=report['status'], knots=report['required_knots'],
            solved=len(report['rows']), failure_time=report.get('failure', {}).get('time'),
            failed_checks=report.get('failure', {}).get('failed_checks'))))
        return
    rows = []
    for frame in runtime['results']:
        t = frame['time']
        if frame['animation'] != 'external-motion' or not trajectory[0]['time'] <= t <= trajectory[-1]['time']:
            raise ValueError('source_ankle_time_mismatch')
        pose = matrices(document, 'external-motion', t)
        for index, side in enumerate(('l','r')):
            point = interpolate([dict(time=r['time'],vertices=r['targets'][index]) for r in trajectory],t,'vertices')
            evidence = solve(document,'external-motion',t,'thigh_'+side,'calf_'+side,'foot_'+side,point)
            rows.append(dict(time=t,side=side,target=point,
                input_error_px=math.dist(pose['foot_'+side][4:6],point),**evidence))
    report = dict(profile='moving-source-ankle-feasibility-v1',artifact_sha256=digest,
        source_observation=observation,records=rows,selected=False,authority='none',
        scope='independent_bounded_rotation_solutions_not_timeline_mesh_or_runtime_validation')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf8') as stream:json.dump(report,stream)
    print(json.dumps(dict(samples=len(runtime['results']),solutions=sum(r['solution'] is not None for r in rows),
        failures=sum(r['solution'] is None for r in rows),outer_bound_failures=sum(r['exceeds_outer_reach_bound'] for r in rows))))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--state',type=Path,default=Path('workspace'))
    p.add_argument('--timeline',action='store_true')
    a=p.parse_args();run(a.folder,a.state,a.output,timeline=a.timeline)
