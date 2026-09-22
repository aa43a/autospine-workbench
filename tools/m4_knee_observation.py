"""Read exact isolated candidate and verified source; never changes adoption."""
import argparse
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.knee_projection import build


def run(folder, output):
    receipt = json.loads((folder/'report.json').read_bytes())
    job = receipt['source_job_id']
    if not job.startswith('motion-') or len(job) != 39 or any(c not in '0123456789abcdef' for c in job[7:]):
        raise ValueError('invalid_source_job')
    request = json.loads((Path('workspace/jobs/motion-intake-v1')/job/'request.json').read_bytes())
    identity = request['motion_identity']
    source = VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'], identity['bundle_sha256'])
    artifact = receipt['candidate_bundle_sha256']
    files = AnimatedStore(folder/'isolated-store').read(artifact)
    report = build(files, artifact, source, request)
    report['source_identity'] = identity
    report['source_job_id'] = job
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(artifact=artifact, samples=len(report['rows']),
        worst=[min((r for r in report['rows'] if r['side']==side and r['source']['status']=='measured'),
            key=lambda r:min(r['source']['projection_visibility'])) for side in ('left','right')]), ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    run(args.candidate, args.output)
