"""Compare exact-source independent and shared-plane inference experiments."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_coherent_inference_audit import audit as coherent_audit


def audit(before, after):
    old=json.loads((before/'report.json').read_bytes())
    new=json.loads((after/'report.json').read_bytes())
    for key in ('parent_report_sha256','source_artifact_sha256','observations_sha256','held_setup_pairs'):
        if old[key]!=new[key]:raise ValueError('plane_audit_source_changed')
    a=json.loads((before/'inference.json').read_bytes())
    b=json.loads((after/'inference.json').read_bytes())
    if set(a)!=set(b):raise ValueError('plane_audit_arm_inventory')
    changed=Counter();transitions=0
    for arm in a:
        if set(a[arm])!=set(b[arm]):raise ValueError('plane_audit_body_inventory')
        for body,frames in a[arm].items():
            updated=b[arm][body]
            if len(frames)!=len(updated):raise ValueError('plane_audit_frame_inventory')
            for prev,current in zip(frames,updated):
                for key in ('time','source_tick','observed_states','unresolved_triangles'):
                    if prev[key]!=current[key]:raise ValueError('plane_audit_observations_changed')
                for state,x,y in zip(prev['observed_states'],prev['labels'],current['labels']):
                    if x!=y:
                        if state!='A':raise ValueError('plane_audit_nonambiguous_changed')
                        changed[arm]+=1
            transitions+=sum(x!=y for f,g in zip(updated,updated[1:]) for x,y in zip(f['labels'],g['labels']))
    recorded=sum(r['changed_labels'] for r in new['shared_plane_coupling'])
    if recorded!=sum(changed.values()):raise ValueError('plane_audit_change_receipt')
    return dict(before=coherent_audit(before),after=coherent_audit(after),changed_ambiguous_labels=dict(changed),
                between_sample_transitions=transitions,nonambiguous_labels_changed=0,
                coupling_groups=len(new['shared_plane_coupling']),
                before_report_sha256=sha256((before/'report.json').read_bytes()).hexdigest(),
                runtime_recaptured=False,authority='none',selected=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('folders',nargs='+',type=Path);args=parser.parse_args()
    if len(args.folders)%2:parser.error('Expected before/after pairs')
    result=dict(profile='shared-plane-inference-audit-v1',experiments=[audit(*args.folders[i:i+2])
                for i in range(0,len(args.folders),2)])
    args.output.write_bytes(canonical_bytes(result));print(json.dumps(result))
