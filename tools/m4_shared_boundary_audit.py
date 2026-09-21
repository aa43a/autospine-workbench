"""Freeze source-bound shared-boundary recheck outcomes, including failures."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.storage_io import canonical_bytes


def audit(folder,frozen):
    raw=(folder/'report.json').read_bytes();report=json.loads(raw)
    parents=[e for e in frozen['experiments'] if e['report_sha256']==report['parent_report_sha256']]
    if len(parents)!=1:raise ValueError('boundary_audit_parent_identity')
    parent=parents[0]
    if report['original_failure_counts']!=parent['failure_counts']:raise ValueError('boundary_audit_original_counts')
    for field in ('source_artifact_sha256','observations_sha256','inference_sha256'):
        if report[field]!=parent[field]:raise ValueError('boundary_audit_source_identity')
    if report['failure_counts']!=dict(Counter(f['reason_code'] for f in report['order']['failures'])):
        raise ValueError('boundary_audit_failure_counts')
    candidate=folder/'skeleton.json'
    if candidate.exists()!=('skeleton_sha256' in report):raise ValueError('boundary_audit_candidate_inventory')
    if candidate.exists() and sha256(candidate.read_bytes()).hexdigest()!=report['skeleton_sha256']:
        raise ValueError('boundary_audit_candidate_identity')
    return dict(report_sha256=sha256(raw).hexdigest(),parent_report_sha256=report['parent_report_sha256'],
        source_artifact_sha256=report['source_artifact_sha256'],original_failure_counts=report['original_failure_counts'],
        failure_counts=report['failure_counts'],refined_pair_samples=len(report['boundary_refinements']),
        triangle_pairs_checked=report['triangle_pairs_checked'],limit_reached=report['triangle_pair_limit_reached'],
        candidate_emitted=candidate.exists(),runtime_recaptured=False,authority='none',selected=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('folders',nargs='+',type=Path);args=parser.parse_args()
    frozen=json.loads(Path('docs/benchmark/m4-coherent-inference-evidence-v1.json').read_bytes())
    result=dict(profile='common-source-boundary-audit-v1',experiments=[audit(p,frozen) for p in args.folders])
    args.output.write_bytes(canonical_bytes(result));print(json.dumps(result))
