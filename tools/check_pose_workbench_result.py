"""Read actual API results and export; never submit or accept an animation."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.automation.animated_store import AnimatedStore


def check(base, job, previous, state, output):
    def get(path):
        with urlopen(base+'/api/motions/'+job+path, timeout=60) as response:
            return response.read(256 << 20)
    current = json.loads(get(''))
    if current['status'] != 'succeeded':
        raise ValueError('pose_check_job_not_complete')
    root = state/'jobs/motion-intake-v1'
    request = json.loads((root/job/'request.json').read_bytes())
    old = json.loads((root/previous/'request.json').read_bytes())
    if request['repair_execution'] != old['repair_execution']:
        raise ValueError('pose_check_retry_changed')
    result = current['result']
    archive = get('/download')
    with ZipFile(BytesIO(archive)) as zipped:
        if len(set(zipped.namelist())) != len(zipped.namelist()):
            raise ValueError('pose_check_duplicate_export_entries')
        files = {n: zipped.read(n) for n in zipped.namelist()}
    inventory = {n: sha256(raw).hexdigest() for n, raw in files.items()}
    if canonical_sha256(inventory) != result['artifact_sha256']:
        raise ValueError('pose_check_export_identity')
    plan = request['repair_execution']['draft']['pose_geometry']
    if json.loads(files['pose-geometry-request.json']) != plan:
        raise ValueError('pose_check_export_patch_changed')
    old_result = json.loads((root/previous/'worker-result.json').read_bytes())
    old_files = AnimatedStore(state).read(old_result['artifact_sha256'])
    if old_files['skeleton.json'] != files['skeleton.json']:
        raise ValueError('pose_check_retry_animation_changed')
    manifest = json.loads(files['character-manifest.json'])
    if any(inventory.get(n) != h for n, h in manifest['files'].items()):
        raise ValueError('pose_check_manifest_changed')
    readiness = json.loads(get('/view/readiness.json'))
    if readiness['artifact_sha256'] != result['artifact_sha256']:
        raise ValueError('pose_check_readiness_identity')
    runtime = json.loads((root/job/'runtime/report.json').read_bytes())
    if runtime['bundle_sha256'] != result['artifact_sha256'] or not runtime['passed']:
        raise ValueError('pose_check_runtime_failed')
    parent = json.loads(files['parent-motion-review.json'])
    review = json.loads(files['motion-review.json'])
    for key in ('source_pose_fit', 'projected_lengths'):
        if review.get(key) != parent.get(key):
            raise ValueError('pose_check_projection_evidence_lost')
    report = dict(job=job, previous=previous, artifact=result['artifact_sha256'],
        retry_preserved=True, retry_skeleton_identical=True, export_bytes=len(archive), export_sha256=sha256(archive).hexdigest(),
        export_files=len(files), runtime_frames=len(runtime['results']), runtime_numeric_passed=True,
        geometry_passed=result['geometry_passed'], contact_status=result['contact_status'],
        readiness_status=readiness['status'], stages=[dict(stage=s['stage'], status=s['status']) for s in readiness['stages']],
        selected=False, scope='workflow_identity_and_evidence_not_visual_acceptance')
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('job'); parser.add_argument('previous')
    parser.add_argument('output', type=Path)
    parser.add_argument('--base', default='http://127.0.0.1:8918')
    parser.add_argument('--state', type=Path, default=Path('workspace'))
    args = parser.parse_args()
    check(args.base, args.job, args.previous, args.state, args.output)
