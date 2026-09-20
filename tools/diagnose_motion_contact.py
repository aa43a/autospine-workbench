"""Inspect inferred BVH support intervals without rewriting or adopting motion."""
import argparse
import json
from pathlib import Path
from urllib.request import urlopen

from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.motion2d.contact_candidate import infer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job_id')
    parser.add_argument('output', type=Path)
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    args = parser.parse_args()
    if not args.job_id.startswith('motion-') or not args.job_id[7:].isalnum():
        parser.error('invalid motion job')
    with urlopen('http://127.0.0.1:8918/api/motions/'+args.job_id, timeout=180) as response:
        job = json.load(response)
    if job.get('kind') == 'adapt' or job['status'] != 'succeeded':
        parser.error('compiled source job required')
    identity = job['result']['motion']
    bundle = VerifiedMotionBundleReader(args.state_root).load(identity['clip_sha256'], identity['bundle_sha256'])
    if bundle.source_kind == 'kimodo_npz':
        parser.error('BVH/FBX required; Kimodo contact labels remain authoritative')
    report = infer(parse_bvh((bundle.path/'source.bvh').read_bytes()),
                   json.loads((bundle.path/'map.json').read_bytes()))
    report.update(source_job_id=args.job_id, input_source_sha256=job['source_sha256'], motion_identity=identity)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(status=report['status'], intervals=len(report['markers']))))


if __name__ == '__main__':
    main()
