"""Recheck recorded three-format intake identities without importing new jobs."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.request import urlopen

from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader


def audit(reference, state, base):
    rows = []
    if sorted(r['format'] for r in reference['jobs']) != ['bvh', 'fbx', 'npz']:
        raise ValueError('expected_exact_three_formats')
    for previous in reference['jobs']:
        job, kind = previous['job_id'], previous['format']
        if not re.fullmatch(r'motion-[a-f0-9]{32}', job):
            raise ValueError('invalid_job')
        url = base.rstrip('/') + '/api/motions/' + job
        with urlopen(url, timeout=120) as response:
            current = json.load(response)
        if current['job_id'] != job or current['status'] != 'succeeded':
            raise ValueError('job_not_complete')
        result = current['result']
        if current['source_sha256'] != previous['source_sha256']:
            raise ValueError('source_identity_changed')
        folder = state / 'jobs/motion-intake-v1' / job
        source_hash = sha256((folder / ('source.' + kind)).read_bytes()).hexdigest()
        if source_hash != current['source_sha256']:
            raise ValueError('source_bytes_changed')
        identity = result['motion']
        if identity != previous['result']['motion']:
            raise ValueError('motion_identity_changed')
        VerifiedMotionBundleReader(state).load(identity['clip_sha256'], identity['bundle_sha256'])
        with urlopen(url + '/preview', timeout=120) as response:
            preview_hash = sha256(response.read()).hexdigest()
        if preview_hash != result['preview_sha256'] or preview_hash != previous['result']['preview_sha256']:
            raise ValueError('preview_changed')
        for field in ('frame_count', 'joint_count', 'fps'):
            if result[field] != previous['result'][field]:
                raise ValueError('source_shape_changed:' + field)
        if kind == 'fbx':
            bridge = json.loads((folder / 'bridge-verification.json').read_bytes())
            if bridge != result['fbx_bridge'] or bridge['passed'] is not True:
                raise ValueError('bridge_evidence_changed')
        rows.append(dict(format=kind, job_id=job, source_sha256=source_hash,
                         motion=identity, preview_sha256=preview_hash,
                         frames=result['frame_count'], joints=result['joint_count'],
                         immutable_bundle_reproduced=True))
    return dict(schema='autospine.m4-current-intake-audit/v1',
                checked_at=datetime.now(timezone.utc).isoformat(), rows=rows,
                scope='existing_source_bytes_compiled_bundle_and_preview_not_new_import_or_capture',
                authority='none', production_authorized=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--state', type=Path, default=Path('workspace'))
    parser.add_argument('--base', default='http://127.0.0.1:8918')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(json.loads(args.reference.read_bytes()), args.state, args.base)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    print(json.dumps([dict(format=r['format'], frames=r['frames'], joints=r['joints']) for r in report['rows']]))
