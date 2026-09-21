"""Audit hard proxy labels separately from inferred labels and order success."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.storage_io import canonical_bytes


def audit(folder):
    report_raw=(folder/'report.json').read_bytes();report=json.loads(report_raw)
    raw=(folder/'inference.json').read_bytes();models=json.loads(raw);counts=Counter();frames=0;violations=0;transitions=0
    for body_groups in models.values():
        groups=[body_groups] if isinstance(body_groups,list) else list(body_groups.values())
        for group in groups:
            for frame in group:
                if len(frame['observed_states'])!=len(frame['labels']):raise ValueError('coherent_audit_inventory')
                frames+=1;transitions+=frame['transition_count'];counts.update(frame['observed_states'])
                violations+=sum(state in 'FB' and label!=int(state=='F') for state,label in zip(frame['observed_states'],frame['labels']))
    if dict(counts)!=report['observed_state_counts'] or violations:raise ValueError('coherent_audit_evidence_changed')
    return dict(source_artifact_sha256=report['source_artifact_sha256'],observations_sha256=report['observations_sha256'],
        report_sha256=sha256(report_raw).hexdigest(),inference_sha256=sha256(raw).hexdigest(),
        regions=len(report['partition']['regions']),pair_frames=frames,state_counts=dict(counts),
        hard_proxy_violations=violations,model_transitions=transitions,order_status=report['order']['status'],
        failure_counts=report['failure_counts'],candidate_emitted='skeleton_sha256' in report,
        authority='none',selected=False,runtime_recaptured=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);parser.add_argument('folders',nargs='+',type=Path)
    args=parser.parse_args();result=dict(profile='coherent-depth-inference-audit-v1',experiments=[audit(p) for p in args.folders])
    args.output.write_bytes(canonical_bytes(result));print(json.dumps(result),flush=True)
