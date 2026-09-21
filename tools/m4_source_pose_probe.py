"""Create an isolated pose-calibration experiment from an exact M4 request."""
import argparse
import json
import math
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.motionir_candidate import build, ROLES
from autospine_workbench.targets.character43.oblique_source import extract
from autospine_workbench.targets.character43.source_pose_fit import fit
from m4_source_pose_view import render


def run(job, output):
    request = json.loads((Path('workspace/jobs/motion-intake-v1')/job/'request.json').read_bytes())
    if request.get('projection') or request.get('clip'):
        raise ValueError('probe_requires_full_original_projection')
    identity = request['motion_identity']
    bundle = VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'], identity['bundle_sha256'])
    files = AnimatedStore(Path('workspace')).read(request['character_sha256'])
    setup = json.loads(files['skeleton.json']); setup['animations'] = {}
    baseline, _ = build(setup, bundle.motion, 'external-motion')
    vectors, _, _ = extract(bundle)
    ticks = next(t for t in bundle.motion['tracks'] if t['property'] == 'rotation')['keys']
    times = [k['tick']/bundle.motion['ticks_per_second'] for k in ticks]
    candidate, report = fit(baseline, 'external-motion', vectors, times, project_lengths=True)
    records = {r['bone']: r for r in report['records']}
    frames = []
    for i, time in enumerate(times):
        before = matrices(baseline, 'external-motion', time)
        after = matrices(candidate, 'external-motion', time)
        for role, values in vectors.items():
            bone = ROLES.get(role)
            if bone not in records:
                continue
            x, y, _ = values[i]
            angle = math.degrees(math.atan2(-y, x))
            m = before[bone]
            error = abs((math.degrees(math.atan2(m[2], m[0]))-angle+180) % 360-180)
            row = records[bone]
            row['baseline_maximum_direction_error_deg'] = max(row.get('baseline_maximum_direction_error_deg', 0), error)
        frames.append(dict(time=time, source={r: v[i] for r, v in vectors.items()}, before={n: list(m[4:]) for n, m in before.items()},
                           after={n: list(m[4:]) for n, m in after.items()}))
    report.update(source_job_id=request['source_job_id'], baseline_job_id=job,
                  source_identity=identity, character_sha256=request['character_sha256'],
                  scope='rotation_only_calibration_experiment_not_replacement_for_existing_candidate',
                  runtime_verified=False)
    output.mkdir(parents=True, exist_ok=False)
    (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output/'skeleton.json').write_text(json.dumps(candidate), encoding='utf-8')
    (output/'index.html').write_text(render(frames, setup['bones']), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job'); parser.add_argument('output', type=Path)
    args = parser.parse_args(); run(args.job, args.output)
