"""Read exact successful jobs and audit final axes against verified source data."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.oblique_source import extract
from autospine_workbench.targets.character43.motion_direction_audit import audit


def run(job):
    root = Path('workspace/jobs/motion-intake-v1') / job
    request = json.loads((root/'request.json').read_bytes())
    result = json.loads((root/'result.json').read_bytes())
    if result['status'] != 'succeeded' or request.get('projection') or request.get('clip'):
        raise ValueError('audit_requires_successful_original_full_clip')
    identity = request['motion_identity']
    bundle = VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'], identity['bundle_sha256'])
    artifact = result['result']['artifact_sha256']
    files = AnimatedStore('workspace').read(artifact)
    vectors, _, _ = extract(bundle)
    tracks = [t for t in bundle.motion['tracks'] if t['property'] == 'rotation']
    ticks = [k['tick'] for k in tracks[0]['keys']]
    if any([k['tick'] for k in t['keys']] != ticks for t in tracks):
        raise ValueError('source_sample_grid_mismatch')
    report = audit(json.loads(files['skeleton.json']), 'external-motion', vectors,
                   [t/bundle.motion['ticks_per_second'] for t in ticks])
    report.update(job_id=job, project_id=request['project_id'], source_identity=identity,
                  artifact_sha256=artifact, skeleton_sha256=sha256(files['skeleton.json']).hexdigest())
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('jobs', nargs='+')
    args = parser.parse_args()
    reports = [run(job) for job in args.jobs]
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(reports, handle, indent=2)
    for report in reports:
        print(report['project_id'], report['job_id'])
        for row in report['records']:
            print(row['bone'], row['worst_direction'], 'unreliable', len(row['unreliable_times']))
