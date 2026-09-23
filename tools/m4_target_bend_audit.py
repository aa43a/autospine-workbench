"""Compare exact group-projection artifacts with declared source bend evidence."""
import argparse
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.group_bend_evidence import evidence
from autospine_workbench.targets.character43.group_projection_pose import source_segments


def run(folder):
    probe = json.loads((folder/'probe.json').read_bytes())
    identity = probe['source_identity']
    bundle = VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'], identity['bundle_sha256'])
    segments = source_segments(bundle)
    tracks = [t for t in bundle.motion['tracks'] if t['property'] == 'rotation']
    ticks = [k['tick'] for k in tracks[0]['keys']]
    if any([k['tick'] for k in t['keys']] != ticks for t in tracks):
        raise ValueError('bend_audit_source_ticks_mismatch')
    times = [t/bundle.motion['ticks_per_second'] for t in ticks]
    results = []
    for stage in ('candidate', 'target-contact'):
        location = folder/stage
        receipt = json.loads((location/'report.json').read_bytes())
        if receipt['parent_sha256'] != probe['parent']:
            raise ValueError('bend_audit_parent_mismatch')
        artifact = receipt['candidate_bundle_sha256']
        files = AnimatedStore(location/'isolated-store').read(artifact)
        document = json.loads(files['skeleton.json'])
        rows = []
        for i, time in enumerate(times):
            pose = matrices(document, 'external-motion', time)
            for side, suffix in (('left', 'l'), ('right', 'r')):
                expected = evidence(segments[f'humanoid.leg.upper.{side}'][i][1],
                                    segments[f'humanoid.leg.lower.{side}'][i][1], -90)
                a, b, c = [pose[name+'_'+suffix][4:6] for name in ('thigh', 'calf', 'foot')]
                # Target uses screen-up; source basis and branch evidence use screen-down.
                observed = evidence([b[0]-a[0], a[1]-b[1], 0], [c[0]-b[0], b[1]-c[1], 0], 0)
                status = ('unknown' if None in (expected['branch'], observed['branch']) else
                          'match' if expected['branch'] == observed['branch'] else 'opposite')
                rows.append(dict(time=time, side=side, expected=expected, observed=observed, status=status))
        results.append(dict(stage=stage, artifact=artifact, samples=rows,
                            counts={s: sum(r['status'] == s for r in rows) for s in ('match', 'opposite', 'unknown')}))
    return dict(scope='sampled_target_joint_bend_not_mesh_silhouette_or_acceptance', selected=False,
                source_identity=identity, source_yaw=-90, requested_branch=probe['branch'], stages=results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = run(args.folder)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps([dict(stage=s['stage'], counts=s['counts']) for s in report['stages']]))
