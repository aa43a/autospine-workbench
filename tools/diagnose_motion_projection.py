"""Export source-bound projection intervals and curves for a compiled motion job."""
import argparse
import json
from pathlib import Path
from urllib.request import urlopen

from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.projection_diagnostics import (
    bvh_series, kimodo_series, summarize)
from autospine_workbench.automation.motion_projection_review import render


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('job_id')
    p.add_argument('output', type=Path)
    p.add_argument('--state-root', type=Path, default=Path('workspace'))
    args = p.parse_args()
    if not args.job_id.startswith('motion-') or not args.job_id[7:].isalnum():
        p.error('invalid motion job')
    with urlopen('http://127.0.0.1:8918/api/motions/'+args.job_id, timeout=180) as response:
        job = json.load(response)
    identity = job['result']['motion']
    bundle = VerifiedMotionBundleReader(args.state_root).load(identity['clip_sha256'], identity['bundle_sha256'])
    mapping = json.loads((bundle.path/'map.json').read_bytes())
    if bundle.source_kind == 'kimodo_npz':
        data = kimodo_series(bundle.raw_npz, bundle.kimodo_source, mapping)
    else:
        data = bvh_series(parse_bvh((bundle.path/'source.bvh').read_bytes()), mapping)
    report = summarize(*data)
    report.update(source_job_id=args.job_id, source_sha256=job['source_sha256'],
                  motion_identity=identity, basis=mapping['basis'])
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output/'index.html').write_bytes(render(report))
    print(json.dumps([dict(role=r['role'], min=r['minimum_visibility'], time=r['minimum_time'],
                          passed=r['passed']) for r in report['records']]))


if __name__ == '__main__':
    main()
