"""Check exact NPZ source feet through the existing full-view pose preparation."""
import argparse
import json
from pathlib import Path
from urllib.request import urlopen
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.automation.motion_view_pose import prepare


def run(job):
    with urlopen('http://127.0.0.1:8918/api/motions/'+job, timeout=60) as response:
        value = json.load(response)
    if value['status'] != 'succeeded' or value.get('format') != 'npz':
        raise ValueError('compiled_npz_required')
    identity = value['result']['motion']
    bundle = VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'], identity['bundle_sha256'])
    original = canonical_sha256(bundle.motion)
    rows = []
    for yaw in (0, -45, 45):
        motion, view, pose = prepare(bundle, yaw, post_contact=True)
        feet = pose['foot_observations']
        if motion['markers'] != bundle.motion['markers'] or feet['times'] != pose['times']:
            raise ValueError('source_labels_or_time_changed')
        rows.append(dict(yaw=yaw, samples=len(feet['times']), records=feet['records'],
                         profile=feet['profile'], observations_sha256=canonical_sha256(feet)))
    if canonical_sha256(bundle.motion) != original:
        raise ValueError('source_motion_changed')
    return dict(job_id=job, motion_identity=identity, views=rows, authority='none',
                source_markers_preserved=True, scope='source_pose_preparation_not_target_or_runtime_acceptance')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job'); parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = run(args.job)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False))
