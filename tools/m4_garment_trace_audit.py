"""Verify untouched original traces and source-bound garment inference evidence."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_coherent_inference_audit import audit as coherent_audit


def audit(parent,supplement,ordered):
    raw=(supplement/'report.json').read_bytes();report=json.loads(raw)
    for filename,field in [('report.json','parent_report_sha256'),('observations.json','parent_observations_sha256')]:
        if sha256((parent/filename).read_bytes()).hexdigest()!=report[field]:raise ValueError('garment_audit_parent_identity')
    for filename,field in [('observations.json','observations_sha256'),('checks.json','checks_sha256')]:
        if sha256((supplement/filename).read_bytes()).hexdigest()!=report[field]:raise ValueError('garment_audit_supplement_identity')
    original=json.loads((parent/'observations.json').read_bytes())
    extended=json.loads((supplement/'observations.json').read_bytes());checks=json.loads((supplement/'checks.json').read_bytes())
    if set(original)!=set(extended):raise ValueError('garment_audit_inventory')
    for arm,rows in original.items():
        if extended[arm][:len(rows)]!=rows:raise ValueError('garment_audit_original_changed')
    if sum(len(extended[a])-len(rows) for a,rows in original.items())!=len(checks):
        raise ValueError('garment_audit_check_inventory')
    counts=dict(Counter(c['status'] for c in checks))
    if counts!=report['status_counts']:raise ValueError('garment_audit_counts')
    inference=json.loads((ordered/'report.json').read_bytes())
    if (inference['parent_report_sha256']!=sha256(raw).hexdigest()
            or inference['supplemental_models']!=report['supplemental_models']
            or inference['observations_sha256']!=report['observations_sha256']):
        raise ValueError('garment_audit_inference_identity')
    return dict(supplement_report_sha256=sha256(raw).hexdigest(),parent_observations_sha256=report['parent_observations_sha256'],
        original_rows_preserved=True,added_checks=len(checks),status_counts=counts,
        supplemental_models=report['supplemental_models'],coherent=coherent_audit(ordered))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('roots',nargs='+',type=Path,help='Repeating triples: original supplement coherent')
    args=parser.parse_args()
    if len(args.roots)%3:parser.error('Expected triples of original, supplement and coherent directories')
    result=dict(profile='garment-supplement-coherent-audit-v1',experiments=[audit(*args.roots[i:i+3]) for i in range(0,len(args.roots),3)])
    args.output.write_bytes(canonical_bytes(result));print(json.dumps(result))
