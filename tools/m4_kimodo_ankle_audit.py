"""Read-only audit of exact local Kimodo bundles; not animation acceptance."""
import argparse
import json
import math
from pathlib import Path

from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.kimodo_npz_reader import decode_kimodo_npz
from autospine_workbench.kimodo_npz_consistency import validate_kimodo_consistency
from autospine_workbench.kimodo_soma77 import SOMA77_INDEX_BY_NAME
from autospine_workbench.targets.character43.source_ankle_targets import extract, targets


def run(state, output):
    rows = []
    for path in sorted((state/'motions').glob('*/*/source.npz')):
        identity = dict(clip_sha256=path.parent.parent.name, bundle_sha256=path.parent.name)
        try:
            bundle = VerifiedMotionBundleReader(state).load(**identity)
            pose = validate_kimodo_consistency(
                decode_kimodo_npz(bundle.raw_npz, bundle.kimodo_source), bundle.kimodo_source)
            basis = bundle.kimodo_map['basis']
            names = {r['role']: r['aim_joint_name'] for r in bundle.kimodo_map['bones']}
            checks = []
            for yaw in (-90, -30, 0, 30, 90):
                observation = extract(bundle, yaw)
                error = 0
                for frame, samples in zip(pose.positions, observation['points']):
                    for side, actual in zip(('left', 'right'), samples):
                        p = frame[SOMA77_INDEX_BY_NAME[names['humanoid.leg.lower.'+side]]]
                        x, y, z = [(1 if basis[k][0] == '+' else -1)*p['XYZ'.index(basis[k][1])]
                                   for k in ('screen_x', 'screen_y', 'depth')]
                        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
                        error = max(error, math.dist(actual, (c*x-s*z, y, s*x+c*z)))
                trajectory = targets(observation, [[0, 0], [0, 0]], 1)
                checks.append(dict(yaw=yaw, samples=len(trajectory), max_projection_error=error,
                    peak_normalized_displacement=max(math.hypot(*p) for row in trajectory for p in row['targets'])))
            if any(c['samples'] != pose.frame_count or c['max_projection_error'] > 1e-10 for c in checks):
                raise ValueError('ankle_projection_mismatch')
            rows.append(dict(identity, status='passed', source_id=bundle.kimodo_source['source_id'],
                producer=bundle.kimodo_source['producer']['status'], checks=checks))
        except (ValueError, RuntimeError, KeyError) as exc:
            rows.append(dict(identity, status='failed', reason=str(exc)))
    report = dict(profile='kimodo-moving-ankle-source-audit-v1', rows=rows,
        scope='source_extraction_only_not_solver_runtime_or_visual_acceptance', authority='none')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(dict(bundles=len(rows), passed=sum(r['status']=='passed' for r in rows),
                         failures=[r for r in rows if r['status']!='passed'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('state', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    run(args.state, args.output)
