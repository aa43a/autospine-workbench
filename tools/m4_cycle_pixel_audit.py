"""Freeze exact report/heatmap identities without converting diagnostics to acceptance."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.storage_io import canonical_bytes


def audit(folder,frozen):
    raw=(folder/'report.json').read_bytes();report=json.loads(raw)
    matches=[r for r in frozen['experiments'] if r['report_sha256']==report['order_report_sha256']]
    if len(matches)!=1 or matches[0]['source_artifact_sha256']!=report['source_artifact_sha256']:
        raise ValueError('cycle_pixels_audit_source_identity')
    counts=dict(Counter(r['status'] for r in report['rows']))
    if counts!=report['status_counts']:raise ValueError('cycle_pixels_audit_counts')
    images={}
    for row in report['rows']:
        for key in ('full','zoom'):
            name=row.get(key)
            if not name:continue
            if Path(name).name!=name:raise ValueError('cycle_pixels_audit_image_path')
            images[name]=sha256((folder/name).read_bytes()).hexdigest()
    return dict(source_artifact_sha256=report['source_artifact_sha256'],report_sha256=sha256(raw).hexdigest(),
        order_report_sha256=report['order_report_sha256'],status_counts=counts,rows=len(report['rows']),
        affected_failure_times=len({r['order_failure_time'] for r in report['rows'] if r['common_pixels']>0})
            if all('common_pixels' in r for r in report['rows']) else None,
        maximum_common_pixels=max((r['common_pixels'] for r in report['rows'] if 'common_pixels' in r),default=None),
        skipped_failures=report['skipped_failures'],images_sha256=images,
        authority='none',selected=False,runtime_recaptured=False,candidate_emitted=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('folders',nargs='+',type=Path);args=parser.parse_args()
    frozen=json.loads(Path('docs/benchmark/m4-shared-boundary-evidence-v1.json').read_bytes())
    result=dict(profile='same-frame-cycle-pixels-audit-v1',experiments=[audit(p,frozen) for p in args.folders])
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps([{k:v for k,v in r.items() if k!='images_sha256'} for r in result['experiments']]))
